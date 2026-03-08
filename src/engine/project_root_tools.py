from __future__ import annotations

from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


_ALLOWED_PREFIXES = (
    ".agent/rules/",
    ".agent/workflows/",
    "docs/architecture/",
    "docs/reports/",
    "docs/benchmarks/",
)
# Project-root tools stay scoped to curated governance docs. Full repository
# edit parity is provided through workspace tools when workspace_root=repo root.


class ProjectFileReadArgs(BaseModel):
    path: str = Field(..., description="Path to read relative to project root.")


class ProjectFileWriteArgs(BaseModel):
    path: str = Field(..., description="Path to write relative to project root.")
    content: str = Field(..., description="UTF-8 text content to write.")


def _normalise_relative(path: str) -> str:
    return str(Path(path).as_posix()).lstrip("./")


def _enforce_project_whitelist(relative_path: str) -> None:
    normalised = _normalise_relative(relative_path)
    if not any(normalised.startswith(prefix) for prefix in _ALLOWED_PREFIXES):
        raise ValueError(
            "Project-root file access denied. Allowed prefixes: "
            + ", ".join(_ALLOWED_PREFIXES)
        )


def _resolve_project_path(project_root: Path, relative_path: str) -> Path:
    _enforce_project_whitelist(relative_path)
    target = (project_root / relative_path).resolve()
    if not target.is_relative_to(project_root):
        raise ValueError(f"Path '{relative_path}' escapes project root.")
    return target


class ProjectRootFileReadTool(BaseTool):
    name: str = "project_root_file_read"
    description: str = (
        "Read a UTF-8 text file from project root, restricted to "
        ".agent/rules/*, .agent/workflows/*, docs/architecture/*, "
        "docs/reports/*, and docs/benchmarks/*."
    )
    args_schema: Type[BaseModel] = ProjectFileReadArgs
    project_root: str = Field(..., description="Absolute project root path.")

    def _run(self, path: str) -> str:
        root = Path(self.project_root).resolve()
        file_path = _resolve_project_path(root, path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return file_path.read_text(encoding="utf-8")


class ProjectRootFileWriteTool(BaseTool):
    name: str = "project_root_file_write"
    description: str = (
        "Write UTF-8 text under project root, restricted to "
        ".agent/rules/*, .agent/workflows/*, docs/architecture/*, "
        "docs/reports/*, and docs/benchmarks/*."
    )
    args_schema: Type[BaseModel] = ProjectFileWriteArgs
    project_root: str = Field(..., description="Absolute project root path.")

    def _run(self, path: str, content: str) -> str:
        root = Path(self.project_root).resolve()
        file_path = _resolve_project_path(root, path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Wrote {path}"
