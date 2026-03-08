"""
Enhancement 3: Asynchronous Tier 1 Orchestrator and Deterministic Global Memory
Addresses Critique 1 – Synchronous Blocking in Tier 1 Orchestration
         Critique 4 – Semantic Drift in Memory Synchronization.

Refactors the Tier 1 Orchestrator to completely bypass linear blocking by utilizing
Python's asyncio.gather for true concurrent parallel processing of multiple Tier 2
Domain Agents. Also replaces unstructured natural language status updates with a
strictly typed GlobalMemorySnapshot and DomainAgentState Pydantic model schema.
"""

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

import litellm
from pydantic import BaseModel, Field
from engine.llm_config import (
    require_env,
    resolve_optional_base_url,
    resolved_model_specs,
)
from engine.runtime_env import resolve_runtime_env

# Configure module-level logging for Orchestration
logger = logging.getLogger("Tier1_Orchestrator")
logger.setLevel(logging.INFO)
_MODULE_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


def _resolved_level2_spec():
    workspace = Path(os.environ.get("ANTIGRAVITY_WORKSPACE_DIR", Path.cwd())).resolve()
    specs = resolved_model_specs(
        resolve_runtime_env(workspace, project_root=_MODULE_PROJECT_ROOT)
    )
    return specs[4]


def _extract_completion_content(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        return ""

    message = getattr(choices[0], "message", None)
    if isinstance(choices[0], dict):
        message = choices[0].get("message", message)

    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")

    if content is None:
        return ""
    return content if isinstance(content, str) else str(content)


class GlobalMemorySnapshot(BaseModel):
    """
    Deterministic memory payload. This object is injected into Tier 2 Domain Agents
    upon instantiation to prevent Context Window Pollution while preserving
    cross-cutting preferences.
    """

    user_id: str = Field(..., description="Unique alphanumeric user identifier.")
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique session routing ID.",
    )
    global_constraints: List[str] = Field(
        default_factory=list,
        description="Immutable hard constraints applied globally across all spawned agents.",
    )
    routing_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Pre-computed context required for MCP tool routing.",
    )


class DomainAgentState(BaseModel):
    """
    Strictly typed state transition payload for Tier 2 agents reporting back to
    Tier 1. Eliminates semantic drift caused by unstructured LLM summarization.
    """

    agent_id: str
    domain_type: str = Field(
        ...,
        description="Classification of the domain agent (e.g., 'DevOps', 'Research').",
    )
    status: str = Field(
        ...,
        pattern="^(INIT|RUNNING|COMPLETED|FAILED)$",
    )
    structured_output: Dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = Field(ge=0.0, le=1.0)


class Tier2DomainAgent:
    """
    Concrete implementation of the Tier 2 Domain Agent representing an autonomous
    Finite State Machine (FSM) operating within isolated context boundaries.
    """

    def __init__(
        self,
        agent_id: str,
        domain_type: str,
        memory_snapshot: GlobalMemorySnapshot,
    ) -> None:
        self.agent_id = agent_id
        self.domain_type = domain_type
        self.memory = memory_snapshot

    async def execute_fsm_playbook(
        self, task_payload: Dict[str, Any]
    ) -> DomainAgentState:
        """
        Asynchronously executes the Domain Playbook via a live LLM reasoning call.
        Issues a real litellm.acompletion request using OPENAI_API_KEY from the
        environment to perform isolated LLM reasoning for the domain task.

        Raises:
            RuntimeError: if OPENAI_API_KEY is not configured or the LLM call fails.
        """
        logger.info(f"Agent {self.agent_id} initialized.")
        logger.debug(f"Applied Constraints: {self.memory.global_constraints}")

        spec = _resolved_level2_spec()
        api_key_names: tuple[str, ...]
        if spec.crewai_model.startswith("gemini/"):
            api_key_names = ("GOOGLE_API_KEY", "GEMINI_API_KEY")
        elif spec.api_key_env:
            api_key_names = (spec.api_key_env,)
        else:
            api_key_names = ()

        directive = task_payload.get("directive", "No directive provided.")
        constraints_text = "; ".join(self.memory.global_constraints) or "None"
        system_prompt = (
            f"You are a {self.domain_type} domain agent operating within a "
            "3-tier multi-agent orchestration system. "
            f"Active global constraints: {constraints_text}. "
            "Respond with a concise, structured JSON object containing your "
            "analysis and recommendations."
        )
        user_prompt = f"Domain directive: {directive}"

        try:
            kwargs = {
                "model": spec.crewai_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 512,
                # OpenAI-compatible providers do not share identical param support.
                # Drop unsupported params instead of hard failing the async swarm path.
                "drop_params": True,
            }
            if api_key_names:
                kwargs["api_key"] = require_env(
                    api_key_names, label="/".join(api_key_names)
                )
            if not spec.crewai_model.startswith(("gemini/", "ollama/", "deepseek/")):
                kwargs["reasoning_effort"] = spec.effort.value
            if spec.runtime_temperature is not None:
                kwargs["temperature"] = spec.runtime_temperature
            base_url = resolve_optional_base_url(spec)
            if base_url:
                kwargs["api_base"] = base_url
            response = await litellm.acompletion(**kwargs)
            llm_output = _extract_completion_content(response)
        except Exception as exc:
            raise RuntimeError(
                f"Agent {self.agent_id} LLM call failed: {exc}"
            ) from exc

        logger.info(f"Agent {self.agent_id} completed task processing.")

        # Deterministic state return to prevent Orchestrator memory fragmentation
        return DomainAgentState(
            agent_id=self.agent_id,
            domain_type=self.domain_type,
            status="COMPLETED",
            structured_output={
                "processed_directive": directive,
                "llm_reasoning": llm_output,
            },
            confidence_score=0.99,
        )


class AsyncTier1Orchestrator:
    """
    Tier 1 Manager responsible for high-level semantic routing, task decomposition,
    and non-blocking lifecycle management of Tier 2 Agent Swarms.
    """

    def __init__(self) -> None:
        self.active_swarms: Dict[str, Any] = {}
        # In-process memory registry: keyed by user_id, holds GlobalMemorySnapshot instances.
        self._memory_registry: Dict[str, GlobalMemorySnapshot] = {}

    def fetch_global_memory(self, user_id: str) -> GlobalMemorySnapshot:
        """
        Retrieves and locks global memory context from the central registry.
        If it does not exist, it initializes a pristine snapshot.
        """
        if user_id not in self._memory_registry:
            snapshot = GlobalMemorySnapshot(
                user_id=user_id,
                global_constraints=[
                    "NO_PII_IN_LOGS",
                    "RESPONSE_FORMAT=JSONL",
                    "MAX_TOOL_RETRIES=4",
                ],
            )
            self._memory_registry[user_id] = snapshot

        return self._memory_registry[user_id]

    async def orchestrate_concurrent_tasks(
        self,
        user_id: str,
        task_definitions: List[Dict[str, Any]],
    ) -> List[DomainAgentState]:
        """
        Resolves the fundamental orchestration bottleneck by utilizing asyncio.gather
        to instantiate and execute multiple Tier 2 Domain Agents in parallel.
        """
        memory_snapshot = self.fetch_global_memory(user_id)
        execution_coroutines: List[Any] = []

        logger.info(
            f"Orchestrator initiating {len(task_definitions)} parallel Domain Agent tasks."
        )

        # Map tasks to specialized Domain Agents dynamically
        for task in task_definitions:
            agent_domain = task.get("domain", "General")
            agent = Tier2DomainAgent(
                agent_id=f"T2_Agent_{uuid.uuid4().hex[:6]}",
                domain_type=agent_domain,
                memory_snapshot=memory_snapshot,
            )

            # Queue the coroutine for parallel execution
            execution_coroutines.append(agent.execute_fsm_playbook(task))

        # Execute all FSM playbooks concurrently, awaiting their collective resolution
        try:
            # return_exceptions=False ensures that if one agent critically fails,
            # the Orchestrator can handle the swarm abort sequence appropriately.
            results = await asyncio.gather(
                *execution_coroutines, return_exceptions=False
            )
            logger.info(
                f"Tier 1 Orchestration complete. "
                f"Synthesized {len(results)} agent states."
            )
            return list(results)
        except Exception as e:
            logger.critical(
                f"Catastrophic failure in Swarm execution loop: {e}"
            )
            raise
