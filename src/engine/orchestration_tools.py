from __future__ import annotations

import os
import subprocess
import sys
import time
import json
from pathlib import Path
from typing import Any, Literal, Mapping, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from view.a2ui_protocol import (
    ACK_ACTION_ID,
    acknowledgement_visibility_path,
    apply_acknowledgement_update,
)


def _default_test_command(project_root: Path) -> list[str]:
    makefile = project_root / "Makefile"
    if makefile.exists() and "test-pytest" in makefile.read_text(encoding="utf-8"):
        return ["make", "test-pytest"]
    return [sys.executable, "-m", "pytest", "tests"]


def _default_benchmark_command(project_root: Path) -> list[str]:
    return [sys.executable, "benchmarks/run_benchmark.py"]


def _run_command(
    *,
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    start = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    elapsed = time.perf_counter() - start

    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "duration_seconds": round(elapsed, 3),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "success": completed.returncode == 0,
    }


def run_tests(
    *,
    project_root: Path,
    command: list[str] | None = None,
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    return _run_command(
        command=command or _default_test_command(project_root),
        cwd=project_root,
        timeout_seconds=timeout_seconds,
    )


def run_benchmarks(
    *,
    project_root: Path,
    command: list[str] | None = None,
    timeout_seconds: int = 3600,
) -> dict[str, Any]:
    return _run_command(
        command=command or _default_benchmark_command(project_root),
        cwd=project_root,
        timeout_seconds=timeout_seconds,
    )


def complete_task_signal(
    *,
    summary: str,
    status: Literal["success", "partial", "blocked"] = "success",
) -> dict[str, Any]:
    """
    Canonical completion signal used by agent loops.

    `success` describes whether the call succeeded, while `should_continue`
    explicitly controls loop termination.
    """
    return {
        "success": True,
        "status": status,
        "summary": summary.strip(),
        "should_continue": False,
    }


_RUNTIME_KEYS = (
    "PRIMARY_LLM",
    "ORCHESTRATION_MODEL",
    "L1_MODEL",
    "L2_MODEL",
    "L3_MODEL",
    "L2_AGENT_SWARMS",
    "L3_AGENT_SWARMS",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OLLAMA_BASE_URL",
    "ANTIGRAVITY_WORKSPACE_DIR",
    "ANTIGRAVITY_WORKSPACE_ROOT",
    "CREWAI_STORAGE_DIR",
)

_MUTABLE_ENV_KEYS = {
    "PRIMARY_LLM",
    "ORCHESTRATION_MODEL",
    "L1_MODEL",
    "L2_MODEL",
    "L3_MODEL",
    "L2_AGENT_SWARMS",
    "L3_AGENT_SWARMS",
    "ANTIGRAVITY_WORKSPACE_DIR",
    "ANTIGRAVITY_WORKSPACE_ROOT",
    "CREWAI_STORAGE_DIR",
    "ANTIGRAVITY_STRICT_PROVIDER_VALIDATION",
    "ANTIGRAVITY_MAX_PROVIDER_4XX",
    "ANTIGRAVITY_FAIL_ON_RESEARCH_EMPTY",
    "OLLAMA_BASE_URL",
}


def read_runtime_configuration(
    *,
    project_root: Path,
    workspace: Path,
    include_system_env: bool = False,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    project_root = project_root.resolve()
    workspace_env = workspace / ".env"
    project_env = project_root / ".env"

    env_status = {
        key: {
            "present": key in os.environ,
            "is_set_nonempty": bool(os.environ.get(key)),
        }
        for key in _RUNTIME_KEYS
    }

    payload: dict[str, Any] = {
        "project_root": str(project_root),
        "workspace": str(workspace),
        "workspace_env_path": str(workspace_env),
        "project_env_path": str(project_env),
        "workspace_env_exists": workspace_env.exists(),
        "project_env_exists": project_env.exists(),
        "env_status": env_status,
    }
    if include_system_env:
        payload["system_env"] = {
            key: os.environ.get(key)
            for key in _RUNTIME_KEYS
            if os.environ.get(key) is not None
        }
    return payload


def _parse_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        data[key.strip()] = value.strip()
    return data


def _write_dotenv(path: Path, payload: Mapping[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in sorted(payload.items())]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_runtime_configuration(
    *,
    workspace: Path,
    updates: Mapping[str, str],
) -> dict[str, Any]:
    for key in updates:
        if key not in _MUTABLE_ENV_KEYS:
            raise ValueError(
                f"Key '{key}' is not mutable through runtime config tooling."
            )

    env_file = workspace.resolve() / ".env"
    current = _parse_dotenv(env_file)
    merged = dict(current)
    merged.update({key: str(value) for key, value in updates.items()})
    _write_dotenv(env_file, merged)

    return {
        "workspace_env_path": str(env_file),
        "updated_keys": sorted(updates.keys()),
        "total_keys": len(merged),
    }


def acknowledge_ui_action(
    *,
    workspace: Path,
    action_id: str = ACK_ACTION_ID,
    acknowledged: bool = True,
) -> dict[str, Any]:
    """
    Primitive shared-state mutation for UI acknowledgements.
    The same pointer path is used by A2UI payload generation and agent tools.
    """
    workspace = workspace.resolve()
    state_file = workspace / ".agent" / "memory" / "a2ui_state.json"
    if state_file.exists():
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    else:
        payload = {}

    data_model = payload.get("data_model", {})
    if not isinstance(data_model, dict):
        data_model = {}

    updated_data_model = apply_acknowledgement_update(
        data_model,
        action_id=action_id,
        acknowledged=acknowledged,
    )
    pointer = acknowledgement_visibility_path(action_id)
    payload["data_model"] = updated_data_model
    payload["last_action"] = {
        "action_id": action_id,
        "acknowledged": acknowledged,
        "shared_state_path": pointer,
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "workspace": str(workspace),
        "action_id": action_id,
        "acknowledged": acknowledged,
        "shared_state_path": pointer,
        "visibility": bool(updated_data_model.get(pointer)),
        "state_file": str(state_file),
    }


def submit_objective(
    *,
    prompt: str,
    workspace: Path,
    strict_provider_validation: bool = True,
    max_provider_4xx: int = 50,
    fail_on_research_empty: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    """Programmatic equivalent of CLI objective submission."""
    from engine.orchestration_api import OrchestrationRunConfig, run_orchestration

    cfg = OrchestrationRunConfig(
        prompt=prompt,
        workspace=workspace.resolve(),
        strict_provider_validation=strict_provider_validation,
        max_provider_4xx=max_provider_4xx,
        fail_on_research_empty=fail_on_research_empty,
        verbose=verbose,
        caller="internal",
    )
    result = run_orchestration(cfg)
    return {
        "success": result.success,
        "workspace": str(result.workspace),
        "run_id": result.run_id,
        "completion_status": result.completion_status,
        "completion_summary": result.completion_summary,
        "final_output_path": str(result.final_output_path),
        "reconstructed_prompt_path": str(result.reconstructed_prompt_path),
        "research_context_path": str(result.research_context_path),
        "execution_log_path": str(result.execution_log_path),
        "failed_stage": result.failed_stage,
        "error": result.error,
    }


class _RunTestsArgs(BaseModel):
    timeout_seconds: int = Field(default=1800, description="Command timeout in seconds.")


class _RunBenchmarksArgs(BaseModel):
    timeout_seconds: int = Field(default=3600, description="Command timeout in seconds.")


class _ReadConfigArgs(BaseModel):
    include_system_env: bool = Field(
        default=False,
        description=(
            "When True, augments the configuration snapshot with a subset of "
            "system environment variables relevant to runtime behaviour."
        ),
    )


class _UpdateConfigArgs(BaseModel):
    updates: dict[str, str] = Field(
        ...,
        description="Environment key/value updates for workspace .env.",
    )


class _CompleteTaskArgs(BaseModel):
    summary: str = Field(..., description="Summary of what was completed.")
    status: Literal["success", "partial", "blocked"] = Field(
        default="success",
        description="Completion status for the current objective.",
    )


class _AcknowledgeUIActionArgs(BaseModel):
    action_id: str = Field(
        default=ACK_ACTION_ID,
        description="A2UI action identifier to acknowledge.",
    )
    acknowledged: bool = Field(
        default=True,
        description="Whether the action has been acknowledged.",
    )


class _SubmitObjectiveArgs(BaseModel):
    prompt: str = Field(..., description="Objective/prompt to submit for orchestration.")
    strict_provider_validation: bool = Field(
        default=True,
        description="Fail fast when provider runtime configuration is invalid.",
    )
    max_provider_4xx: int = Field(
        default=50,
        description="Maximum tolerated provider HTTP 4xx events before abort.",
    )
    fail_on_research_empty: bool = Field(
        default=False,
        description="Fail if research context has fewer than two citations for non-trivial prompts.",
    )
    verbose: bool = Field(
        default=False,
        description="Enable verbose model execution output.",
    )


class RunTestsTool(BaseTool):
    name: str = "run_tests"
    description: str = (
        "Run the repository's automated tests and return machine-readable output. "
        "This tool only executes test commands; it does not select models or alter LLM behaviour."
    )
    args_schema: Type[BaseModel] = _RunTestsArgs
    project_root: str = Field(..., description="Absolute project root path.")

    def _run(self, timeout_seconds: int = 1800) -> str:
        result = run_tests(
            project_root=Path(self.project_root),
            timeout_seconds=timeout_seconds,
        )
        return str(result)


class RunBenchmarksTool(BaseTool):
    name: str = "run_benchmarks"
    description: str = (
        "Run the benchmark harness and return machine-readable output. "
        "This tool only executes benchmark commands; it does not select models or alter LLM behaviour."
    )
    args_schema: Type[BaseModel] = _RunBenchmarksArgs
    project_root: str = Field(..., description="Absolute project root path.")

    def _run(self, timeout_seconds: int = 3600) -> str:
        result = run_benchmarks(
            project_root=Path(self.project_root),
            timeout_seconds=timeout_seconds,
        )
        return str(result)


class CompleteTaskTool(BaseTool):
    name: str = "complete_task"
    description: str = (
        "Explicitly signal task completion for the current objective. "
        "Returns should_continue=false so loop controllers can stop deterministically."
    )
    args_schema: Type[BaseModel] = _CompleteTaskArgs

    def _run(
        self,
        summary: str,
        status: Literal["success", "partial", "blocked"] = "success",
    ) -> str:
        return str(complete_task_signal(summary=summary, status=status))


class ReadRuntimeConfigTool(BaseTool):
    name: str = "read_runtime_configuration"
    description: str = (
        "Inspect effective runtime configuration: key presence and related env/.env paths. "
        "This tool only reports configuration for the active workspace; "
        "it does not modify or interpret model policy."
    )
    args_schema: Type[BaseModel] = _ReadConfigArgs
    project_root: str = Field(..., description="Absolute project root path.")
    workspace: str = Field(..., description="Absolute active workspace path.")

    def _run(self, include_system_env: bool = False) -> str:
        result = read_runtime_configuration(
            project_root=Path(self.project_root),
            workspace=Path(self.workspace),
            include_system_env=include_system_env,
        )
        return str(result)


class UpdateRuntimeConfigTool(BaseTool):
    name: str = "update_runtime_configuration"
    description: str = (
        "Update allowed runtime configuration keys in the active workspace .env file. "
        "This tool only edits environment variables; higher-level prompts decide how to use them."
    )
    args_schema: Type[BaseModel] = _UpdateConfigArgs
    workspace: str = Field(..., description="Absolute active workspace path.")

    def _run(self, updates: dict[str, str]) -> str:
        result = update_runtime_configuration(
            workspace=Path(self.workspace),
            updates=updates,
        )
        return str(result)


class AcknowledgeUIActionTool(BaseTool):
    name: str = "acknowledge_ui_action"
    description: str = (
        "Acknowledge an A2UI action by mutating shared state at the canonical pointer path. "
        "This keeps agent and UI acknowledgement behavior in parity."
    )
    args_schema: Type[BaseModel] = _AcknowledgeUIActionArgs
    workspace: str = Field(..., description="Absolute active workspace path.")

    def _run(self, action_id: str = ACK_ACTION_ID, acknowledged: bool = True) -> str:
        result = acknowledge_ui_action(
            workspace=Path(self.workspace),
            action_id=action_id,
            acknowledged=acknowledged,
        )
        return str(result)


class SubmitObjectiveTool(BaseTool):
    name: str = "submit_objective"
    description: str = (
        "Submit a new objective/prompt into the orchestration pipeline. "
        "This is the agent equivalent of the CLI --prompt submission path."
    )
    args_schema: Type[BaseModel] = _SubmitObjectiveArgs
    workspace: str = Field(..., description="Absolute active workspace path.")

    def _run(
        self,
        prompt: str,
        strict_provider_validation: bool = True,
        max_provider_4xx: int = 50,
        fail_on_research_empty: bool = False,
        verbose: bool = False,
    ) -> str:
        result = submit_objective(
            prompt=prompt,
            workspace=Path(self.workspace),
            strict_provider_validation=strict_provider_validation,
            max_provider_4xx=max_provider_4xx,
            fail_on_research_empty=fail_on_research_empty,
            verbose=verbose,
        )
        return str(result)
