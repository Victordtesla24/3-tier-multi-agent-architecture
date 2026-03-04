from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from crewai import Agent, Crew, LLM, Process, Task

from engine.llm_config import (
    ModelMatrix,
    ModelTier,
    build_model_matrix,
    classify_provider_error,
)
from engine.orchestration_tools import (
    CompleteTaskTool,
    ReadRuntimeConfigTool,
    RunBenchmarksTool,
    RunTestsTool,
    UpdateRuntimeConfigTool,
)
from engine.project_root_tools import ProjectRootFileReadTool, ProjectRootFileWriteTool
from engine.workflow_primitives import (
    llm_call,
    load_prompt_template,
    normalize_research_markdown,
    sanitize_user_input,
    write_workspace_file,
)
from engine.workspace_tools import WorkspaceFileReadTool, WorkspaceFileWriteTool

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
        strict_provider_validation: bool = True,
        run_id: Optional[str] = None,
        telemetry_hook: Optional[Callable[[str, dict], None]] = None,
    ):
        self.workspace = Path(workspace_dir).resolve()
        self.verbose = verbose
        self.strict_provider_validation = strict_provider_validation
        self.run_id = run_id
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
            strict_validation=self.strict_provider_validation,
        )

    def _emit_telemetry(self, event_type: str, details: dict) -> None:
        if self.telemetry_hook is None:
            return
        try:
            self.telemetry_hook(event_type, details)
        except Exception:
            # Telemetry should never block execution.
            return

    def _llm_identity(self, llm: LLM) -> tuple[str, str]:
        model = str(getattr(llm, "model", "unknown"))
        provider = model.split("/", maxsplit=1)[0] if "/" in model else "unknown"
        return provider, model

    def _emit_provider_attempt(
        self,
        *,
        stage: str,
        tier: str,
        llm: LLM,
        attempt: int,
        fallback_used: bool,
        status: str,
        error: Exception | None = None,
    ) -> None:
        provider, model = self._llm_identity(llm)
        classified = classify_provider_error(error, model=model) if error else {}
        details: dict[str, Any] = {
            "run_id": self.run_id,
            "stage": stage,
            "model": model,
            "provider": provider,
            "attempt": attempt,
            "request_id": None,
            "http_status": classified.get("http_status", 200 if error is None else None),
            "error_type": classified.get("error_type", "none" if error is None else type(error).__name__),
            "error_code": classified.get("error_code"),
            "retriable": classified.get("retriable", True if error is None else False),
            "fallback_used": fallback_used,
            "status": status,
        }
        if error is not None:
            details["error"] = f"{type(error).__name__}: {error}"
        self._emit_telemetry("PROVIDER_ATTEMPT", details)

    @staticmethod
    def _extract_final_answer(result: str) -> str:
        """
        CrewAI verbose traces can include full transcripts. Extract deterministic final answer
        when present to avoid downstream re-processing.
        """
        match = re.search(
            r"##\s*Final Answer:\s*(.*)$",
            result,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if not match:
            return result.strip()
        return match.group(1).strip() or result.strip()

    @staticmethod
    def _extract_input_data(raw_prompt: str) -> str:
        """
        Backward-compatible contract for tests/integrations that still call the
        historical extraction method.
        """
        return sanitize_user_input(raw_prompt)

    @staticmethod
    def _normalise_research_context(raw: str) -> str:
        """
        Backward-compatible wrapper around the shared workflow primitive.
        """
        return normalize_research_markdown(raw)

    def _build_worker_tools(self) -> list[Any]:
        # Safe-by-default tooling: scoped workspace tools + restricted project-root
        # tools + explicit health/runtime controls.
        tools = [
            WorkspaceFileReadTool(workspace_root=str(self.workspace)),
            WorkspaceFileWriteTool(workspace_root=str(self.workspace)),
            ProjectRootFileReadTool(project_root=str(_MODULE_PROJECT_ROOT)),
            ProjectRootFileWriteTool(project_root=str(_MODULE_PROJECT_ROOT)),
            RunTestsTool(project_root=str(_MODULE_PROJECT_ROOT)),
            RunBenchmarksTool(project_root=str(_MODULE_PROJECT_ROOT)),
            ReadRuntimeConfigTool(project_root=str(_MODULE_PROJECT_ROOT)),
            UpdateRuntimeConfigTool(),
            CompleteTaskTool(),
        ]
        self._emit_telemetry(
            "TOOLING_INFO",
            {
                "stage": "execution_hierarchical",
                "tooling": "workspace_projectroot_health_config",
                "status": "active",
                "tool_count": len(tools),
            },
        )
        return tools

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
            self._emit_provider_attempt(
                stage=stage_name,
                tier=tier_name,
                llm=tier.primary,
                attempt=1,
                fallback_used=False,
                status="started",
            )
            primary_result = llm_call(tier.primary, runner=runner)
            if self._is_soft_failure(primary_result):
                raise RuntimeError("Primary model returned a soft-failure response.")
            self._emit_provider_attempt(
                stage=stage_name,
                tier=tier_name,
                llm=tier.primary,
                attempt=1,
                fallback_used=False,
                status="success",
            )
            return primary_result
        except Exception as primary_error:
            self._emit_provider_attempt(
                stage=stage_name,
                tier=tier_name,
                llm=tier.primary,
                attempt=1,
                fallback_used=False,
                status="failed",
                error=primary_error,
            )
            self._emit_telemetry(
                "FALLBACK_ATTEMPT",
                {
                    "stage": stage_name,
                    "tier": tier_name,
                    "reason": f"{type(primary_error).__name__}: {primary_error}",
                },
            )

            try:
                self._emit_provider_attempt(
                    stage=stage_name,
                    tier=tier_name,
                    llm=tier.fallback,
                    attempt=2,
                    fallback_used=True,
                    status="started",
                )
                fallback_result = llm_call(tier.fallback, runner=runner)
                if self._is_soft_failure(fallback_result):
                    raise RuntimeError("Fallback model returned a soft-failure response.")
                self._emit_provider_attempt(
                    stage=stage_name,
                    tier=tier_name,
                    llm=tier.fallback,
                    attempt=2,
                    fallback_used=True,
                    status="success",
                )
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
                self._emit_provider_attempt(
                    stage=stage_name,
                    tier=tier_name,
                    llm=tier.fallback,
                    attempt=2,
                    fallback_used=True,
                    status="failed",
                    error=fallback_error,
                )
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

    def reconstruct_prompt(self, raw_prompt: str) -> str:
        """
        Executes the Prompt Reconstruction Protocol as a CrewAI task using Level 1 models.
        """
        template = load_prompt_template(
            "prompt-reconstruction.md",
            workspace=self.workspace,
            project_root=_MODULE_PROJECT_ROOT,
        )
        payload = sanitize_user_input(raw_prompt)
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

        write_workspace_file(self.workspace, ".agent/tmp/reconstructed_prompt.md", result)
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
                    "- Return markdown using this exact schema:\n"
                    "  - ## Summary\n"
                    "  - ## Citations[]\n"
                    "  - ## MissingConfig[]\n"
                    "  - ## RiskNotes[]\n"
                    "- Provide constraints, API limits, model configuration facts, and integration gotchas.\n"
                    "- Cite official documentation URLs in Citations[] whenever external facts are referenced.\n"
                    "- Be explicit about missing configuration that blocks execution.\n"
                ),
                expected_output=(
                    "Markdown with sections Summary, Citations[], MissingConfig[], RiskNotes[]; "
                    "include at least two citation URLs when external facts are required."
                ),
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

        normalised = normalize_research_markdown(result)
        write_workspace_file(self.workspace, ".agent/tmp/research-context.md", normalised)
        return normalised

    def execute(
        self,
        reconstructed_prompt: str,
        research_context: str,
        context_block: str | None = None,
    ) -> str:
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

            worker_tools = self._build_worker_tools()
            tooling_manifest = (
                "Tooling Manifest:\n"
                "- workspace_file_read/workspace_file_write: read/write files under the active workspace only.\n"
                "- project_root_file_read/project_root_file_write: read/write only in "
                ".agent/rules/*, .agent/workflows/*, docs/architecture/*.\n"
                "- run_tests/run_benchmarks: execute repository verification commands and return machine-readable output.\n"
                "- read_runtime_configuration/update_runtime_configuration: inspect or safely update runtime config.\n"
                "- complete_task: emit explicit completion signal with status success|partial|blocked."
            )

            worker = Agent(
                role="Level 2 Execution/Worker Agent",
                goal="Implement atomic tasks with zero placeholders and explicit error handling.",
                backstory=(
                    "You are an elite staff engineer who produces complete, executable artefacts "
                    "with no TODOs and no simulated logic.\n\n"
                    f"{tooling_manifest}"
                ),
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
                    "3) Runtime/Workspace Context:\n"
                    f"{context_block or 'No additional context supplied.'}\n\n"
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
                planning=False,
                verbose=self.verbose,
                cache=True,
            )
            return self._extract_final_answer(str(crew.kickoff()))

        try:
            self._emit_provider_attempt(
                stage="execution_hierarchical",
                tier="orchestration",
                llm=self.models.orchestration.primary,
                attempt=1,
                fallback_used=False,
                status="started",
            )
            result = _run_once(use_fallback=False)
            if self._is_soft_failure(result):
                raise RuntimeError("Primary execute run returned a soft-failure response.")
            self._emit_provider_attempt(
                stage="execution_hierarchical",
                tier="orchestration",
                llm=self.models.orchestration.primary,
                attempt=1,
                fallback_used=False,
                status="success",
            )
        except Exception as primary_error:
            self._emit_provider_attempt(
                stage="execution_hierarchical",
                tier="orchestration",
                llm=self.models.orchestration.primary,
                attempt=1,
                fallback_used=False,
                status="failed",
                error=primary_error,
            )
            self._emit_telemetry(
                "FALLBACK_ATTEMPT",
                {
                    "stage": "execution_hierarchical",
                    "tier": "all",
                    "reason": f"{type(primary_error).__name__}: {primary_error}",
                },
            )
            try:
                self._emit_provider_attempt(
                    stage="execution_hierarchical",
                    tier="orchestration",
                    llm=self.models.orchestration.fallback,
                    attempt=2,
                    fallback_used=True,
                    status="started",
                )
                result = _run_once(use_fallback=True)
                if self._is_soft_failure(result):
                    raise RuntimeError("Fallback execute run returned a soft-failure response.")
                self._emit_provider_attempt(
                    stage="execution_hierarchical",
                    tier="orchestration",
                    llm=self.models.orchestration.fallback,
                    attempt=2,
                    fallback_used=True,
                    status="success",
                )
                self._emit_telemetry(
                    "FALLBACK_RESULT",
                    {
                        "stage": "execution_hierarchical",
                        "tier": "all",
                        "status": "success",
                    },
                )
            except Exception as fallback_error:
                self._emit_provider_attempt(
                    stage="execution_hierarchical",
                    tier="orchestration",
                    llm=self.models.orchestration.fallback,
                    attempt=2,
                    fallback_used=True,
                    status="failed",
                    error=fallback_error,
                )
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

        write_workspace_file(self.workspace, ".agent/tmp/final_output.md", result)
        return result
