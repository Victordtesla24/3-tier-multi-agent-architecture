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
        self.stage_progress = {
            stage: {"status": "pending", "notes": None}
            for stage in self._PIPELINE_STAGES
        }

    def _mark_stage(self, stage: str, status: str, notes: str | None = None) -> None:
        if stage not in self.stage_progress:
            self.stage_progress[stage] = {"status": "pending", "notes": None}
        self.stage_progress[stage]["status"] = status
        self.stage_progress[stage]["notes"] = notes
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
        while retries < self.max_retries:
            try:
                return func(*args)
            except Exception as e:
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
        raise RuntimeError("Max retries exceeded during agent execution.")

    def _record_orchestrator_event(self, event_type: str, details: dict) -> None:
        """Telemetry bridge for orchestrator-level events (fallback attempts/results)."""
        http_status = details.get("http_status")
        if isinstance(http_status, int) and 400 <= http_status < 500:
            self.provider_4xx_count += 1
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
            raise RuntimeError(
                "Provider 4xx error budget exhausted "
                f"({self.provider_4xx_count}>{self.max_provider_4xx}) during stage '{stage_name}'."
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
            raise RuntimeError(
                "Research quality gate failed: fewer than 2 citation URLs were returned."
            )

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
                "Delegating hierarchical execution to crew manager and worker agents.",
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
                    {"success": True, **self.get_completion_snapshot()},
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
                {"success": False, **self.get_completion_snapshot()},
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
                {"success": False, **self.get_completion_snapshot()},
            )
            raise
        finally:
            httpx_logger.removeHandler(httpx_handler)

    def _run_verification_scoring(self, results: dict) -> bool:
        """
        Production-grade verification gating.
        Executes AST structural parsing and strict lexical constraint checking.
        """
        output = str(results.get("final_output", ""))

        agent = VerificationAgent()
        report = agent.evaluate(output)
        if report.success:
            return True

        for message in report.errors:
            logger.error(message)
        return False
