from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, Optional

from crewai import Agent, Crew, LLM, Process, Task

from engine.llm_config import ModelMatrix, ModelTier, build_model_matrix

# Project root is two levels up from this module (src/engine/ → project root)
_MODULE_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


class CrewAIThreeTierOrchestrator:
    """
    CrewAI-backed orchestrator that preserves the 3-tier boundaries:
      - Orchestration tier: manager/router (Gemini primary → GPT-5.2-Codex fallback)
      - Level 1: senior/analytical agents (GPT-5.2-Codex primary → MiniMax fallback)
      - Level 2: execution/worker agents (MiniMax primary → DeepSeek fallback)

    Memory is enabled at Crew level and stored under <workspace>/.agent/memory/crewai_storage.
    """

    def __init__(
        self,
        workspace_dir: str,
        *,
        verbose: bool = True,
        telemetry_hook: Optional[Callable[[str, dict], None]] = None,
    ):
        self.workspace = Path(workspace_dir).resolve()
        self.verbose = verbose
        self.telemetry_hook = telemetry_hook

        # Ensure 3-tier expected directories exist.
        (self.workspace / ".agent" / "tmp").mkdir(parents=True, exist_ok=True)
        (self.workspace / ".agent" / "memory").mkdir(parents=True, exist_ok=True)

        # Bind CrewAI memory storage into the 3-tier memory namespace.
        storage_dir = self.workspace / ".agent" / "memory" / "crewai_storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        os.environ["CREWAI_STORAGE_DIR"] = str(storage_dir)

        self.models: ModelMatrix = build_model_matrix(
            self.workspace,
            project_root=_MODULE_PROJECT_ROOT,
        )

    def _emit_telemetry(self, event_type: str, details: dict) -> None:
        if self.telemetry_hook is None:
            return
        try:
            self.telemetry_hook(event_type, details)
        except Exception:
            # Telemetry should never block execution.
            return

    @staticmethod
    def _is_soft_failure(result: str) -> bool:
        lowered = result.lower().strip()
        if not lowered:
            return True
        return (
            "i cannot fulfill this request" in lowered
            or "as an ai language model" in lowered
        )

    def _run_stage_with_tier_fallback(
        self,
        *,
        stage_name: str,
        tier_name: str,
        tier: ModelTier,
        runner: Callable[[LLM], str],
    ) -> str:
        try:
            primary_result = runner(tier.primary)
            if self._is_soft_failure(primary_result):
                raise RuntimeError("Primary model returned a soft-failure response.")
            return primary_result
        except Exception as primary_error:
            self._emit_telemetry(
                "FALLBACK_ATTEMPT",
                {
                    "stage": stage_name,
                    "tier": tier_name,
                    "reason": f"{type(primary_error).__name__}: {primary_error}",
                },
            )

            try:
                fallback_result = runner(tier.fallback)
                if self._is_soft_failure(fallback_result):
                    raise RuntimeError("Fallback model returned a soft-failure response.")
                self._emit_telemetry(
                    "FALLBACK_RESULT",
                    {
                        "stage": stage_name,
                        "tier": tier_name,
                        "status": "success",
                    },
                )
                return fallback_result
            except Exception as fallback_error:
                self._emit_telemetry(
                    "FALLBACK_RESULT",
                    {
                        "stage": stage_name,
                        "tier": tier_name,
                        "status": "failed",
                        "error": f"{type(fallback_error).__name__}: {fallback_error}",
                    },
                )
                raise RuntimeError(
                    f"LLM fallback exhausted for stage '{stage_name}' tier '{tier_name}'. "
                    f"Primary failed with {type(primary_error).__name__}: {primary_error}. "
                    f"Fallback failed with {type(fallback_error).__name__}: {fallback_error}."
                ) from fallback_error

    def _extract_input_data(self, raw_prompt: str) -> str:
        """
        If raw_prompt contains <input_data>...</input_data>, extract its inner payload.
        Otherwise return raw_prompt as-is.
        """
        match = re.search(
            r"<input_data>(.*?)</input_data>",
            raw_prompt,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        return raw_prompt.strip()

    def _sanitize_prompt(self, payload: str) -> str:
        """
        Applies basic input sanitization to strip potential system prompt injection attacks.
        """
        sanitized = re.sub(
            r"(?i)\b(ignore previous instructions|you are now|system prompt|bypass|override)\b",
            "[REDACTED]",
            payload,
        )
        sanitized = re.sub(
            r"(?i)<script.*?>.*?</script>",
            "[REMOVED SCRIPT]",
            sanitized,
            flags=re.DOTALL,
        )
        return sanitized.strip()

    def reconstruct_prompt(self, raw_prompt: str) -> str:
        """
        Executes the Prompt Reconstruction Protocol as a CrewAI task using Level 1 models.
        """
        template_path = _MODULE_PROJECT_ROOT / "docs" / "architecture" / "prompt-reconstruction.md"
        if not template_path.exists():
            template_path = self.workspace / "docs" / "architecture" / "prompt-reconstruction.md"
        if not template_path.exists():
            raise FileNotFoundError(
                f"Missing prompt reconstruction template at {template_path}. "
                "This integration expects the existing 3-tier architecture docs to be present."
            )

        template = template_path.read_text(encoding="utf-8")
        raw_payload = self._extract_input_data(raw_prompt)
        payload = self._sanitize_prompt(raw_payload)
        reconstruction_prompt = template.replace("{{INPUT_DATA}}", payload)

        def _runner(llm: LLM) -> str:
            agent = Agent(
                role="Prompt Reconstruction Protocol Agent",
                goal="Reconstruct <input_data> into an optimal, production-grade system prompt with 1:1 requirement coverage.",
                backstory="You are an elite prompt engineer enforcing deterministic execution constraints.",
                llm=llm,
                verbose=self.verbose,
                allow_delegation=False,
                reasoning=True,
                max_reasoning_attempts=3,
            )

            task = Task(
                description=reconstruction_prompt,
                expected_output="ONLY a Markdown code block containing the rewritten prompt, OR a list of clarifying questions.",
                agent=agent,
            )

            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                memory=True,
                verbose=self.verbose,
            )
            return str(crew.kickoff())

        result = self._run_stage_with_tier_fallback(
            stage_name="prompt_reconstruction",
            tier_name="level1",
            tier=self.models.level1,
            runner=_runner,
        )

        out_path = self.workspace / ".agent" / "tmp" / "reconstructed_prompt.md"
        out_path.write_text(result, encoding="utf-8")
        return result

    def run_research(self, reconstructed_prompt: str) -> str:
        """
        Executes the Internet Research Agent role as a CrewAI task using Level 1 models.
        """

        def _runner(llm: LLM) -> str:
            agent = Agent(
                role="Internet Research Agent",
                goal="Produce verified constraints/context for the reconstructed prompt (official sources only).",
                backstory="You are a technical OSINT analyst. You do not write project code; you provide ground-truth constraints.",
                llm=llm,
                verbose=self.verbose,
                allow_delegation=False,
                reasoning=True,
                max_reasoning_attempts=3,
            )

            task = Task(
                description=(
                    "Perform technical research strictly from official / primary documentation sources.\n\n"
                    "INPUT (Reconstructed Prompt):\n"
                    f"{reconstructed_prompt}\n\n"
                    "OUTPUT REQUIREMENTS:\n"
                    "- Provide constraints, API limits, model configuration facts, and integration gotchas.\n"
                    "- Prefer official documentation and vendor API references.\n"
                    "- Be explicit about any missing configuration that blocks execution.\n"
                ),
                expected_output="A concise but complete research context, suitable to be passed to an orchestrator agent.",
                agent=agent,
            )

            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                memory=True,
                verbose=self.verbose,
            )
            return str(crew.kickoff())

        result = self._run_stage_with_tier_fallback(
            stage_name="research",
            tier_name="level1",
            tier=self.models.level1,
            runner=_runner,
        )

        out_path = self.workspace / ".agent" / "tmp" / "research-context.md"
        out_path.write_text(result, encoding="utf-8")
        return result

    def execute(self, reconstructed_prompt: str, research_context: str) -> str:
        """
        Executes the main 3-tier Crew using a hierarchical process:
          - Manager/router: orchestration-tier models
          - Senior agents: level1-tier models
          - Worker agent: level2-tier models
        """

        def _run_once(*, use_fallback: bool) -> str:
            orchestration_llm = (
                self.models.orchestration.fallback
                if use_fallback
                else self.models.orchestration.primary
            )
            level1_llm = self.models.level1.fallback if use_fallback else self.models.level1.primary
            level2_llm = self.models.level2.fallback if use_fallback else self.models.level2.primary

            manager = Agent(
                role="Orchestration Tier Manager/Router",
                goal="Plan, delegate, and validate completion using strict success-criteria enforcement.",
                backstory="You are a CTO-level manager agent. You delegate to senior and worker agents, enforce single-source-of-truth, and reject placeholder output.",
                llm=orchestration_llm,
                verbose=self.verbose,
                allow_delegation=True,
                reasoning=True,
                max_reasoning_attempts=3,
            )

            senior = Agent(
                role="Level 1 Senior/Analytical Agent",
                goal="Decompose objectives and produce an execution plan with strict acceptance criteria per task.",
                backstory="You are a senior systems architect. You translate requirements into executable work packages and guardrails.",
                llm=level1_llm,
                verbose=self.verbose,
                allow_delegation=True,
                reasoning=True,
                max_reasoning_attempts=3,
            )

            worker_tools = []
            try:
                from crewai_tools import FileReadTool, FileWriterTool

                worker_tools = [FileReadTool(), FileWriterTool()]
            except Exception as tool_error:
                self._emit_telemetry(
                    "TOOLING_WARNING",
                    {
                        "stage": "execution_hierarchical",
                        "warning": (
                            "crewai_tools unavailable; continuing without file tools. "
                            f"{type(tool_error).__name__}: {tool_error}"
                        ),
                    },
                )

            worker = Agent(
                role="Level 2 Execution/Worker Agent",
                goal="Implement atomic tasks with zero placeholders and explicit error handling.",
                backstory="You are an elite staff engineer who produces complete, executable artefacts with no TODOs and no simulated logic.",
                llm=level2_llm,
                verbose=self.verbose,
                allow_delegation=False,
                tools=worker_tools,
                reasoning=True,
                max_reasoning_attempts=2,
            )

            kickoff_task = Task(
                description=(
                    "You are executing inside the Antigravity 3-tier architecture.\n\n"
                    "INPUTS:\n"
                    "1) Reconstructed Prompt:\n"
                    f"{reconstructed_prompt}\n\n"
                    "2) Research Context:\n"
                    f"{research_context}\n\n"
                    "REQUIREMENTS:\n"
                    "- Produce a complete, production-grade answer with no placeholder code and no TODOs.\n"
                    "- Where code is required, output exact files (paths + full contents).\n"
                    "- If shell operations are required, provide a single combined script.\n"
                    "- Enforce a strict single-source-of-truth across files.\n"
                ),
                expected_output=(
                    "A complete deliverable set (plans + code + scripts) with explicit file paths and full file contents."
                ),
                agent=manager,
            )

            crew = Crew(
                agents=[senior, worker],
                tasks=[kickoff_task],
                process=Process.hierarchical,
                manager_agent=manager,
                memory=True,
                planning=True,
                verbose=self.verbose,
                cache=True,
            )
            return str(crew.kickoff())

        try:
            result = _run_once(use_fallback=False)
            if self._is_soft_failure(result):
                raise RuntimeError("Primary execute run returned a soft-failure response.")
        except Exception as primary_error:
            self._emit_telemetry(
                "FALLBACK_ATTEMPT",
                {
                    "stage": "execution_hierarchical",
                    "tier": "all",
                    "reason": f"{type(primary_error).__name__}: {primary_error}",
                },
            )
            try:
                result = _run_once(use_fallback=True)
                if self._is_soft_failure(result):
                    raise RuntimeError("Fallback execute run returned a soft-failure response.")
                self._emit_telemetry(
                    "FALLBACK_RESULT",
                    {
                        "stage": "execution_hierarchical",
                        "tier": "all",
                        "status": "success",
                    },
                )
            except Exception as fallback_error:
                self._emit_telemetry(
                    "FALLBACK_RESULT",
                    {
                        "stage": "execution_hierarchical",
                        "tier": "all",
                        "status": "failed",
                        "error": f"{type(fallback_error).__name__}: {fallback_error}",
                    },
                )
                raise RuntimeError(
                    "LLM fallback exhausted for stage 'execution_hierarchical'. "
                    f"Primary failed with {type(primary_error).__name__}: {primary_error}. "
                    f"Fallback failed with {type(fallback_error).__name__}: {fallback_error}."
                ) from fallback_error

        out_path = self.workspace / ".agent" / "tmp" / "final_output.md"
        out_path.write_text(result, encoding="utf-8")
        return result
