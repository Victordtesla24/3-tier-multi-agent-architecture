import logging
import time
import json
import os
import re
import ast
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from engine.crew_orchestrator import CrewAIThreeTierOrchestrator
from engine.llm_config import classify_provider_error

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

    def __init__(
        self,
        workspace_dir: str,
        *,
        strict_provider_validation: bool = True,
        max_provider_4xx: int = 50,
        fail_on_research_empty: bool = False,
    ):
        self.workspace = workspace_dir
        self.state = "INIT"
        self.max_retries = 3
        self.strict_provider_validation = strict_provider_validation
        self.max_provider_4xx = max_provider_4xx
        self.fail_on_research_empty = fail_on_research_empty
        self.provider_4xx_count = 0
        self.run_id: str | None = None

        # Ensure observability path exists
        self.log_path = os.path.join(self.workspace, ".agent", "memory", "execution_log.json")
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w") as f:
                json.dump({"executions": []}, f)

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

    def execute_pipeline(self, raw_prompt: str) -> bool:
        self.run_id = str(uuid.uuid4())
        self.provider_4xx_count = 0
        httpx_logger = logging.getLogger("httpx")
        httpx_handler = _HTTPStatusCaptureHandler(self._record_httpx_status)
        httpx_logger.addHandler(httpx_handler)
        logger.info("Transitioning to state: PROMPT_RECONSTRUCTION")
        self.state = "PROMPT_RECONSTRUCTION"
        try:
            self._structured_log("STATE_TRANSITION", {"raw_prompt_length": len(raw_prompt)})

            orchestrator = CrewAIThreeTierOrchestrator(
                workspace_dir=self.workspace,
                verbose=True,
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

            logger.info("Transitioning to state: RESEARCH")
            self.state = "RESEARCH"
            self._structured_log("STATE_TRANSITION", {"status": "started"})
            research_context = self._execute_with_backoff(
                orchestrator.run_research,
                reconstructed,
                stage_name="research",
            )
            self._enforce_provider_error_budget("research")
            self._enforce_research_quality(raw_prompt, research_context)

            logger.info("Transitioning to state: ORCHESTRATION_L1")
            self.state = "ORCHESTRATION_L1"
            self._structured_log("STATE_TRANSITION", {"status": "delegating_to_crewai"})
            final_output = self._execute_with_backoff(
                orchestrator.execute,
                reconstructed,
                research_context,
                stage_name="execution_hierarchical",
            )
            self._enforce_provider_error_budget("execution_hierarchical")

            logger.info("Transitioning to state: VERIFICATION")
            self.state = "VERIFICATION"
            self._structured_log("STATE_TRANSITION", {"status": "validating_results"})

            results: Dict[str, Any] = {"final_output": final_output}

            if self._run_verification_scoring(results):
                logger.info("Pipeline successful. Verification Passed.")
                self._structured_log("PIPELINE_COMPLETE", {"success": True})
                return True

            logger.error("Pipeline failed verification constraints.")
            self._structured_log("PIPELINE_COMPLETE", {"success": False})
            return False
        finally:
            httpx_logger.removeHandler(httpx_handler)

    def _run_verification_scoring(self, results: dict) -> bool:
        """
        Production-grade verification gating.
        Executes AST structural parsing and strict lexical constraint checking.
        """
        output = str(results.get("final_output", ""))

        banned_patterns = [
            (r"(?im)^\s*(#|//)\s*TODO\b", "TODO comment marker"),
            (r"(?im)^\s*TODO\b", "TODO marker"),
            (r"(?im)\bTBD\b", "TBD marker"),
            (r"(?im)\bFIXME\b", "FIXME marker"),
            (r"(?im)\braise\s+NotImplementedError\b", "NotImplementedError stub"),
            (r"(?im)^\s*pass\s*(#.*)?$", "pass-only implementation"),
            (r"(?im)<\s*placeholder\s*>", "<placeholder> token"),
            (r"(?im)\{\{\s*.*placeholder.*\}\}", "{{placeholder}} token"),
        ]

        for pattern, marker_name in banned_patterns:
            if re.search(pattern, output):
                logger.error(
                    f"Verification failed: detected banned lexical marker '{marker_name}'."
                )
                return False

        # Dynamic AST Analysis for Python code blocks
        python_blocks = re.findall(r"```python\n(.*?)\n```", output, re.DOTALL)
        for code in python_blocks:
            try:
                parsed = ast.parse(code)
                for node in ast.walk(parsed):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                            logger.error("Verification failed: AST detected empty implementation (pass).")
                            return False
            except SyntaxError as e:
                logger.error(f"Verification failed: AST SyntaxError in generated code - {e}")
                return False

        return True
