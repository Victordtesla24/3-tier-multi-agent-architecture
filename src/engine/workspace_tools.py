from __future__ import annotations

from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class FileReadArgs(BaseModel):
    path: str = Field(..., description="Path to read, relative to workspace root.")


class FileWriteArgs(BaseModel):
    path: str = Field(..., description="Path to write, relative to workspace root.")
    content: str = Field(..., description="UTF-8 text content to write.")


def _resolve_workspace_path(workspace_root: Path, relative_path: str) -> Path:
    target = (workspace_root / relative_path).resolve()
    if not target.is_relative_to(workspace_root):
        raise ValueError(f"Path '{relative_path}' escapes workspace root.")
    return target


class WorkspaceFileReadTool(BaseTool):
    name: str = "workspace_file_read"
    description: str = (
        "Read a UTF-8 text file from the workspace. "
        "Use this for source files and generated artifacts."
    )
    args_schema: Type[BaseModel] = FileReadArgs
    workspace_root: str = Field(..., description="Absolute workspace root path.")

    def _run(self, path: str) -> str:
        root = Path(self.workspace_root).resolve()
        file_path = _resolve_workspace_path(root, path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return file_path.read_text(encoding="utf-8")


class WorkspaceFileWriteTool(BaseTool):
    name: str = "workspace_file_write"
    description: str = (
        "Write UTF-8 text to a file under workspace. "
        "Creates parent directories if needed."
    )
    args_schema: Type[BaseModel] = FileWriteArgs
    workspace_root: str = Field(..., description="Absolute workspace root path.")

    def _run(self, path: str, content: str) -> str:
        root = Path(self.workspace_root).resolve()
        file_path = _resolve_workspace_path(root, path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Wrote {path}"
