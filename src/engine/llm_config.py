from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Sequence, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from crewai import LLM as CrewAILLM
else:  # pragma: no cover - annotations only
    CrewAILLM = Any

try:
    from crewai import LLM as _RuntimeCrewAILLM
except ModuleNotFoundError:  # pragma: no cover - import guard only
    _RuntimeCrewAILLM = None

from engine.model_catalog import (
    DEFAULT_LEVEL1_FALLBACK_MODEL,
    DEFAULT_LEVEL1_MODEL,
    DEFAULT_LEVEL2_FALLBACK_MODEL,
    DEFAULT_LEVEL2_MODEL,
    DEFAULT_LEVEL3_FALLBACK_MODEL,
    DEFAULT_LEVEL3_MODEL,
    DEFAULT_ORCHESTRATION_FALLBACK_MODEL,
    DEFAULT_ORCHESTRATION_MODEL,
    ModelCatalogEntry,
    get_model_entry,
    iter_primary_model_entries,
)
from engine.runtime_env import (
    EnvConfigError,
    ResolvedRuntimeEnv,
    load_workspace_env as _load_workspace_env,
    normalize_model_identifier,
    resolve_runtime_env,
    resolve_runtime_env_from_environ,
)

load_workspace_env = _load_workspace_env


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
    default_base_url: Optional[str] = None
    requested_thinking: Optional[str] = None
    runtime_reasoning_effort: Optional[str] = None
    requested_temperature: Optional[float] = None
    runtime_temperature: Optional[float] = None


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
        model_pattern="openai/gpt-5*",
        blocked_params=("temperature",),
        non_retriable_markers=DEFAULT_PROVIDER_POLICY.non_retriable_markers,
    ),
    ProviderPolicy(
        model_pattern="openai/o1",
        blocked_params=("temperature",),
        non_retriable_markers=DEFAULT_PROVIDER_POLICY.non_retriable_markers,
    ),
    ProviderPolicy(
        model_pattern="ollama/*",
        blocked_params=("reasoning_effort",),
        non_retriable_markers=DEFAULT_PROVIDER_POLICY.non_retriable_markers,
    ),
    ProviderPolicy(
        model_pattern="deepseek/*",
        blocked_params=("reasoning_effort",),
        non_retriable_markers=DEFAULT_PROVIDER_POLICY.non_retriable_markers,
    ),
    DEFAULT_PROVIDER_POLICY,
)

_AUTO = object()


def _placeholder_values() -> set[str]:
    return {
        "",
        "none",
        "null",
        "your_deepseek_api_key_here",
        "your_deepseek_base_url_here",
        "your_google_api_key_here",
        "your_openai_api_key_here",
        "your_ollama_base_url_here",
    }


def _first_env(names: Sequence[str]) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def require_env(names: Sequence[str], *, label: str) -> str:
    value = _first_env(names)
    if not value:
        raise EnvConfigError(
            f"Missing required configuration for {label}. "
            f"Set one of: {', '.join(names)}"
        )
    return value


def normalise_base_url(url: str) -> str:
    """Remove trailing slashes to avoid double //v1 patterns."""
    return url.rstrip("/")


def _default_effort_for_entry(entry: ModelCatalogEntry) -> Effort:
    if entry.runtime_reasoning_effort:
        return Effort(entry.runtime_reasoning_effort.lower())
    return Effort.HIGH


def model_spec_from_catalog(
    logical_id: str,
    *,
    effort: Effort | None = None,
    requested_thinking: str | None = None,
    requested_temperature: float | None | object = _AUTO,
    runtime_temperature: float | None | object = _AUTO,
) -> ModelSpec:
    entry = get_model_entry(normalize_model_identifier(logical_id))
    spec_effort = effort or _default_effort_for_entry(entry)
    spec_requested_temperature = (
        entry.requested_temperature
        if requested_temperature is _AUTO
        else cast(float | None, requested_temperature)
    )
    if runtime_temperature is _AUTO:
        spec_runtime_temperature = (
            None
            if entry.logical_id.startswith("openai/gpt-5")
            else spec_requested_temperature
        )
    else:
        spec_runtime_temperature = cast(float | None, runtime_temperature)

    return ModelSpec(
        logical_id=entry.logical_id,
        crewai_model=entry.crewai_model,
        effort=spec_effort,
        api_key_env=entry.api_key_env,
        base_url_env=entry.base_url_env,
        default_base_url=entry.default_base_url,
        requested_thinking=requested_thinking or entry.requested_thinking,
        runtime_reasoning_effort=entry.runtime_reasoning_effort,
        requested_temperature=spec_requested_temperature,
        runtime_temperature=spec_runtime_temperature,
    )


def get_provider_policy(model: str) -> ProviderPolicy:
    """Resolve the most specific provider policy for the given model identifier."""
    for policy in PROVIDER_POLICIES:
        if policy.model_pattern == "*":
            continue
        if fnmatch.fnmatch(model, policy.model_pattern):
            return policy
    return DEFAULT_PROVIDER_POLICY


def classify_provider_error(
    exc: Exception, *, model: str | None = None
) -> dict[str, Any]:
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


def _api_key_aliases_for_spec(spec: ModelSpec) -> tuple[str, ...]:
    if spec.crewai_model.startswith("gemini/"):
        return ("GOOGLE_API_KEY", "GEMINI_API_KEY")
    if spec.api_key_env is None:
        return ()
    return (spec.api_key_env,)


def _base_url_aliases_for_spec(spec: ModelSpec) -> tuple[str, ...]:
    return (spec.base_url_env,) if spec.base_url_env else ()


def resolve_optional_base_url(spec: ModelSpec) -> str | None:
    configured = _first_env(_base_url_aliases_for_spec(spec))
    if configured:
        return normalise_base_url(configured.strip())
    if spec.default_base_url:
        return normalise_base_url(spec.default_base_url)
    return None


def _supports_reasoning_effort(spec: ModelSpec) -> bool:
    return not spec.crewai_model.startswith(("gemini/", "ollama/", "deepseek/"))


def _required_provider_env_aliases_for_specs(
    model_specs: Sequence[ModelSpec],
) -> tuple[tuple[str, ...], ...]:
    aliases: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for spec in model_specs:
        api_names = _api_key_aliases_for_spec(spec)
        if api_names and api_names not in seen:
            seen.add(api_names)
            aliases.append(api_names)
        base_names = _base_url_aliases_for_spec(spec)
        if base_names and base_names not in seen:
            seen.add(base_names)
            aliases.append(base_names)
    return tuple(aliases)


def validate_provider_runtime_env(
    *,
    strict: bool = True,
    model_specs: Sequence[ModelSpec] | None = None,
) -> dict[str, str]:
    """
    Validates that the credentials/base URLs for the active model matrix are configured.
    When strict=True, placeholder-like values are rejected.
    """
    specs = tuple(model_specs or active_model_specs())
    resolved: dict[str, str] = {}
    placeholders = _placeholder_values()

    for names in _required_provider_env_aliases_for_specs(specs):
        label = " / ".join(names)
        matching_spec = next(
            (
                spec
                for spec in specs
                if _base_url_aliases_for_spec(spec) == names
            ),
            None,
        )
        value = _first_env(names)
        if value is None:
            if matching_spec is not None and matching_spec.default_base_url is not None:
                resolved[names[0]] = normalise_base_url(matching_spec.default_base_url)
                continue
            raise EnvConfigError(
                f"Missing required configuration for {label}. "
                f"Set one of: {', '.join(names)}"
            )

        value = value.strip()
        if strict and value.lower() in placeholders:
            raise EnvConfigError(
                f"Invalid placeholder value for {label}. "
                "Set a real credential/base URL before runtime."
            )
        if matching_spec is not None:
            value = normalise_base_url(value)
        resolved[names[0]] = value
    return resolved


def build_llm(spec: ModelSpec) -> CrewAILLM:
    """
    Creates a CrewAI LLM instance for the given model spec.
    For OpenAI-compatible proxies, set base_url via spec.base_url_env.
    """
    if _RuntimeCrewAILLM is None:  # pragma: no cover - runtime-only guard
        raise ModuleNotFoundError(
            "crewai is not installed. Install crewai to build runtime LLM clients."
        )

    kwargs: dict[str, Any] = {
        "model": spec.crewai_model,
        "timeout": 90.0,
    }

    api_key_aliases = _api_key_aliases_for_spec(spec)
    if api_key_aliases:
        kwargs["api_key"] = require_env(
            api_key_aliases, label=spec.api_key_env or "api key"
        ).strip()

    if spec.crewai_model.startswith("gemini/"):
        if spec.runtime_temperature is not None:
            kwargs["temperature"] = spec.runtime_temperature
        return _RuntimeCrewAILLM(**kwargs)

    if _supports_reasoning_effort(spec):
        kwargs["reasoning_effort"] = spec.effort.value
    if spec.runtime_temperature is not None:
        kwargs["temperature"] = spec.runtime_temperature

    resolved_base_url = resolve_optional_base_url(spec)
    if resolved_base_url is not None:
        kwargs["base_url"] = resolved_base_url

    policy = get_provider_policy(spec.crewai_model)
    for blocked in policy.blocked_params:
        kwargs.pop(blocked, None)

    return _RuntimeCrewAILLM(**kwargs)


@dataclass(frozen=True)
class ModelTier:
    primary: CrewAILLM
    fallback: CrewAILLM


PRIMARY_LLM_MAP: dict[str, tuple[str, str | None]] = {
    entry.logical_id: (entry.crewai_model, entry.api_key_env)
    for entry in iter_primary_model_entries()
}

PRIMARY_LLM_ALIASES: dict[str, str] = {
    "openai/gpt-5.2": DEFAULT_ORCHESTRATION_MODEL,
    "openai/gpt-5.3-codex": DEFAULT_ORCHESTRATION_FALLBACK_MODEL,
    "gemini/gemini-3-pro-preview": DEFAULT_LEVEL1_MODEL,
}

_PRIMARY_LLM_DEFAULT = DEFAULT_ORCHESTRATION_MODEL


def resolve_primary_model_spec(effort: Effort | None = None) -> ModelSpec:
    """
    Backwards-compatible orchestration primary resolver driven by PRIMARY_LLM.
    Tier-specific env vars override it via the shared runtime resolver.
    """
    raw = os.environ.get("PRIMARY_LLM", "").strip() or _PRIMARY_LLM_DEFAULT
    raw = PRIMARY_LLM_ALIASES.get(raw, raw)
    resolved = resolve_runtime_env_from_environ(primary_model_id_override=raw)
    return _spec_for_tier_slot(
        resolved.orchestration.primary_logical_id,
        tier_name="orchestration",
        is_fallback=False,
        override_effort=effort,
    )


def _thinking_for_slot(
    *,
    logical_id: str,
    tier_name: str,
    is_fallback: bool,
    effort: Effort,
) -> str:
    if tier_name == "orchestration" and logical_id.startswith("openai/gpt-5"):
        return "xHigh"
    if is_fallback and effort == Effort.MEDIUM:
        return "Medium"
    if effort == Effort.LOW:
        return "Low"
    return "High"


def _spec_for_tier_slot(
    logical_id: str,
    *,
    tier_name: str,
    is_fallback: bool,
    override_effort: Effort | None = None,
) -> ModelSpec:
    if override_effort is not None:
        effort = override_effort
    elif is_fallback:
        effort = {
            "orchestration": Effort.HIGH,
            "level1": Effort.MEDIUM,
            "level2": Effort.LOW,
            "level3": Effort.LOW,
        }[tier_name]
    else:
        effort = Effort.HIGH

    return model_spec_from_catalog(
        logical_id,
        effort=effort,
        requested_thinking=_thinking_for_slot(
            logical_id=normalize_model_identifier(logical_id),
            tier_name=tier_name,
            is_fallback=is_fallback,
            effort=effort,
        ),
    )


ORCHESTRATION_PRIMARY = _spec_for_tier_slot(
    DEFAULT_ORCHESTRATION_MODEL,
    tier_name="orchestration",
    is_fallback=False,
)
ORCHESTRATION_FALLBACK = _spec_for_tier_slot(
    DEFAULT_ORCHESTRATION_FALLBACK_MODEL,
    tier_name="orchestration",
    is_fallback=True,
)
L1_PRIMARY = _spec_for_tier_slot(
    DEFAULT_LEVEL1_MODEL,
    tier_name="level1",
    is_fallback=False,
)
L1_FALLBACK = _spec_for_tier_slot(
    DEFAULT_LEVEL1_FALLBACK_MODEL,
    tier_name="level1",
    is_fallback=True,
)
L2_PRIMARY = _spec_for_tier_slot(
    DEFAULT_LEVEL2_MODEL,
    tier_name="level2",
    is_fallback=False,
)
L2_FALLBACK = _spec_for_tier_slot(
    DEFAULT_LEVEL2_FALLBACK_MODEL,
    tier_name="level2",
    is_fallback=True,
)
L3_PRIMARY = _spec_for_tier_slot(
    DEFAULT_LEVEL3_MODEL,
    tier_name="level3",
    is_fallback=False,
)
L3_FALLBACK = _spec_for_tier_slot(
    DEFAULT_LEVEL3_FALLBACK_MODEL,
    tier_name="level3",
    is_fallback=True,
)


@dataclass(frozen=True)
class ModelMatrix:
    orchestration: ModelTier
    level1: ModelTier
    level2: ModelTier
    level3: ModelTier
    level2_swarm_count: int | None = None
    level3_swarm_count: int | None = None
    config_warnings: tuple[str, ...] = ()
    tier_primary_logical_ids: dict[str, str] = field(default_factory=dict)
    tier_fallback_logical_ids: dict[str, str] = field(default_factory=dict)
    active_provider_env_keys: tuple[str, ...] = ()


def _runtime_env_to_specs(resolved: ResolvedRuntimeEnv) -> tuple[ModelSpec, ...]:
    return (
        _spec_for_tier_slot(
            resolved.orchestration.primary_logical_id,
            tier_name="orchestration",
            is_fallback=False,
        ),
        _spec_for_tier_slot(
            resolved.orchestration.fallback_logical_id,
            tier_name="orchestration",
            is_fallback=True,
        ),
        _spec_for_tier_slot(
            resolved.level1.primary_logical_id,
            tier_name="level1",
            is_fallback=False,
        ),
        _spec_for_tier_slot(
            resolved.level1.fallback_logical_id,
            tier_name="level1",
            is_fallback=True,
        ),
        _spec_for_tier_slot(
            resolved.level2.primary_logical_id,
            tier_name="level2",
            is_fallback=False,
        ),
        _spec_for_tier_slot(
            resolved.level2.fallback_logical_id,
            tier_name="level2",
            is_fallback=True,
        ),
        _spec_for_tier_slot(
            resolved.level3.primary_logical_id,
            tier_name="level3",
            is_fallback=False,
        ),
        _spec_for_tier_slot(
            resolved.level3.fallback_logical_id,
            tier_name="level3",
            is_fallback=True,
        ),
    )


def resolved_model_specs(resolved: ResolvedRuntimeEnv) -> tuple[ModelSpec, ...]:
    return _runtime_env_to_specs(resolved)


def active_model_specs(primary_model_id: str | None = None) -> tuple[ModelSpec, ...]:
    primary_override = (
        PRIMARY_LLM_ALIASES.get(primary_model_id, primary_model_id)
        if primary_model_id
        else None
    )
    resolved = resolve_runtime_env_from_environ(
        primary_model_id_override=primary_override
    )
    return _runtime_env_to_specs(resolved)


def required_env_keys_for_active_matrix(
    primary_model_id: str | None = None,
) -> tuple[str, ...]:
    primary_override = (
        PRIMARY_LLM_ALIASES.get(primary_model_id, primary_model_id)
        if primary_model_id
        else None
    )
    resolved = resolve_runtime_env_from_environ(
        primary_model_id_override=primary_override
    )
    return resolved.active_provider_env_keys


def build_model_matrix(
    workspace_dir: str | Path,
    *,
    project_root: str | Path | None = None,
    strict_validation: bool = True,
) -> ModelMatrix:
    resolved = resolve_runtime_env(
        workspace_dir,
        project_root=project_root,
    )
    active_specs = _runtime_env_to_specs(resolved)
    validate_provider_runtime_env(strict=strict_validation, model_specs=active_specs)

    (
        orch_primary,
        orch_fallback,
        l1_primary,
        l1_fallback,
        l2_primary,
        l2_fallback,
        l3_primary,
        l3_fallback,
    ) = (build_llm(spec) for spec in active_specs)

    return ModelMatrix(
        orchestration=ModelTier(primary=orch_primary, fallback=orch_fallback),
        level1=ModelTier(primary=l1_primary, fallback=l1_fallback),
        level2=ModelTier(primary=l2_primary, fallback=l2_fallback),
        level3=ModelTier(primary=l3_primary, fallback=l3_fallback),
        level2_swarm_count=resolved.swarm.level2,
        level3_swarm_count=resolved.swarm.level3,
        config_warnings=resolved.warnings,
        tier_primary_logical_ids=resolved.tier_primary_logical_ids(),
        tier_fallback_logical_ids=resolved.tier_fallback_logical_ids(),
        active_provider_env_keys=resolved.active_provider_env_keys,
    )
