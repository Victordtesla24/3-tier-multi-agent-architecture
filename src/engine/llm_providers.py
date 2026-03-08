"""Legacy multi-provider LLM helpers used by older integration paths."""

from __future__ import annotations

import os
from pathlib import Path

from crewai import LLM

from engine.llm_config import build_llm, resolved_model_specs
from engine.runtime_env import resolve_runtime_env

_MODULE_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


class ThinkingEffort:
    """Legacy temperature hints retained for backwards-compatible imports."""

    LOW = 0.9
    MEDIUM = 0.5
    HIGH = 0.25
    XHIGH = 0.1


def _default_workspace() -> Path:
    candidate = os.environ.get("ANTIGRAVITY_WORKSPACE_DIR", "").strip()
    if candidate:
        return Path(candidate).resolve()
    return Path.cwd().resolve()


def _resolved_specs() -> tuple:
    workspace = _default_workspace()
    return resolved_model_specs(
        resolve_runtime_env(workspace, project_root=_MODULE_PROJECT_ROOT)
    )


class LLMProvider:
    """Central LLM provider configuration for env-driven tier selection."""

    @staticmethod
    def get_orchestration_llm(fallback: bool = False) -> LLM:
        specs = _resolved_specs()
        return build_llm(specs[1] if fallback else specs[0])

    @staticmethod
    def get_l1_llm(fallback: bool = False) -> LLM:
        specs = _resolved_specs()
        return build_llm(specs[3] if fallback else specs[2])

    @staticmethod
    def get_l2_llm(fallback: bool = False) -> LLM:
        specs = _resolved_specs()
        return build_llm(specs[5] if fallback else specs[4])

    @staticmethod
    def get_l3_llm(fallback: bool = False) -> LLM:
        specs = _resolved_specs()
        return build_llm(specs[7] if fallback else specs[6])
