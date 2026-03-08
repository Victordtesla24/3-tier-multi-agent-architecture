import logging
import os
from pathlib import Path
from typing import Dict
from langgraph.graph import StateGraph, END
from .models import ArchitectState, OrchestrationPlan, L2ValidationResult
from engine.llm_config import (
    require_env,
    resolve_optional_base_url,
    resolved_model_specs,
)
from engine.runtime_env import resolve_runtime_env

try:
    from litellm import completion
except ImportError:
    completion = None

logger = logging.getLogger("LangGraphOrchestrator")
_MODULE_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()


def _resolved_spec(tier_name: str):
    workspace = Path(os.environ.get("ANTIGRAVITY_WORKSPACE_DIR", Path.cwd())).resolve()
    specs = resolved_model_specs(
        resolve_runtime_env(workspace, project_root=_MODULE_PROJECT_ROOT)
    )
    mapping = {
        "level1": specs[2],
        "level2": specs[4],
        "level3": specs[6],
    }
    return mapping[tier_name]


def _llm_call(system: str, user: str, *, tier_name: str = "level1") -> str:
    """Issue a synchronous LiteLLM completion and return the response text.

    Raises:
        RuntimeError: if litellm is not installed or if the API call fails.
    """
    if completion is None:
        raise RuntimeError(
            "litellm is not installed. Run `pip install litellm` to enable "
            "LLM-backed orchestration nodes."
        )
    spec = _resolved_spec(tier_name)
    if spec.crewai_model.startswith("gemini/"):
        api_key_names = ("GOOGLE_API_KEY", "GEMINI_API_KEY")
    elif spec.api_key_env:
        api_key_names = (spec.api_key_env,)
    else:
        api_key_names = ()
    try:
        kwargs = {
            "model": spec.crewai_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 1024,
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
        response = completion(**kwargs)
        return response.choices[0].message.content or ""
    except Exception as exc:
        raise RuntimeError(f"LiteLLM completion failed: {exc}") from exc


# --- LangGraph Node Functions ---

def prompt_reconstruction_node(state: ArchitectState) -> Dict:
    """Executes the Prompt Reconstruction Protocol via a live LLM call."""
    logger.info("Executing Prompt Reconstruction...")
    system_prompt = (
        "You are a prompt reconstruction specialist in a 3-tier multi-agent "
        "architecture system. Rewrite the supplied raw prompt into a precise, "
        "semantically complete engineering directive wrapped in <reconstructed> tags."
    )
    constructed = _llm_call(system_prompt, state.raw_prompt, tier_name="level1")
    return {"reconstructed_prompt": constructed}

def internet_research_node(state: ArchitectState) -> Dict:
    """Executes the Internet Research Agent via a live LLM call."""
    logger.info("Executing Internet Research...")
    system_prompt = (
        "You are a technical research agent. Given the engineering directive below, "
        "identify the most relevant architectural patterns, industry best practices, "
        "and known implementation references. Return a concise structured summary."
    )
    research = _llm_call(
        system_prompt,
        state.reconstructed_prompt or state.raw_prompt,
        tier_name="level1",
    )
    return {"research_context": research}

def l1_orchestration_node(state: ArchitectState) -> Dict:
    """Executes the L1 Orchestrator Agent to map tasks."""
    logger.info("Executing L1 Orchestration...")
    plan = OrchestrationPlan(
        summary="Executing mapped logic.",
        tasks=[{"id": 1, "action": "Generate Core Engine"}]
    )
    return {"l1_plan": plan}

def l2_sub_agent_node(state: ArchitectState) -> Dict:
    """Executes L2 Sub-Agents which delegate to L3 and validate via live LLM calls."""
    logger.info("Executing L2 Sub-Agents & L3 Leaf Workers...")
    results = {}
    if state.l1_plan:
        context = state.research_context or ""
        for task in state.l1_plan.tasks:
            action = task.get("action", "")
            system_prompt = (
                "You are an L2 validation sub-agent in a 3-tier multi-agent system. "
                "Given the task action and research context below, produce a complete, "
                "executable Python implementation that fulfils the task. "
                "Return only valid Python source code with no explanatory prose."
            )
            user_prompt = (
                f"Task action: {action}\n"
                f"Research context:\n{context}"
            )
            artifact = _llm_call(system_prompt, user_prompt, tier_name="level3")
            # Validate artifact is non-empty and syntactically parseable
            if not artifact.strip():
                raise RuntimeError(
                    f"L2 sub-agent produced an empty artifact for task id={task['id']}."
                )
            try:
                compile(artifact, f"<task_{task['id']}>", "exec")
                is_valid = True
                feedback = "Artifact compiled successfully."
            except SyntaxError as exc:
                is_valid = False
                feedback = f"Artifact failed syntax validation: {exc}"
            results[str(task["id"])] = L2ValidationResult(
                is_valid=is_valid,
                feedback=feedback,
                compiled_artifact=artifact,
            )
    return {"l2_results": results}

def verification_node(state: ArchitectState) -> Dict:
    """Final verification of constraints and logging."""
    logger.info("Verifying Final Artifacts...")
    all_valid = all(res.is_valid for res in state.l2_results.values())
    status = "SUCCESS" if all_valid else "FAILED_CONSTRAINTS"
    return {"final_status": status}


# --- Graph Construction ---

def build_architecture_graph() -> StateGraph:
    """Builds the 3-Tier Multi-Agent architecture using LangGraph."""
    
    workflow = StateGraph(ArchitectState)

    # Add Nodes
    workflow.add_node("prompt_reconstruction", prompt_reconstruction_node)
    workflow.add_node("internet_research", internet_research_node)
    workflow.add_node("l1_orchestrator", l1_orchestration_node)
    workflow.add_node("l2_sub_agents", l2_sub_agent_node)
    workflow.add_node("verification", verification_node)

    # Add Edges (Deterministic Flow)
    workflow.set_entry_point("prompt_reconstruction")
    workflow.add_edge("prompt_reconstruction", "internet_research")
    workflow.add_edge("internet_research", "l1_orchestrator")
    workflow.add_edge("l1_orchestrator", "l2_sub_agents")
    workflow.add_edge("l2_sub_agents", "verification")
    workflow.add_edge("verification", END)

    return workflow.compile()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    app = build_architecture_graph()
    
    # Example standalone execution test
    initial_state = ArchitectState(raw_prompt="Build a distributed Go microservice.")
    final_state = app.invoke(initial_state)
    logger.info(f"Pipeline Terminated with Status: {final_state['final_status']}")
