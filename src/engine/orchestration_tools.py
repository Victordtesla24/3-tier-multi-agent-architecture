from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Literal, Mapping, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


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
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_BASE_URL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "ANTIGRAVITY_WORKSPACE_DIR",
    "ANTIGRAVITY_WORKSPACE_ROOT",
    "CREWAI_STORAGE_DIR",
)

_MUTABLE_ENV_KEYS = {
    "ANTIGRAVITY_WORKSPACE_DIR",
    "ANTIGRAVITY_WORKSPACE_ROOT",
    "CREWAI_STORAGE_DIR",
    "ANTIGRAVITY_STRICT_PROVIDER_VALIDATION",
    "ANTIGRAVITY_MAX_PROVIDER_4XX",
    "ANTIGRAVITY_FAIL_ON_RESEARCH_EMPTY",
    "MINIMAX_BASE_URL",
    "DEEPSEEK_BASE_URL",
}


def read_runtime_configuration(
    *,
    project_root: Path,
    workspace: Path,
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

    return {
        "project_root": str(project_root),
        "workspace": str(workspace),
        "workspace_env_path": str(workspace_env),
        "project_env_path": str(project_env),
        "workspace_env_exists": workspace_env.exists(),
        "project_env_exists": project_env.exists(),
        "env_status": env_status,
    }


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


class _RunTestsArgs(BaseModel):
    timeout_seconds: int = Field(default=1800, description="Command timeout in seconds.")


class _RunBenchmarksArgs(BaseModel):
    timeout_seconds: int = Field(default=3600, description="Command timeout in seconds.")


class _ReadConfigArgs(BaseModel):
    pass


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

    def _run(self) -> str:
        result = read_runtime_configuration(
            project_root=Path(self.project_root),
            workspace=Path(self.workspace),
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
