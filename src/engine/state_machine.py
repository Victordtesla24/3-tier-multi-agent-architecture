import logging
import time
import json
import os
import re
import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from engine.crew_orchestrator import CrewAIThreeTierOrchestrator

logger = logging.getLogger("AntigravityEngine")


class OrchestrationStateMachine:
    """
    Programmatic State Machine for the 3-Tier Multi-Agent Architecture.

    This implementation replaces prior stub behaviour with a CrewAI-backed pipeline:
      - Prompt reconstruction via CrewAI (Level 1 tier)
      - Research via CrewAI (Level 1 tier)
      - Hierarchical execution via CrewAI (Orchestration tier + L1 + L2)
      - Verification gate that rejects placeholder / simulated output
    """

    def __init__(self, workspace_dir: str):
        self.workspace = workspace_dir
        self.state = "INIT"
        self.max_retries = 3

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

    def _execute_with_backoff(self, func, *args):
        """Standard exponential backoff wrapper for API stability."""
        retries = 0
        while retries < self.max_retries:
            try:
                return func(*args)
            except Exception as e:
                retries += 1
                sleep_time = 2 ** retries
                logger.warning(
                    f"Execution failed: {e}. Retrying in {sleep_time}s ({retries}/{self.max_retries})"
                )
                time.sleep(sleep_time)
        raise RuntimeError("Max retries exceeded during agent execution.")

    def _record_orchestrator_event(self, event_type: str, details: dict) -> None:
        """Telemetry bridge for orchestrator-level events (fallback attempts/results)."""
        self._structured_log(event_type, details)

    def execute_pipeline(self, raw_prompt: str) -> bool:
        logger.info("Transitioning to state: PROMPT_RECONSTRUCTION")
        self.state = "PROMPT_RECONSTRUCTION"
        self._structured_log("STATE_TRANSITION", {"raw_prompt_length": len(raw_prompt)})

        orchestrator = CrewAIThreeTierOrchestrator(
            workspace_dir=self.workspace,
            verbose=True,
            telemetry_hook=self._record_orchestrator_event,
        )

        reconstructed = self._execute_with_backoff(orchestrator.reconstruct_prompt, raw_prompt)

        logger.info("Transitioning to state: RESEARCH")
        self.state = "RESEARCH"
        self._structured_log("STATE_TRANSITION", {"status": "started"})
        research_context = self._execute_with_backoff(orchestrator.run_research, reconstructed)

        logger.info("Transitioning to state: ORCHESTRATION_L1")
        self.state = "ORCHESTRATION_L1"
        self._structured_log("STATE_TRANSITION", {"status": "delegating_to_crewai"})
        final_output = self._execute_with_backoff(orchestrator.execute, reconstructed, research_context)

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
