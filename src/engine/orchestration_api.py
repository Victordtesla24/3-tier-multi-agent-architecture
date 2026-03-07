from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from engine.llm_config import EnvConfigError, load_workspace_env, validate_provider_runtime_env
from engine.state_machine import OrchestrationStateMachine


OrchestrationCaller = Literal["cli", "mcp", "chat", "internal"]
CompletionStatus = Literal["pending", "success", "partial", "blocked"]


@dataclass(frozen=True)
class OrchestrationRunConfig:
    prompt: str
    workspace: Path
    strict_provider_validation: bool = True
    max_provider_4xx: int = 50
    fail_on_research_empty: bool = False
    verbose: bool = False
    caller: OrchestrationCaller = "internal"


@dataclass(frozen=True)
class OrchestrationRunResult:
    success: bool
    prompt: str
    workspace: Path
    run_id: str | None
    execution_log_path: Path
    final_output_path: Path
    reconstructed_prompt_path: Path
    research_context_path: Path
    provider_4xx_count: int
    strict_provider_validation: bool
    max_provider_4xx: int
    fail_on_research_empty: bool
    caller: OrchestrationCaller
    completion_status: CompletionStatus
    completion_summary: str
    failed_stage: str | None
    execution_mode: str = "legacy_hierarchical"
    plan_id: str | None = None
    task_count: int = 0
    parallel_batch_count: int = 0
    worker_retry_count: int = 0
    task_failure_count: int = 0
    stage_progress: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None
    extra_metadata: Mapping[str, Any] = field(default_factory=dict)


def _project_root() -> Path:
    # src/engine/ → project root
    return Path(__file__).parent.parent.parent.resolve()


def run_orchestration(config: OrchestrationRunConfig) -> OrchestrationRunResult:
    """
    Canonical programmatic entrypoint for a single 3-tier pipeline run.

    This mirrors the CLI semantics but performs no printing or CLI-specific
    side effects, returning a structured result instead.
    """
    workspace = config.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    project_root = _project_root()

    # Pre-flight provider validation to fail fast on misconfiguration.
    if config.strict_provider_validation:
        try:
            load_workspace_env(workspace, project_root=project_root)
            validate_provider_runtime_env(strict=True)
        except EnvConfigError as exc:
            tmp_dir = workspace / ".agent" / "tmp"
            memory_dir = workspace / ".agent" / "memory"
            return OrchestrationRunResult(
                success=False,
                prompt=config.prompt,
                workspace=workspace,
                run_id=None,
                execution_log_path=memory_dir / "execution_log.json",
                final_output_path=tmp_dir / "final_output.md",
                reconstructed_prompt_path=tmp_dir / "reconstructed_prompt.md",
                research_context_path=tmp_dir / "research-context.md",
                provider_4xx_count=0,
                strict_provider_validation=config.strict_provider_validation,
                max_provider_4xx=config.max_provider_4xx,
                fail_on_research_empty=config.fail_on_research_empty,
                caller=config.caller,
                completion_status="blocked",
                completion_summary="Provider runtime validation failed before pipeline execution.",
                failed_stage="INIT",
                execution_mode="legacy_hierarchical",
                plan_id=None,
                task_count=0,
                parallel_batch_count=0,
                worker_retry_count=0,
                task_failure_count=0,
                stage_progress={},
                error=str(exc),
                extra_metadata={},
            )

    # Execute the state machine pipeline and collect metadata.
    engine = OrchestrationStateMachine(
        workspace_dir=str(workspace),
        verbose=config.verbose,
        strict_provider_validation=config.strict_provider_validation,
        max_provider_4xx=config.max_provider_4xx,
        fail_on_research_empty=config.fail_on_research_empty,
    )

    try:
        success, metadata = engine.execute_pipeline_with_metadata(raw_prompt=config.prompt)
    except Exception as exc:  # pragma: no cover - defensive
        tmp_dir = workspace / ".agent" / "tmp"
        memory_dir = workspace / ".agent" / "memory"
        completion_snapshot = engine.get_completion_snapshot()
        return OrchestrationRunResult(
            success=False,
            prompt=config.prompt,
            workspace=workspace,
            run_id=getattr(engine, "run_id", None),
            execution_log_path=memory_dir / "execution_log.json",
            final_output_path=tmp_dir / "final_output.md",
            reconstructed_prompt_path=tmp_dir / "reconstructed_prompt.md",
            research_context_path=tmp_dir / "research-context.md",
            provider_4xx_count=getattr(engine, "provider_4xx_count", 0),
            strict_provider_validation=config.strict_provider_validation,
            max_provider_4xx=config.max_provider_4xx,
            fail_on_research_empty=config.fail_on_research_empty,
            caller=config.caller,
            completion_status=completion_snapshot.get("completion_status", "blocked"),
            completion_summary=completion_snapshot.get(
                "completion_summary",
                "Pipeline raised an exception before completion metadata was finalised.",
            ),
            failed_stage=completion_snapshot.get("failed_stage"),
            execution_mode=str(completion_snapshot.get("execution_mode", "legacy_hierarchical")),
            plan_id=completion_snapshot.get("plan_id"),
            task_count=int(completion_snapshot.get("task_count", 0) or 0),
            parallel_batch_count=int(completion_snapshot.get("parallel_batch_count", 0) or 0),
            worker_retry_count=int(completion_snapshot.get("worker_retry_count", 0) or 0),
            task_failure_count=int(completion_snapshot.get("task_failure_count", 0) or 0),
            stage_progress=completion_snapshot.get("stage_progress", {}),
            error=str(exc),
            extra_metadata={
                k: v
                for k, v in completion_snapshot.items()
                if k not in {
                    "completion_status",
                    "completion_summary",
                    "failed_stage",
                    "execution_mode",
                    "plan_id",
                    "task_count",
                    "parallel_batch_count",
                    "worker_retry_count",
                    "task_failure_count",
                    "stage_progress",
                }
            },
        )

    tmp_dir = workspace / ".agent" / "tmp"
    memory_dir = workspace / ".agent" / "memory"

    return OrchestrationRunResult(
        success=success,
        prompt=config.prompt,
        workspace=workspace,
        run_id=str(metadata.get("run_id") or getattr(engine, "run_id", None)),
        execution_log_path=Path(metadata.get("execution_log_path", memory_dir / "execution_log.json")),
        final_output_path=Path(metadata.get("final_output_path", tmp_dir / "final_output.md")),
        reconstructed_prompt_path=Path(
            metadata.get("reconstructed_prompt_path", tmp_dir / "reconstructed_prompt.md")
        ),
        research_context_path=Path(
            metadata.get("research_context_path", tmp_dir / "research-context.md")
        ),
        provider_4xx_count=int(metadata.get("provider_4xx_count", getattr(engine, "provider_4xx_count", 0))),
        strict_provider_validation=config.strict_provider_validation,
        max_provider_4xx=config.max_provider_4xx,
        fail_on_research_empty=config.fail_on_research_empty,
        caller=config.caller,
        completion_status=metadata.get("completion_status", "pending"),
        completion_summary=metadata.get("completion_summary", "No completion summary available."),
        failed_stage=metadata.get("failed_stage"),
        execution_mode=str(metadata.get("execution_mode", "legacy_hierarchical")),
        plan_id=metadata.get("plan_id"),
        task_count=int(metadata.get("task_count", 0) or 0),
        parallel_batch_count=int(metadata.get("parallel_batch_count", 0) or 0),
        worker_retry_count=int(metadata.get("worker_retry_count", 0) or 0),
        task_failure_count=int(metadata.get("task_failure_count", 0) or 0),
        stage_progress=metadata.get("stage_progress", {}),
        error=None,
        extra_metadata={k: v for k, v in metadata.items() if k not in {
            "run_id",
            "execution_log_path",
            "final_output_path",
            "reconstructed_prompt_path",
            "research_context_path",
            "provider_4xx_count",
            "completion_status",
            "completion_summary",
            "failed_stage",
            "execution_mode",
            "plan_id",
            "task_count",
            "parallel_batch_count",
            "worker_retry_count",
            "task_failure_count",
            "stage_progress",
        }},
    )


@dataclass(frozen=True)
class SubmitPromptRequest:
    prompt: str
    workspace: Path | None = None
    strict_provider_validation: bool = True
    max_provider_4xx: int = 50
    fail_on_research_empty: bool = False
    verbose: bool = False
    caller: OrchestrationCaller = "internal"
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class SubmitPromptResponse:
    success: bool
    prompt: str
    workspace: Path
    run_id: str | None
    final_output_path: Path
    research_context_path: Path
    reconstructed_prompt_path: Path
    execution_log_path: Path
    provider_4xx_count: int
    completion_status: CompletionStatus
    completion_summary: str
    failed_stage: str | None
    execution_mode: str = "legacy_hierarchical"
    plan_id: str | None = None
    task_count: int = 0
    parallel_batch_count: int = 0
    worker_retry_count: int = 0
    task_failure_count: int = 0
    stage_progress: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _default_workspace() -> Path:
    root = _project_root()
    base = Path(os.environ.get("ANTIGRAVITY_WORKSPACE_ROOT", root / "workspaces"))  # type: ignore[name-defined]
    return (base / "api-default").resolve()


def submit_prompt(request: SubmitPromptRequest) -> SubmitPromptResponse:
    workspace = request.workspace or _default_workspace()
    config = OrchestrationRunConfig(
        prompt=request.prompt,
        workspace=workspace,
        strict_provider_validation=request.strict_provider_validation,
        max_provider_4xx=request.max_provider_4xx,
        fail_on_research_empty=request.fail_on_research_empty,
        verbose=request.verbose,
        caller=request.caller,
    )
    result = run_orchestration(config)

    metadata: dict[str, Any] = {
        "caller": request.caller,
    }
    metadata.update(dict(result.extra_metadata))
    if request.metadata:
        metadata.update(request.metadata)

    return SubmitPromptResponse(
        success=result.success,
        prompt=result.prompt,
        workspace=result.workspace,
        run_id=result.run_id,
        final_output_path=result.final_output_path,
        research_context_path=result.research_context_path,
        reconstructed_prompt_path=result.reconstructed_prompt_path,
        execution_log_path=result.execution_log_path,
        provider_4xx_count=result.provider_4xx_count,
        completion_status=result.completion_status,
        completion_summary=result.completion_summary,
        failed_stage=result.failed_stage,
        execution_mode=result.execution_mode,
        plan_id=result.plan_id,
        task_count=result.task_count,
        parallel_batch_count=result.parallel_batch_count,
        worker_retry_count=result.worker_retry_count,
        task_failure_count=result.task_failure_count,
        stage_progress=result.stage_progress,
        error=result.error,
        metadata=metadata,
    )


def run_objective(
    objective: str,
    *,
    workspace: Path | None = None,
    strict_provider_validation: bool = True,
    max_provider_4xx: int = 50,
    fail_on_research_empty: bool = False,
    verbose: bool = False,
    caller: OrchestrationCaller = "internal",
) -> SubmitPromptResponse:
    """
    Thin alias for submit_prompt with a different primary parameter name.
    """
    request = SubmitPromptRequest(
        prompt=objective,
        workspace=workspace,
        strict_provider_validation=strict_provider_validation,
        max_provider_4xx=max_provider_4xx,
        fail_on_research_empty=fail_on_research_empty,
        verbose=verbose,
        caller=caller,
    )
    return submit_prompt(request)
