from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Sequence

from dotenv import load_dotenv

from crewai import LLM


class Effort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


@dataclass(frozen=True)
class ModelSpec:
    logical_id: str
    crewai_model: str
    effort: Effort
    api_key_env: Optional[str] = None
    base_url_env: Optional[str] = None


class EnvConfigError(RuntimeError):
    pass


def load_workspace_env(
    workspace_dir: str | Path,
    *,
    project_root: str | Path | None = None,
) -> None:
    """
    Loads environment variables with deterministic precedence:
      1) project-root .env (if provided)
      2) workspace .env (overrides project-root values)
    """
    if project_root is not None:
        project_env = Path(project_root).resolve() / ".env"
        try:
            if project_env.exists():
                load_dotenv(dotenv_path=project_env, override=False)
        except PermissionError:
            pass

    workspace_env = Path(workspace_dir).resolve() / ".env"
    try:
        if workspace_env.exists():
            # Workspace-specific values should override project defaults.
            load_dotenv(dotenv_path=workspace_env, override=True)
    except PermissionError:
        pass


def _first_env(names: Sequence[str]) -> Optional[str]:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


def require_env(names: Sequence[str], *, label: str) -> str:
    v = _first_env(names)
    if not v:
        raise EnvConfigError(
            f"Missing required configuration for {label}. "
            f"Set one of: {', '.join(names)}"
        )
    return v


def normalise_base_url(url: str) -> str:
    """Remove trailing slashes to avoid double //v1 patterns."""
    return url.rstrip("/")


def build_llm(spec: ModelSpec) -> LLM:
    """
    Creates a CrewAI LLM instance for the given model spec.
    For OpenAI-compatible proxies, set base_url via spec.base_url_env.
    """
    if spec.crewai_model.startswith("gemini/"):
        google_key = _first_env(["GOOGLE_API_KEY", "GEMINI_API_KEY"])
        if not google_key:
            raise EnvConfigError(
                "Missing Google API key. Set GOOGLE_API_KEY or GEMINI_API_KEY."
            )
        # Gemini 3 defaults to dynamic 'high' thinking if thinkingLevel is not specified.
        return LLM(
            model=spec.crewai_model,
            api_key=google_key,
            temperature=0.2,
            timeout=90.0,
        )

    # OpenAI + OpenAI-compatible
    api_key_env = spec.api_key_env or "OPENAI_API_KEY"
    provider_key = os.environ.get(api_key_env)
    if not provider_key:
        raise EnvConfigError(f"Missing {api_key_env}.")

    kwargs: dict[str, Any] = dict(
        model=spec.crewai_model,
        api_key=provider_key,
        timeout=90.0,
        reasoning_effort=spec.effort.value,
    )

    if spec.base_url_env:
        base_url = os.environ.get(spec.base_url_env)
        if not base_url:
            raise EnvConfigError(
                f"Missing proxy base URL for {spec.logical_id}. "
                f"Set {spec.base_url_env} in .env."
            )
        kwargs["base_url"] = normalise_base_url(base_url)

    return LLM(**kwargs)


@dataclass(frozen=True)
class ModelTier:
    primary: LLM
    fallback: LLM


# --- Hardcoded Model Matrix (as specified) ---

ORCHESTRATION_PRIMARY = ModelSpec(
    logical_id="Google/Gemini-3.1-Pro-Preview",
    crewai_model="gemini/gemini-3.1-pro-preview",
    effort=Effort.HIGH,
)

ORCHESTRATION_FALLBACK = ModelSpec(
    logical_id="OpenAI/GPT-5.2-Codex",
    crewai_model="openai/gpt-5.2-codex",
    effort=Effort.XHIGH,
)

L1_PRIMARY = ModelSpec(
    logical_id="OpenAI/GPT-5.2-Codex",
    crewai_model="openai/gpt-5.2-codex",
    effort=Effort.MEDIUM,
)

L1_FALLBACK = ModelSpec(
    logical_id="MiniMax/Minimax-m2.5",
    crewai_model="openai/minimax-m2.5",
    effort=Effort.MEDIUM,
    api_key_env="MINIMAX_API_KEY",
    base_url_env="MINIMAX_BASE_URL",
)

L2_PRIMARY = ModelSpec(
    logical_id="MiniMax/Minimax-m2.5",
    crewai_model="openai/minimax-m2.5",
    effort=Effort.LOW,
    api_key_env="MINIMAX_API_KEY",
    base_url_env="MINIMAX_BASE_URL",
)

L2_FALLBACK = ModelSpec(
    logical_id="deepseek/deepseek-v3.2",
    crewai_model="openai/deepseek-v3.2",
    effort=Effort.LOW,
    api_key_env="DEEPSEEK_API_KEY",
    base_url_env="DEEPSEEK_BASE_URL",
)


@dataclass(frozen=True)
class ModelMatrix:
    orchestration: ModelTier
    level1: ModelTier
    level2: ModelTier


def build_model_matrix(
    workspace_dir: str | Path,
    *,
    project_root: str | Path | None = None,
) -> ModelMatrix:
    load_workspace_env(workspace_dir, project_root=project_root)

    # Validate that the minimum env surface exists up-front.
    require_env(["OPENAI_API_KEY"], label="OpenAI API key")
    require_env(["GOOGLE_API_KEY", "GEMINI_API_KEY"], label="Google Gemini API key")
    require_env(["MINIMAX_API_KEY"], label="MiniMax API key")
    require_env(["DEEPSEEK_API_KEY"], label="DeepSeek API key")
    require_env(["MINIMAX_BASE_URL"], label="MiniMax OpenAI-compatible base URL")
    require_env(["DEEPSEEK_BASE_URL"], label="DeepSeek OpenAI-compatible base URL")

    orch_primary = build_llm(ORCHESTRATION_PRIMARY)
    orch_fallback = build_llm(ORCHESTRATION_FALLBACK)

    l1_primary = build_llm(L1_PRIMARY)
    l1_fallback = build_llm(L1_FALLBACK)

    l2_primary = build_llm(L2_PRIMARY)
    l2_fallback = build_llm(L2_FALLBACK)

    return ModelMatrix(
        orchestration=ModelTier(primary=orch_primary, fallback=orch_fallback),
        level1=ModelTier(primary=l1_primary, fallback=l1_fallback),
        level2=ModelTier(primary=l2_primary, fallback=l2_fallback),
    )
