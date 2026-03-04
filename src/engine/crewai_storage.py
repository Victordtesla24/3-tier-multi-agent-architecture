from __future__ import annotations

"""
Centralised CrewAI storage bootstrap.

This module ensures that all CrewAI- and appdirs-backed storage is routed into
the current workspace under:

    <workspace>/.agent/memory/crewai_storage

Call `bootstrap_crewai_storage(workspace)` *before* importing any modules that
initialise CrewAI or ChromaDB to avoid writes to user-level directories.
"""

import os
from pathlib import Path


def bootstrap_crewai_storage(workspace: str | Path) -> Path:
    """
    Bind CrewAI storage to <workspace>/.agent/memory/crewai_storage and
    patch appdirs.user_data_dir so any library that relies on appdirs will
    also write inside this directory.
    """
    workspace_path = Path(workspace).resolve()
    storage_dir = workspace_path / ".agent" / "memory" / "crewai_storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Environment variables recognised by CrewAI for persistent storage.
    os.environ.setdefault("CREWAI_STORAGE_DIR", str(storage_dir))
    os.environ.setdefault("CREWAI_HOME", str(storage_dir))

    try:
        import appdirs  # type: ignore
    except Exception:
        # If appdirs is unavailable, we still return a valid storage path.
        return storage_dir

    def _patched_user_data_dir(
        appname: str | None = None,
        appauthor: str | None = None,
        version: str | None = None,
        roaming: bool = False,
    ) -> str:
        base = storage_dir / "appdirs_data"
        if appname:
            base = base / appname
        base.mkdir(parents=True, exist_ok=True)
        return str(base)

    appdirs.user_data_dir = _patched_user_data_dir  # type: ignore[attr-defined]

    return storage_dir

