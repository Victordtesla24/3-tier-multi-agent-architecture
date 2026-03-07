import logging
import time
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Tuple

from engine.context_builder import build_orchestration_context_block
from engine.continuous_learning import apply_architecture_upgrade, generate_improvement_proposal
from engine.crew_orchestrator import CrewAIThreeTierOrchestrator
from engine.exceptions import PipelineError, ResearchEmptyError, VerificationFailedError
from engine.llm_config import classify_provider_error
from engine.verification_agent import VerificationAgent

logger = logging.getLogger("AntigravityEngine")


class _HTTPStatusCaptureHandler(logging.Handler):
    """Captures HTTP status codes from httpx log records."""

    _STATUS_PATTERN = re.compile(r"HTTP/1\.1\s+(\d{3})")

    def __init__(self, callback):
        super().__init__(level=logging.INFO)
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            match = self._STATUS_PATTERN.search(message)
            if match:
                self._callback(int(match.group(1)), message)
        except Exception:
            return


class OrchestrationStateMachine:
    """
    Programmatic State Machine for the 3-Tier Multi-Agent Architecture.

    This implementation replaces prior stub behaviour with a CrewAI-backed pipeline:
      - Prompt reconstruction via CrewAI (Level 1 tier)
      - Research via CrewAI (Level 1 tier)
      - Hierarchical execution via CrewAI (Orchestration tier + L1 + L2)
      - Verification gate that rejects placeholder / simulated output
    """

    _PIPELINE_STAGES = (
        "PROMPT_RECONSTRUCTION",
        "RESEARCH",
        "ORCHESTRATION_L1",
        "VERIFICATION",
        "CONTINUOUS_LEARNING",
    )

    def __init__(
        self,
        workspace_dir: str,
        *,
        verbose: bool = False,
        strict_provider_validation: bool = True,
        max_provider_4xx: int = 50,
        fail_on_research_empty: bool = False,
    ):
        self.workspace = workspace_dir
        self.state = "INIT"
        self.max_retries = 3
        self.verbose = verbose
        self.strict_provider_validation = strict_provider_validation
        self.max_provider_4xx = max_provider_4xx
        self.fail_on_research_empty = fail_on_research_empty
        self.provider_4xx_count = 0
        self.run_id: str | None = None
        self.completion_status = "pending"
        self.completion_summary = "Execution has not started."
        self.failed_stage: str | None = None
        self.stage_progress: Dict[str, Dict[str, Any]] = {}
        self._stage_started_monotonic: Dict[str, float] = {}
        self._last_verification_error: VerificationFailedError | None = None
        self.execution_mode = "legacy_hierarchical"
        self.plan_id: str | None = None
        self.task_count = 0
        self.parallel_batch_count = 0
        self.worker_retry_count = 0
        self.task_failure_count = 0
        self._reset_execution_tracking()

        # Ensure observability path exists
        self.log_path = os.path.join(self.workspace, ".agent", "memory", "execution_log.json")
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w") as f:
                json.dump({"executions": []}, f)

    def _reset_execution_tracking(self) -> None:
        self.completion_status = "pending"
        self.completion_summary = "Execution has not started."
        self.failed_stage = None
        self._stage_started_monotonic = {}
        self._last_verification_error = None
        self.execution_mode = "legacy_hierarchical"
        self.plan_id = None
        self.task_count = 0
        self.parallel_batch_count = 0
        self.worker_retry_count = 0
        self.task_failure_count = 0
        self.stage_progress = {
            stage: {
                "status": "pending",
                "notes": None,
                "started_at": None,
                "finished_at": None,
                "duration_s": None,
            }
            for stage in self._PIPELINE_STAGES
        }

    @staticmethod
    def _current_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _mark_stage(self, stage: str, status: str, notes: str | None = None) -> None:
        if stage not in self.stage_progress:
            self.stage_progress[stage] = {
                "status": "pending",
                "notes": None,
                "started_at": None,
                "finished_at": None,
                "duration_s": None,
            }

        payload = self.stage_progress[stage]
        payload["status"] = status
        payload["notes"] = notes

        if status == "in_progress":
            payload["started_at"] = payload.get("started_at") or self._current_timestamp()
            payload["finished_at"] = None
            payload["duration_s"] = None
            self._stage_started_monotonic[stage] = time.monotonic()
        elif status in {"completed", "failed", "failed_non_blocking"}:
            finished_at = self._current_timestamp()
            payload["started_at"] = payload.get("started_at") or finished_at
            payload["finished_at"] = finished_at
            started_monotonic = self._stage_started_monotonic.pop(stage, None)
            if started_monotonic is not None:
                payload["duration_s"] = round(time.monotonic() - started_monotonic, 3)
            elif payload.get("duration_s") is None:
                payload["duration_s"] = 0.0

        if status == "failed":
            self.failed_stage = stage

    def get_completion_snapshot(self) -> Dict[str, Any]:
        completed_count = sum(
            1 for payload in self.stage_progress.values() if payload.get("status") == "completed"
        )
        stage_progress = {
            stage: {
                "status": payload.get("status"),
                "notes": payload.get("notes"),
                "started_at": payload.get("started_at"),
                "finished_at": payload.get("finished_at"),
                "duration_s": payload.get("duration_s"),
            }
            for stage, payload in self.stage_progress.items()
        }
        return {
            "completion_status": self.completion_status,
            "completion_summary": self.completion_summary,
            "failed_stage": self.failed_stage,
            "stage_progress": stage_progress,
            "completed_stage_count": completed_count,
            "total_stage_count": len(self.stage_progress),
            "can_resume": self.completion_status == "blocked",
            "execution_mode": self.execution_mode,
            "plan_id": self.plan_id,
            "task_count": self.task_count,
            "parallel_batch_count": self.parallel_batch_count,
            "worker_retry_count": self.worker_retry_count,
            "task_failure_count": self.task_failure_count,
        }

    def _structured_log(self, event_type: str, details: dict):
        """Appends structured JSON telemetry to the central memory file."""
        try:
            with open(self.log_path, "r+") as f:
                data = json.load(f)
                data["executions"].append(
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "run_id": self.run_id,
                        "state": self.state,
                        "event": event_type,
                        "details": details,
                    }
                )
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
        except Exception as e:
            logger.error(f"Failed to write structured log: {e}")

    def _execute_with_backoff(self, func, *args, stage_name: str = "unknown"):
        """Standard exponential backoff wrapper for API stability."""
        retries = 0
        last_error: Exception | None = None
        while retries < self.max_retries:
            try:
                return func(*args)
            except Exception as e:
                last_error = e
                classified = classify_provider_error(e)
                self._structured_log(
                    "PROVIDER_ATTEMPT",
                    {
                        "run_id": self.run_id,
                        "stage": stage_name,
                        "model": "unknown",
                        "provider": "unknown",
                        "attempt": retries + 1,
                        "request_id": None,
                        "http_status": classified.get("http_status"),
                        "error_type": classified.get("error_type"),
                        "error_code": classified.get("error_code"),
                        "retriable": classified.get("retriable", True),
                        "fallback_used": False,
                        "status": "failed",
                        "error": f"{type(e).__name__}: {e}",
                    },
                )
                if classified.get("http_status") is not None and 400 <= classified["http_status"] < 500:
                    self.provider_4xx_count += 1
                if not classified.get("retriable", True):
                    raise

                retries += 1
                sleep_time = 2 ** retries
                logger.warning(
                    f"Execution failed: {e}. Retrying in {sleep_time}s ({retries}/{self.max_retries})"
                )
                time.sleep(sleep_time)
        raise PipelineError(
            "Max retries exceeded during agent execution.",
            stage=stage_name,
            metadata={
                "attempts": retries,
                "max_retries": self.max_retries,
                "last_error_type": type(last_error).__name__ if last_error else None,
                "last_error": str(last_error) if last_error else None,
            },
        )

    def _record_orchestrator_event(self, event_type: str, details: dict) -> None:
        """Telemetry bridge for orchestrator-level events (fallback attempts/results)."""
        http_status = details.get("http_status")
        if isinstance(http_status, int) and 400 <= http_status < 500:
            self.provider_4xx_count += 1

        if event_type == "EXECUTION_PLAN_CREATED":
            self.execution_mode = str(details.get("execution_mode", "task_graph"))
            self.plan_id = str(details.get("plan_id")) if details.get("plan_id") else None
            self.task_count = int(details.get("task_count", 0))
        elif event_type == "TASK_GRAPH_BATCH_COMPLETED":
            self.parallel_batch_count = max(
                self.parallel_batch_count,
                int(details.get("batch_index", 0)),
            )
        elif event_type == "TASK_EXECUTION_RESULT":
            attempt_count = int(details.get("attempt_count", 0))
            self.worker_retry_count += max(attempt_count - 1, 0)
            if details.get("status") == "failed":
                self.task_failure_count += 1
        elif event_type == "TASK_GRAPH_COMPLETE":
            self.execution_mode = str(details.get("execution_mode", self.execution_mode))
            self.parallel_batch_count = int(
                details.get("parallel_batch_count", self.parallel_batch_count)
            )
            self.worker_retry_count = int(
                details.get("worker_retry_count", self.worker_retry_count)
            )
            self.task_failure_count = int(
                details.get("task_failure_count", self.task_failure_count)
            )
        elif event_type in {"EXECUTION_MODE_SELECTED", "EXECUTION_MODE_FALLBACK"}:
            self.execution_mode = str(
                details.get("to_mode")
                or details.get("execution_mode")
                or self.execution_mode
            )

        self._structured_log(event_type, details)

    def _record_httpx_status(self, http_status: int, message: str) -> None:
        if 400 <= http_status < 500:
            self.provider_4xx_count += 1
            self._structured_log(
                "PROVIDER_ATTEMPT",
                {
                    "run_id": self.run_id,
                    "stage": self.state,
                    "model": "unknown",
                    "provider": "httpx",
                    "attempt": 0,
                    "request_id": None,
                    "http_status": http_status,
                    "error_type": "HTTPStatus",
                    "error_code": None,
                    "retriable": http_status == 429,
                    "fallback_used": False,
                    "status": "failed",
                    "error": message,
                },
            )

    def _enforce_provider_error_budget(self, stage_name: str) -> None:
        if self.provider_4xx_count > self.max_provider_4xx:
            raise PipelineError(
                "Provider 4xx error budget exhausted "
                f"({self.provider_4xx_count}>{self.max_provider_4xx}) during stage '{stage_name}'.",
                stage=stage_name,
                metadata={"4xx_count": self.provider_4xx_count, "budget": self.max_provider_4xx},
            )

    @staticmethod
    def _extract_citation_urls(research_context: str) -> list[str]:
        return re.findall(r"https?://[^\s)]+", research_context)

    def _enforce_research_quality(self, raw_prompt: str, research_context: str) -> None:
        if not self.fail_on_research_empty:
            return
        if len(raw_prompt.split()) <= 1:
            # One-word smoke tests are exempt from citation gating.
            return
        citations = self._extract_citation_urls(research_context)
        if len(citations) < 2:
            raise ResearchEmptyError(
                "Research quality gate failed: expected at least 2 citation URLs, "
                f"found {len(citations)}."
            )

    def _build_pipeline_complete_details(
        self,
        *,
        success: bool,
        error: Exception | None = None,
    ) -> Dict[str, Any]:
        details: Dict[str, Any] = {
            "success": success,
            **self.get_completion_snapshot(),
        }
        if error is not None:
            details["error_type"] = type(error).__name__
            details["error"] = str(error)
            if isinstance(error, PipelineError) and error.metadata:
                details["error_metadata"] = dict(error.metadata)
        elif not success and self.failed_stage == "VERIFICATION":
            details["error_type"] = "VerificationFailedError"
            details["error"] = "Verification gate rejected final output."

        if self._last_verification_error is not None:
            details["verification"] = {
                "banned_markers": list(self._last_verification_error.banned_markers),
                "syntax_errors": list(self._last_verification_error.syntax_errors),
                "empty_implementations": self._last_verification_error.empty_implementations,
            }

        return details

    def _verify_results_or_raise(self, results: dict) -> None:
        output = str(results.get("final_output", ""))
        report = VerificationAgent().evaluate(output)
        if report.success:
            return
        raise VerificationFailedError(
            "Verification gate rejected final output.",
            banned_markers=report.banned_markers,
            syntax_errors=report.syntax_errors,
            empty_implementations=report.empty_implementations,
        )

    @staticmethod
    def _log_verification_failure(error: VerificationFailedError) -> None:
        if error.banned_markers:
            markers = ", ".join(error.banned_markers)
            logger.error(
                "Verification failed: detected banned lexical markers: %s",
                markers,
            )
        for syntax_error in error.syntax_errors:
            logger.error(
                "Verification failed: AST SyntaxError in generated code - %s",
                syntax_error,
            )
        if error.empty_implementations:
            logger.error("Verification failed: AST detected empty implementation (pass).")

    def execute_pipeline_with_metadata(self, raw_prompt: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Executes the pipeline and returns (success, metadata) for orchestration APIs.

        Metadata includes stable, machine-readable pointers to core artefacts so
        callers (CLI, MCP tools, UI backends) do not have to replicate path logic.
        """
        success = self.execute_pipeline(raw_prompt)

        workspace_path = Path(self.workspace).resolve()
        tmp_dir = workspace_path / ".agent" / "tmp"
        memory_dir = workspace_path / ".agent" / "memory"

        metadata: Dict[str, Any] = {
            "run_id": self.run_id,
            "execution_log_path": str(memory_dir / "execution_log.json"),
            "final_output_path": str(tmp_dir / "final_output.md"),
            "reconstructed_prompt_path": str(tmp_dir / "reconstructed_prompt.md"),
            "research_context_path": str(tmp_dir / "research-context.md"),
            "provider_4xx_count": self.provider_4xx_count,
            "execution_mode": self.execution_mode,
            "plan_id": self.plan_id,
            "task_count": self.task_count,
            "parallel_batch_count": self.parallel_batch_count,
            "worker_retry_count": self.worker_retry_count,
            "task_failure_count": self.task_failure_count,
        }
        metadata.update(self.get_completion_snapshot())
        return success, metadata

    def execute_pipeline(self, raw_prompt: str) -> bool:
        self.run_id = str(uuid.uuid4())
        self.provider_4xx_count = 0
        self._reset_execution_tracking()
        httpx_logger = logging.getLogger("httpx")
        httpx_handler = _HTTPStatusCaptureHandler(self._record_httpx_status)
        httpx_logger.addHandler(httpx_handler)
        logger.info("Transitioning to state: PROMPT_RECONSTRUCTION")
        self.state = "PROMPT_RECONSTRUCTION"
        self._mark_stage(self.state, "in_progress", "Reconstructing prompt from raw input.")
        try:
            self._structured_log("STATE_TRANSITION", {"raw_prompt_length": len(raw_prompt)})

            orchestrator = CrewAIThreeTierOrchestrator(
                workspace_dir=self.workspace,
                verbose=self.verbose,
                strict_provider_validation=self.strict_provider_validation,
                run_id=self.run_id,
                telemetry_hook=self._record_orchestrator_event,
            )

            reconstructed = self._execute_with_backoff(
                orchestrator.reconstruct_prompt,
                raw_prompt,
                stage_name="prompt_reconstruction",
            )
            self._enforce_provider_error_budget("prompt_reconstruction")
            self._mark_stage("PROMPT_RECONSTRUCTION", "completed", "Prompt reconstructed.")

            logger.info("Transitioning to state: RESEARCH")
            self.state = "RESEARCH"
            self._mark_stage(self.state, "in_progress", "Collecting research context.")
            self._structured_log("STATE_TRANSITION", {"status": "started"})
            research_context = self._execute_with_backoff(
                orchestrator.run_research,
                reconstructed,
                stage_name="research",
            )
            self._enforce_provider_error_budget("research")
            self._enforce_research_quality(raw_prompt, research_context)
            self._mark_stage("RESEARCH", "completed", "Research context collected.")

            logger.info("Transitioning to state: ORCHESTRATION_L1")
            self.state = "ORCHESTRATION_L1"
            self._mark_stage(
                self.state,
                "in_progress",
                "Delegating hardened task-graph execution with legacy fallback available.",
            )
            self._structured_log("STATE_TRANSITION", {"status": "delegating_to_crewai"})
            context_block = build_orchestration_context_block(
                workspace=Path(self.workspace),
                project_root=Path(__file__).resolve().parents[2],
                strict_provider_validation=self.strict_provider_validation,
                max_provider_4xx=self.max_provider_4xx,
                fail_on_research_empty=self.fail_on_research_empty,
            )
            final_output = self._execute_with_backoff(
                orchestrator.execute,
                reconstructed,
                research_context,
                context_block,
                stage_name="execution_hierarchical",
            )
            self._enforce_provider_error_budget("execution_hierarchical")
            self._mark_stage("ORCHESTRATION_L1", "completed", "Hierarchical execution finished.")

            logger.info("Transitioning to state: VERIFICATION")
            self.state = "VERIFICATION"
            self._mark_stage(self.state, "in_progress", "Running verification gate.")
            self._structured_log("STATE_TRANSITION", {"status": "validating_results"})

            results: Dict[str, Any] = {"final_output": final_output}

            if self._run_verification_scoring(results):
                self._mark_stage("VERIFICATION", "completed", "Verification gate passed.")
                logger.info("Pipeline successful. Verification Passed.")
                self.state = "CONTINUOUS_LEARNING"
                self._mark_stage(
                    self.state,
                    "in_progress",
                    "Generating and optionally applying continuous-learning proposal.",
                )
                # Best-effort continuous-learning stage; never blocks the run.
                try:
                    proposal = generate_improvement_proposal(Path(self.workspace))
                    apply_architecture_upgrade(
                        Path(self.workspace),
                        proposal,
                        approval_token=os.environ.get("ANTIGRAVITY_CL_APPROVAL", "").strip(),
                    )
                    self._mark_stage(
                        "CONTINUOUS_LEARNING",
                        "completed",
                        "Continuous-learning proposal processed.",
                    )
                except Exception as exc:
                    logger.warning("Continuous-learning stage failed: %s", exc)
                    self._mark_stage(
                        "CONTINUOUS_LEARNING",
                        "failed_non_blocking",
                        f"{type(exc).__name__}: {exc}",
                    )
                self.completion_status = "success"
                self.completion_summary = "Pipeline completed successfully and passed verification."
                self._structured_log(
                    "PIPELINE_COMPLETE",
                    self._build_pipeline_complete_details(success=True),
                )
                return True

            logger.error("Pipeline failed verification constraints.")
            self._mark_stage(
                "VERIFICATION",
                "failed",
                "Verification gate rejected final output.",
            )
            self.completion_status = "partial"
            self.completion_summary = (
                "Pipeline produced output, but verification failed and execution stopped."
            )
            self._structured_log(
                "PIPELINE_COMPLETE",
                self._build_pipeline_complete_details(
                    success=False,
                    error=self._last_verification_error,
                ),
            )
            return False
        except Exception as exc:
            active_stage = self.state or "UNKNOWN"
            self._mark_stage(active_stage, "failed", f"{type(exc).__name__}: {exc}")
            self.completion_status = "blocked"
            self.completion_summary = (
                f"Pipeline blocked in stage '{active_stage}' due to {type(exc).__name__}: {exc}"
            )
            self._structured_log(
                "PIPELINE_COMPLETE",
                self._build_pipeline_complete_details(success=False, error=exc),
            )
            raise
        finally:
            httpx_logger.removeHandler(httpx_handler)

    def _run_verification_scoring(self, results: dict) -> bool:
        """
        Production-grade verification gating.
        Executes AST structural parsing and strict lexical constraint checking.
        """
        self._last_verification_error = None
        try:
            self._verify_results_or_raise(results)
        except VerificationFailedError as error:
            self._last_verification_error = error
            self._log_verification_failure(error)
            return False
        return True
