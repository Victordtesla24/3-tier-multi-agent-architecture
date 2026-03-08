from __future__ import annotations

import json
import logging
import os
import re
import asyncio
from pathlib import Path
from typing import Any, Callable, Optional

from crewai import Agent, Crew, LLM, Process, Task

from engine.exceptions import ProviderExhaustedError, SoftFailureError
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
from engine.runtime_graph import (
    DAGTaskExecutor,
    OrchestrationPlan,
    PlanningFailureError,
    ReflexiveTaskWorker,
    SemanticTaskPlanner,
    TaskGraphExecutionError,
    TaskGraphExecutionSummary,
    WorkerTask,
)
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

_telemetry_logger = logging.getLogger("AntigravityTelemetry")


class CrewAIThreeTierOrchestrator:
    """
    CrewAI-backed orchestrator that preserves an explicit orchestration tier plus
    three agent layers:
      - Orchestration tier: manager/router (GPT-5.4 primary → GPT-5.2 Codex fallback)
      - Level 1: analytical/planning agents (Gemini 3.1 Pro Preview primary → Ollama Qwen 3 14B fallback)
      - Level 2: coordination/validation agents (Ollama Qwen 3 8B primary → Ollama Qwen 3 14B fallback)
      - Level 3: execution/leaf-worker agents (Ollama Qwen 2.5 Coder 7B primary → Ollama Qwen 2.5 Coder 14B fallback)

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
        self._level2_evaluator_semaphore = (
            asyncio.Semaphore(self.models.level2_swarm_count)
            if self.models.level2_swarm_count
            else None
        )
        self._emit_runtime_env_resolved()

    def _emit_telemetry(self, event_type: str, details: dict) -> None:
        """Emit a telemetry event to the registered hook.

        Telemetry failures are logged at DEBUG level rather than silently
        swallowed, preserving production debuggability without blocking
        the pipeline execution path.
        """
        if self.telemetry_hook is None:
            return
        try:
            self.telemetry_hook(event_type, details)
        except Exception as exc:
            _telemetry_logger.debug(
                "Telemetry emission failed for event '%s': %s: %s",
                event_type,
                type(exc).__name__,
                exc,
            )

    def _llm_identity(self, llm: LLM) -> tuple[str, str]:
        model = str(getattr(llm, "model", "unknown"))
        provider = model.split("/", maxsplit=1)[0] if "/" in model else "unknown"
        return provider, model

    def _emit_runtime_env_resolved(self) -> None:
        self._emit_telemetry(
            "RUNTIME_ENV_RESOLVED",
            {
                "run_id": self.run_id,
                "tier_primary_logical_ids": dict(self.models.tier_primary_logical_ids),
                "tier_fallback_logical_ids": dict(
                    self.models.tier_fallback_logical_ids
                ),
                "tier_primary_runtime_models": {
                    "orchestration": str(self.models.orchestration.primary.model),
                    "level1": str(self.models.level1.primary.model),
                    "level2": str(self.models.level2.primary.model),
                    "level3": str(self.models.level3.primary.model),
                },
                "tier_fallback_runtime_models": {
                    "orchestration": str(self.models.orchestration.fallback.model),
                    "level1": str(self.models.level1.fallback.model),
                    "level2": str(self.models.level2.fallback.model),
                    "level3": str(self.models.level3.fallback.model),
                },
                "active_provider_env_keys": list(self.models.active_provider_env_keys),
                "level2_swarm_count": self.models.level2_swarm_count,
                "level3_swarm_count": self.models.level3_swarm_count,
                "warnings": list(self.models.config_warnings),
            },
        )

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
            "http_status": classified.get(
                "http_status", 200 if error is None else None
            ),
            "error_type": classified.get(
                "error_type", "none" if error is None else type(error).__name__
            ),
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

    @staticmethod
    def _worker_tooling_manifest() -> str:
        return (
            "Tooling Manifest:\n"
            "- workspace_file_read/workspace_file_write: read/write files under the active workspace only.\n"
            "- project_root_file_read/project_root_file_write: read/write only in "
            ".agent/rules/*, .agent/workflows/*, docs/architecture/*.\n"
            "- run_tests/run_benchmarks: execute repository verification commands and return machine-readable output.\n"
            "- read_runtime_configuration/update_runtime_configuration: inspect or safely update runtime config.\n"
            "- complete_task: emit explicit completion signal with status success|partial|blocked."
        )

    def _build_worker_tools(
        self, *, stage_name: str = "execution_hierarchical"
    ) -> list[Any]:
        # Safe-by-default tooling: scoped workspace tools + restricted project-root
        # tools + explicit health/runtime controls.
        tools = [
            WorkspaceFileReadTool(workspace_root=str(self.workspace)),
            WorkspaceFileWriteTool(workspace_root=str(self.workspace)),
            ProjectRootFileReadTool(project_root=str(_MODULE_PROJECT_ROOT)),
            ProjectRootFileWriteTool(project_root=str(_MODULE_PROJECT_ROOT)),
            RunTestsTool(project_root=str(_MODULE_PROJECT_ROOT)),
            RunBenchmarksTool(project_root=str(_MODULE_PROJECT_ROOT)),
            ReadRuntimeConfigTool(
                project_root=str(_MODULE_PROJECT_ROOT),
                workspace=str(self.workspace),
            ),
            UpdateRuntimeConfigTool(workspace=str(self.workspace)),
            CompleteTaskTool(),
        ]
        self._emit_telemetry(
            "TOOLING_INFO",
            {
                "stage": stage_name,
                "tooling": "workspace_projectroot_health_config",
                "status": "active",
                "tool_count": len(tools),
            },
        )
        return tools

    def _run_single_agent_task(
        self,
        *,
        llm: LLM,
        role: str,
        goal: str,
        backstory: str,
        description: str,
        expected_output: str,
        tools: list[Any] | None = None,
        allow_delegation: bool = False,
        max_reasoning_attempts: int = 3,
    ) -> str:
        agent_kwargs: dict[str, Any] = {
            "role": role,
            "goal": goal,
            "backstory": backstory,
            "llm": llm,
            "verbose": self.verbose,
            "allow_delegation": allow_delegation,
            "reasoning": True,
            "max_reasoning_attempts": max_reasoning_attempts,
        }
        if tools is not None:
            agent_kwargs["tools"] = tools

        agent = Agent(**agent_kwargs)
        task = Task(
            description=description,
            expected_output=expected_output,
            agent=agent,
        )
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            memory=True,
            verbose=self.verbose,
            cache=True,
        )
        return self._extract_final_answer(str(crew.kickoff()))

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
                _, model = self._llm_identity(tier.primary)
                raise SoftFailureError(
                    "Primary model returned a soft-failure response.",
                    stage=stage_name,
                    model=model,
                )
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
                    _, model = self._llm_identity(tier.fallback)
                    raise SoftFailureError(
                        "Fallback model returned a soft-failure response.",
                        stage=stage_name,
                        model=model,
                    )
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
                raise ProviderExhaustedError(
                    f"LLM fallback exhausted for stage '{stage_name}' tier '{tier_name}'. "
                    f"Primary failed with {type(primary_error).__name__}: {primary_error}. "
                    f"Fallback failed with {type(fallback_error).__name__}: {fallback_error}.",
                    stage=stage_name,
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                    tier=tier_name,
                ) from fallback_error

    def _plan_execution_graph(
        self,
        *,
        source_prompt: str,
        research_context: str,
        context_block: str | None,
    ) -> OrchestrationPlan:
        def _planner_call(planner_prompt: str) -> str:
            def _runner(llm: LLM) -> str:
                return self._run_single_agent_task(
                    llm=llm,
                    role="Semantic Task Planner",
                    goal="Break the objective into a strict, dependency-valid internal task graph.",
                    backstory=(
                        "You are an internal execution planner. You emit only strict JSON "
                        "task graphs that can be validated and executed without ambiguity."
                    ),
                    description=planner_prompt,
                    expected_output=(
                        "JSON object with original_query and tasks[]. "
                        "No markdown fences or commentary."
                    ),
                )

            return self._run_stage_with_tier_fallback(
                stage_name="execution_planning",
                tier_name="level1",
                tier=self.models.level1,
                runner=_runner,
            )

        planner = SemanticTaskPlanner(llm_planner=_planner_call)
        plan = planner.create_plan(
            source_prompt=source_prompt,
            research_context=research_context,
            context_block=context_block,
        )
        self._emit_telemetry(
            "EXECUTION_PLAN_CREATED",
            {
                "execution_mode": "task_graph",
                "plan_id": plan.plan_id,
                "task_count": len(plan.tasks),
                "tasks": [
                    {
                        "task_id": task.task_id,
                        "dependencies": list(task.dependencies),
                        "required_tools": list(task.required_tools),
                    }
                    for task in plan.tasks
                ],
            },
        )
        return plan

    def _run_task_graph_worker(
        self,
        *,
        task: WorkerTask,
        task_context: dict[str, Any],
        research_context: str,
        context_block: str | None,
        worker_tools: list[Any],
    ) -> str:
        dependency_results = json.dumps(
            task_context.get("dependency_results", {}),
            indent=2,
            sort_keys=True,
            default=str,
        )
        global_context = json.dumps(
            task_context.get("global", {}),
            indent=2,
            sort_keys=True,
            default=str,
        )
        previous_result = str(task_context.get("previous_result") or "None")
        qa_feedback = str(task_context.get("qa_feedback") or "None")
        required_tools = (
            ", ".join(task.required_tools) if task.required_tools else "none"
        )

        description = (
            "Execute a single atomic task inside the Antigravity task graph.\n\n"
            f"Task ID: {task.task_id}\n"
            f"Task Description: {task.description}\n"
            f"Required Tools: {required_tools}\n\n"
            f"Dependency Results:\n{dependency_results}\n\n"
            f"Research Context:\n{research_context}\n\n"
            f"Runtime Context:\n{context_block or 'No additional runtime context supplied.'}\n\n"
            f"Global Graph Context:\n{global_context}\n\n"
            f"Previous Attempt Output:\n{previous_result}\n\n"
            f"QA Feedback From Prior Attempt:\n{qa_feedback}\n\n"
            "Rules:\n"
            "- Return only the concrete output required for this task.\n"
            "- Do not emit placeholder text, TODO markers, or simulated logic.\n"
            "- Use the provided tools when the task requires repository interaction.\n"
        )

        def _runner(llm: LLM) -> str:
            return self._run_single_agent_task(
                llm=llm,
                role="Task Graph L3 Worker",
                goal="Complete one atomic task with production-grade output only.",
                backstory=(
                    "You are an elite L3 leaf worker executing a validated task graph.\n\n"
                    f"{self._worker_tooling_manifest()}"
                ),
                description=description,
                expected_output="Concrete task-local output only.",
                tools=worker_tools,
                max_reasoning_attempts=2,
            )

        return self._run_stage_with_tier_fallback(
            stage_name=f"task_execute_{task.task_id}",
            tier_name="level3",
            tier=self.models.level3,
            runner=_runner,
        )

    def _evaluate_task_graph_worker_output(
        self,
        *,
        task: WorkerTask,
        candidate_output: str,
        task_context: dict[str, Any],
    ) -> str:
        dependency_results = json.dumps(
            task_context.get("dependency_results", {}),
            indent=2,
            sort_keys=True,
            default=str,
        )

        description = (
            "Evaluate whether the worker output fully satisfies the task.\n\n"
            f"Task ID: {task.task_id}\n"
            f"Task Description: {task.description}\n\n"
            f"Dependency Results:\n{dependency_results}\n\n"
            f"Worker Output:\n{candidate_output}\n\n"
            "Reply with exactly one of the following:\n"
            "- PASS\n"
            "- FAIL: <specific reason>\n"
        )

        def _runner(llm: LLM) -> str:
            return self._run_single_agent_task(
                llm=llm,
                role="Task Graph L2 Evaluator",
                goal="Reject incomplete or malformed task outputs before they reach the graph state.",
                backstory=(
                    "You are a strict L2 coordination and QA agent. You do not repair outputs "
                    "yourself; you return PASS or a single actionable FAIL reason."
                ),
                description=description,
                expected_output="PASS or FAIL: <reason>",
            )

        return self._run_stage_with_tier_fallback(
            stage_name=f"task_evaluate_{task.task_id}",
            tier_name="level2",
            tier=self.models.level2,
            runner=_runner,
        )

    async def _evaluate_task_graph_worker_output_bounded(
        self,
        *,
        task: WorkerTask,
        candidate_output: str,
        task_context: dict[str, Any],
    ) -> str:
        if self._level2_evaluator_semaphore is None:
            return await asyncio.to_thread(
                self._evaluate_task_graph_worker_output,
                task=task,
                candidate_output=candidate_output,
                task_context=task_context,
            )

        async with self._level2_evaluator_semaphore:
            return await asyncio.to_thread(
                self._evaluate_task_graph_worker_output,
                task=task,
                candidate_output=candidate_output,
                task_context=task_context,
            )

    def _execute_task_graph(
        self,
        *,
        plan: OrchestrationPlan,
        reconstructed_prompt: str,
        research_context: str,
        context_block: str | None,
    ) -> TaskGraphExecutionSummary:
        worker_tools = self._build_worker_tools(stage_name="execution_task_graph")
        worker = ReflexiveTaskWorker(
            execution_runner=lambda task, task_context: self._run_task_graph_worker(
                task=task,
                task_context=task_context,
                research_context=research_context,
                context_block=context_block,
                worker_tools=worker_tools,
            ),
            evaluation_runner=lambda task, candidate_output, task_context: self._evaluate_task_graph_worker_output_bounded(
                task=task,
                candidate_output=candidate_output,
                task_context=task_context,
            ),
            max_retries=3,
        )
        executor = DAGTaskExecutor(
            worker_dispatcher=worker.execute_task,
            event_sink=self._emit_telemetry,
            max_parallel_tasks=self.models.level3_swarm_count,
        )
        summary = executor.execute_plan_sync(
            plan,
            initial_context={
                "reconstructed_prompt": reconstructed_prompt,
                "research_context": research_context,
            },
        )
        self._emit_telemetry(
            "TASK_GRAPH_COMPLETE",
            {
                "execution_mode": summary.execution_mode,
                "plan_id": summary.plan_id,
                "parallel_batch_count": summary.parallel_batch_count,
                "worker_retry_count": summary.worker_retry_count,
                "task_failure_count": summary.task_failure_count,
                "level2_swarm_count": self.models.level2_swarm_count,
                "level3_swarm_count": self.models.level3_swarm_count,
            },
        )
        return summary

    def _synthesise_task_graph_output(
        self,
        *,
        plan: OrchestrationPlan,
        summary: TaskGraphExecutionSummary,
        reconstructed_prompt: str,
        research_context: str,
        context_block: str | None,
    ) -> str:
        task_results = json.dumps(
            {
                task.task_id: {
                    "description": task.description,
                    "result": task.result,
                }
                for task in summary.completed_tasks
            },
            indent=2,
            sort_keys=True,
            default=str,
        )

        description = (
            "Synthesize the completed task-graph outputs into the final deliverable.\n\n"
            f"Plan ID: {plan.plan_id}\n\n"
            f"Reconstructed Prompt:\n{reconstructed_prompt}\n\n"
            f"Research Context:\n{research_context}\n\n"
            f"Runtime Context:\n{context_block or 'No additional runtime context supplied.'}\n\n"
            f"Completed Task Results:\n{task_results}\n\n"
            "Requirements:\n"
            "- Produce the final production-grade answer.\n"
            "- Preserve exact file paths and full file contents when code is required.\n"
            "- Do not introduce placeholders or TODO markers.\n"
        )

        def _runner(llm: LLM) -> str:
            return self._run_single_agent_task(
                llm=llm,
                role="Task Graph Synthesizer",
                goal="Combine validated task outputs into the final deliverable without losing fidelity.",
                backstory=(
                    "You are the orchestration-tier synthesizer. You assemble final output "
                    "from validated task results and preserve single-source-of-truth semantics."
                ),
                description=description,
                expected_output=(
                    "A complete deliverable set with exact file paths and full file contents "
                    "where code or scripts are required."
                ),
            )

        return self._run_stage_with_tier_fallback(
            stage_name="execution_synthesis",
            tier_name="orchestration",
            tier=self.models.orchestration,
            runner=_runner,
        )

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

        write_workspace_file(
            self.workspace, ".agent/tmp/reconstructed_prompt.md", result
        )
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
        write_workspace_file(
            self.workspace, ".agent/tmp/research-context.md", normalised
        )
        return normalised

    def execute(
        self,
        reconstructed_prompt: str,
        research_context: str,
        context_block: str | None = None,
    ) -> str:
        """
        Executes the main runtime using the hardened task-graph path first and
        falls back to the legacy hierarchical Crew when graph planning fails
        before any work has started.
        """
        try:
            plan = self._plan_execution_graph(
                source_prompt=self._extract_input_data(reconstructed_prompt),
                research_context=research_context,
                context_block=context_block,
            )
            summary = self._execute_task_graph(
                plan=plan,
                reconstructed_prompt=reconstructed_prompt,
                research_context=research_context,
                context_block=context_block,
            )
            result = self._synthesise_task_graph_output(
                plan=plan,
                summary=summary,
                reconstructed_prompt=reconstructed_prompt,
                research_context=research_context,
                context_block=context_block,
            )
            self._emit_telemetry(
                "EXECUTION_MODE_SELECTED",
                {
                    "execution_mode": "task_graph",
                    "plan_id": plan.plan_id,
                    "parallel_batch_count": summary.parallel_batch_count,
                    "worker_retry_count": summary.worker_retry_count,
                    "task_failure_count": summary.task_failure_count,
                },
            )
        except PlanningFailureError as error:
            self._emit_telemetry(
                "EXECUTION_MODE_FALLBACK",
                {
                    "from_mode": "task_graph",
                    "to_mode": "legacy_hierarchical",
                    "reason": str(error),
                },
            )
            result = self._execute_hierarchical_legacy(
                reconstructed_prompt=reconstructed_prompt,
                research_context=research_context,
                context_block=context_block,
            )
        except TaskGraphExecutionError as error:
            if error.started_execution:
                raise
            self._emit_telemetry(
                "EXECUTION_MODE_FALLBACK",
                {
                    "from_mode": "task_graph",
                    "to_mode": "legacy_hierarchical",
                    "reason": str(error),
                },
            )
            result = self._execute_hierarchical_legacy(
                reconstructed_prompt=reconstructed_prompt,
                research_context=research_context,
                context_block=context_block,
            )

        write_workspace_file(self.workspace, ".agent/tmp/final_output.md", result)
        return result

    def _execute_hierarchical_legacy(
        self,
        *,
        reconstructed_prompt: str,
        research_context: str,
        context_block: str | None,
    ) -> str:
        self._emit_telemetry(
            "EXECUTION_MODE_SELECTED",
            {
                "execution_mode": "legacy_hierarchical",
            },
        )

        def _build_crew(
            self_ref: "CrewAIThreeTierOrchestrator", *, use_fallback: bool
        ) -> str:
            orchestration_llm = (
                self_ref.models.orchestration.fallback
                if use_fallback
                else self_ref.models.orchestration.primary
            )
            level1_llm = (
                self_ref.models.level1.fallback
                if use_fallback
                else self_ref.models.level1.primary
            )
            level2_llm = (
                self_ref.models.level2.fallback
                if use_fallback
                else self_ref.models.level2.primary
            )
            level3_llm = (
                self_ref.models.level3.fallback
                if use_fallback
                else self_ref.models.level3.primary
            )

            manager = Agent(
                role="Orchestration Tier Manager/Router",
                goal="Plan, delegate, and validate completion using strict success-criteria enforcement.",
                backstory=(
                    "You are a CTO-level manager agent. You delegate to senior and worker agents, "
                    "enforce single-source-of-truth, and reject placeholder output."
                ),
                llm=orchestration_llm,
                verbose=self_ref.verbose,
                allow_delegation=True,
                reasoning=True,
                max_reasoning_attempts=3,
            )

            senior = Agent(
                role="Level 1 Senior/Analytical Agent",
                goal="Decompose objectives and produce an execution plan with strict acceptance criteria per task.",
                backstory="You are a senior systems architect. You translate requirements into executable work packages and guardrails.",
                llm=level1_llm,
                verbose=self_ref.verbose,
                allow_delegation=True,
                reasoning=True,
                max_reasoning_attempts=3,
            )

            coordinator = Agent(
                role="Level 2 Coordination/QA Agent",
                goal="Validate execution plans, coordinate worker retries, and enforce acceptance criteria.",
                backstory=(
                    "You are the L2 coordination tier. You sit between planning and execution, "
                    "translate work packages for leaf workers, and reject incomplete artefacts."
                ),
                llm=level2_llm,
                verbose=self_ref.verbose,
                allow_delegation=True,
                reasoning=True,
                max_reasoning_attempts=3,
            )

            worker_tools = self_ref._build_worker_tools()

            worker = Agent(
                role="Level 3 Execution/Worker Agent",
                goal="Implement atomic tasks with zero placeholders and explicit error handling.",
                backstory=(
                    "You are the L3 leaf worker tier that produces complete, executable artefacts "
                    "with no TODOs and no simulated logic.\n\n"
                    f"{self_ref._worker_tooling_manifest()}"
                ),
                llm=level3_llm,
                verbose=self_ref.verbose,
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
                agents=[senior, coordinator, worker],
                tasks=[kickoff_task],
                process=Process.hierarchical,
                manager_agent=manager,
                memory=True,
                planning=False,
                verbose=self_ref.verbose,
                cache=True,
            )
            return self_ref._extract_final_answer(str(crew.kickoff()))

        def _primary_runner(llm: LLM) -> str:
            return _build_crew(self, use_fallback=False)

        def _fallback_runner(llm: LLM) -> str:
            return _build_crew(self, use_fallback=True)

        from engine.llm_config import ModelTier as _MT

        synthetic_tier = _MT(
            primary=self.models.orchestration.primary,
            fallback=self.models.orchestration.fallback,
        )

        result = self._run_stage_with_tier_fallback(
            stage_name="execution_hierarchical",
            tier_name="orchestration",
            tier=synthetic_tier,
            runner=lambda llm: (
                _primary_runner(llm)
                if llm is synthetic_tier.primary
                else _fallback_runner(llm)
            ),
        )
        return result
