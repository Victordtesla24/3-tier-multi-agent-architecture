from __future__ import annotations

import os
import re
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


@dataclass(frozen=True)
class ProviderPolicy:
    model_pattern: str
    blocked_params: tuple[str, ...]
    non_retriable_markers: tuple[str, ...]


DEFAULT_PROVIDER_POLICY = ProviderPolicy(
    model_pattern="*",
    blocked_params=(),
    non_retriable_markers=(
        "invalid_request_error",
        "unsupported parameter",
        "authenticationerror",
        "unauthorized",
        "forbidden",
        "key=none",
    ),
)


PROVIDER_POLICIES: tuple[ProviderPolicy, ...] = (
    ProviderPolicy(
        model_pattern="openai/gpt-5.2-codex",
        blocked_params=("temperature",),
        non_retriable_markers=DEFAULT_PROVIDER_POLICY.non_retriable_markers,
    ),
    ProviderPolicy(
        model_pattern="gemini/gemini-3.1-pro-preview",
        blocked_params=(),
        non_retriable_markers=DEFAULT_PROVIDER_POLICY.non_retriable_markers,
    ),
    DEFAULT_PROVIDER_POLICY,
)


def _required_provider_env_aliases() -> tuple[tuple[str, ...], ...]:
    return (
        ("OPENAI_API_KEY",),
        ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        ("MINIMAX_API_KEY",),
        ("DEEPSEEK_API_KEY",),
        ("MINIMAX_BASE_URL",),
        ("DEEPSEEK_BASE_URL",),
    )


def _placeholder_values() -> set[str]:
    return {
        "",
        "none",
        "null",
        "your_google_api_key_here",
        "your_openai_api_key_here",
        "your_minimax_api_key_here",
        "your_deepseek_api_key_here",
        "your_minimax_base_url_here",
        "your_deepseek_base_url_here",
    }


def validate_provider_runtime_env(*, strict: bool = True) -> dict[str, str]:
    """
    Validates that all provider credentials/base URLs are configured before any LLM call.
    When strict=True, placeholder-like values are rejected.
    """
    resolved: dict[str, str] = {}
    placeholders = _placeholder_values()

    for names in _required_provider_env_aliases():
        label = " / ".join(names)
        value = require_env(names, label=label).strip()
        if strict and value.lower() in placeholders:
            raise EnvConfigError(
                f"Invalid placeholder value for {label}. "
                "Set a real credential/base URL before runtime."
            )
        resolved[names[0]] = value
    return resolved


def get_provider_policy(model: str) -> ProviderPolicy:
    for policy in PROVIDER_POLICIES:
        if policy.model_pattern == "*" or policy.model_pattern == model:
            return policy
    return DEFAULT_PROVIDER_POLICY


def classify_provider_error(exc: Exception, *, model: str | None = None) -> dict[str, Any]:
    """Classifies provider errors for retry policy and telemetry emission."""
    message = str(exc)
    lowered = message.lower()
    policy = get_provider_policy(model or "*")

    status_match = re.search(r"HTTP/1\.1\s+(\d{3})", message)
    http_status = int(status_match.group(1)) if status_match else None

    code_match = re.search(r'"code"\s*:\s*"([^"]+)"', message)
    error_code = code_match.group(1) if code_match else None

    retriable = True
    if http_status is not None and 400 <= http_status < 500 and http_status != 429:
        retriable = False
    if any(marker in lowered for marker in policy.non_retriable_markers):
        retriable = False

    return {
        "http_status": http_status,
        "error_type": type(exc).__name__,
        "error_code": error_code,
        "retriable": retriable,
    }


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

    policy = get_provider_policy(spec.crewai_model)
    for blocked in policy.blocked_params:
        kwargs.pop(blocked, None)

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
    strict_validation: bool = True,
) -> ModelMatrix:
    load_workspace_env(workspace_dir, project_root=project_root)

    # Validate that the minimum env surface exists up-front.
    validate_provider_runtime_env(strict=strict_validation)

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
