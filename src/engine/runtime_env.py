from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from dotenv import load_dotenv as _load_dotenv
except ModuleNotFoundError:  # pragma: no cover - exercised via direct script usage
    _load_dotenv = None

from engine.model_catalog import (
    DEFAULT_LEVEL1_FALLBACK_MODEL,
    DEFAULT_LEVEL1_MODEL,
    DEFAULT_LEVEL2_FALLBACK_MODEL,
    DEFAULT_LEVEL2_MODEL,
    DEFAULT_LEVEL3_FALLBACK_MODEL,
    DEFAULT_LEVEL3_MODEL,
    DEFAULT_ORCHESTRATION_FALLBACK_MODEL,
    DEFAULT_ORCHESTRATION_MODEL,
    MODEL_CATALOG,
    get_model_entry,
)


class EnvConfigError(RuntimeError):
    """Raised when runtime environment configuration is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ResolvedTierSelection:
    tier_name: str
    primary_logical_id: str
    fallback_logical_id: str
    primary_source: str
    fallback_source: str = "catalog_default"


@dataclass(frozen=True)
class ResolvedSwarmConfig:
    level2: int | None = None
    level3: int | None = None


@dataclass(frozen=True)
class ResolvedRuntimeEnv:
    workspace_dir: Path | None
    project_root: Path | None
    orchestration: ResolvedTierSelection
    level1: ResolvedTierSelection
    level2: ResolvedTierSelection
    level3: ResolvedTierSelection
    swarm: ResolvedSwarmConfig
    warnings: tuple[str, ...]
    active_provider_env_keys: tuple[str, ...]
    configured_providers: tuple["ConfiguredProviderInventory", ...] = ()

    def active_model_logical_ids(self) -> tuple[str, ...]:
        return (
            self.orchestration.primary_logical_id,
            self.orchestration.fallback_logical_id,
            self.level1.primary_logical_id,
            self.level1.fallback_logical_id,
            self.level2.primary_logical_id,
            self.level2.fallback_logical_id,
            self.level3.primary_logical_id,
            self.level3.fallback_logical_id,
        )

    def tier_primary_logical_ids(self) -> dict[str, str]:
        return {
            "orchestration": self.orchestration.primary_logical_id,
            "level1": self.level1.primary_logical_id,
            "level2": self.level2.primary_logical_id,
            "level3": self.level3.primary_logical_id,
        }

    def tier_fallback_logical_ids(self) -> dict[str, str]:
        return {
            "orchestration": self.orchestration.fallback_logical_id,
            "level1": self.level1.fallback_logical_id,
            "level2": self.level2.fallback_logical_id,
            "level3": self.level3.fallback_logical_id,
        }


@dataclass(frozen=True)
class ConfiguredProviderInventory:
    provider_group: str
    api_key_env: str | None
    configured_api_key_keys: tuple[str, ...]
    api_key_configured: bool
    base_url_env: str | None = None
    configured_base_url_keys: tuple[str, ...] = ()
    resolved_base_url: str | None = None
    canonical_base_url: str | None = None


@dataclass(frozen=True)
class _EnvOccurrence:
    key: str
    value: str
    line_number: int
    path: Path


@dataclass(frozen=True)
class _ProviderEnvSpec:
    provider_group: str
    api_key_env: str | None
    base_url_env: str | None = None
    canonical_base_url: str | None = None


_MODEL_ID_ALIASES: dict[str, str] = {
    "openai/gpt-5.2": DEFAULT_ORCHESTRATION_MODEL,
    "openai/gpt-5.3-codex": DEFAULT_ORCHESTRATION_FALLBACK_MODEL,
    "gemini/gemini-3-pro-preview": DEFAULT_LEVEL1_MODEL,
    "minimax/minimax-m2.5": DEFAULT_LEVEL2_MODEL,
    "glm/glm-5": DEFAULT_LEVEL1_FALLBACK_MODEL,
    "glm/glm-4.7": DEFAULT_LEVEL3_FALLBACK_MODEL,
    "kimi/kimi-k2-thinking": DEFAULT_LEVEL1_FALLBACK_MODEL,
    "moonshotai/kimi-k2.5": DEFAULT_LEVEL1_FALLBACK_MODEL,
    "moonshotai/kimi-k2-thinking": DEFAULT_LEVEL1_FALLBACK_MODEL,
    "deepseek/deepseek-v3.2": "deepseek/deepseek-chat",
}
for _entry in MODEL_CATALOG:
    _MODEL_ID_ALIASES[_entry.logical_id.lower()] = _entry.logical_id
    _MODEL_ID_ALIASES[_entry.crewai_model.lower()] = _entry.logical_id

_ENV_ALIAS_MAP: dict[str, tuple[str, ...]] = {
    "GOOGLE_API_KEY": ("GEMINI_API_KEY",),
}

_BASE_URL_KEYS = (
    "DEEPSEEK_BASE_URL",
    "OLLAMA_BASE_URL",
)

_PLACEHOLDER_VALUES = {
    "",
    "none",
    "null",
    "your_deepseek_api_key_here",
    "your_deepseek_base_url_here",
    "your_google_api_key_here",
    "your_openai_api_key_here",
    "your_ollama_base_url_here",
}


def _provider_env_specs() -> tuple[_ProviderEnvSpec, ...]:
    specs: list[_ProviderEnvSpec] = []
    seen: set[str] = set()
    for entry in MODEL_CATALOG:
        if entry.provider_group in seen:
            continue
        seen.add(entry.provider_group)
        specs.append(
            _ProviderEnvSpec(
                provider_group=entry.provider_group,
                api_key_env=entry.api_key_env,
                base_url_env=entry.base_url_env,
                canonical_base_url=entry.default_base_url,
            )
        )
    return tuple(specs)


_PROVIDER_ENV_SPECS = _provider_env_specs()


def collect_env_warnings(*warning_groups: Iterable[str]) -> tuple[str, ...]:
    warnings: list[str] = []
    seen: set[str] = set()
    for group in warning_groups:
        for warning in group:
            if not warning or warning in seen:
                continue
            seen.add(warning)
            warnings.append(warning)
    return tuple(warnings)


def _is_configured_env_value(value: str | None) -> bool:
    if value is None:
        return False
    cleaned = value.strip().lower()
    return bool(cleaned) and cleaned not in _PLACEHOLDER_VALUES


def _aliases_for_env_key(key: str) -> tuple[str, ...]:
    return _ENV_ALIAS_MAP.get(key, ())


def _configured_occurrence_keys(
    occurrences: dict[str, list[_EnvOccurrence]],
    canonical: str,
) -> tuple[str, ...]:
    keys: list[str] = []
    for name in (canonical, *_aliases_for_env_key(canonical)):
        if occurrences.get(name):
            keys.append(name)
    return tuple(keys)


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

    def _apply_dotenv(path: Path, *, override: bool) -> None:
        if _load_dotenv is not None:
            _load_dotenv(dotenv_path=path, override=override)
            return

        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", maxsplit=1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if override or key not in os.environ:
                os.environ[key] = value

    if project_root is not None:
        project_env = Path(project_root).resolve() / ".env"
        try:
            if project_env.exists():
                _apply_dotenv(project_env, override=False)
        except PermissionError as exc:
            raise RuntimeError(
                f"Permission denied reading project-root .env at '{project_env}'. "
                "Ensure the file is readable by the current process user."
            ) from exc

    workspace_env = Path(workspace_dir).resolve() / ".env"
    try:
        if workspace_env.exists():
            _apply_dotenv(workspace_env, override=True)
    except PermissionError as exc:
        raise RuntimeError(
            f"Permission denied reading workspace .env at '{workspace_env}'. "
            "Ensure the file is readable by the current process user."
        ) from exc

    # Keep provider alias env vars in sync so third-party libraries that only
    # understand one spelling still receive the configured credential.
    google_key = os.environ.get("GOOGLE_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if google_key and not gemini_key:
        os.environ["GEMINI_API_KEY"] = google_key
    elif gemini_key and not google_key:
        os.environ["GOOGLE_API_KEY"] = gemini_key


def normalize_model_identifier(raw: str) -> str:
    cleaned = raw.strip().strip('"').strip("'")
    if not cleaned:
        raise EnvConfigError("Model identifier cannot be empty.")

    alias_key = cleaned.lower()
    resolved = _MODEL_ID_ALIASES.get(alias_key)
    if resolved is not None:
        return resolved

    supported = ", ".join(sorted(entry.logical_id for entry in MODEL_CATALOG))
    raise EnvConfigError(
        f"Unknown model identifier '{cleaned}'. Supported values: {supported}"
    )


def _parse_dotenv_occurrences(path: Path) -> dict[str, list[_EnvOccurrence]]:
    occurrences: dict[str, list[_EnvOccurrence]] = {}
    if not path.exists():
        return occurrences

    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        occurrences.setdefault(key, []).append(
            _EnvOccurrence(key=key, value=value, line_number=line_number, path=path)
        )
    return occurrences


def _validate_duplicate_keys(path: Path) -> tuple[str, ...]:
    warnings: list[str] = []
    for key, records in _parse_dotenv_occurrences(path).items():
        if len(records) <= 1:
            continue

        values = [record.value for record in records]
        line_numbers = [str(record.line_number) for record in records]
        if all(value == values[0] for value in values[1:]):
            warnings.append(
                f"Duplicate .env key '{key}' in {path} at lines {', '.join(line_numbers)} "
                f"uses identical values (length={len(values[0])}); last definition wins."
            )
            continue

        lengths = ", ".join(str(len(value)) for value in values)
        raise EnvConfigError(
            f"Conflicting duplicate .env key '{key}' in {path} at lines "
            f"{', '.join(line_numbers)}. Value lengths: {lengths}."
        )
    return tuple(warnings)


def _collect_dotenv_occurrences(
    paths: Sequence[Path],
) -> dict[str, list[_EnvOccurrence]]:
    occurrences: dict[str, list[_EnvOccurrence]] = {}
    for path in paths:
        for key, records in _parse_dotenv_occurrences(path).items():
            occurrences.setdefault(key, []).extend(records)
    return occurrences


def _resolve_alias_value(
    canonical: str,
    aliases: Sequence[str],
) -> tuple[str | None, tuple[str, ...]]:
    warnings: list[str] = []
    raw_canonical_value = os.environ.get(canonical, "").strip()
    canonical_value = (
        raw_canonical_value if _is_configured_env_value(raw_canonical_value) else ""
    )
    alias_values = {
        alias: os.environ.get(alias, "").strip()
        for alias in aliases
        if _is_configured_env_value(os.environ.get(alias, "").strip())
    }

    if canonical_value:
        for alias in aliases:
            alias_value = os.environ.get(alias, "").strip()
            if not alias_value:
                continue
            if not _is_configured_env_value(alias_value):
                warnings.append(
                    f"Alias '{alias}' uses a placeholder value; using canonical '{canonical}'."
                )
                os.environ[alias] = canonical_value
                continue
            if alias_value != canonical_value:
                warnings.append(
                    f"Alias '{alias}' conflicts with canonical '{canonical}'; using '{canonical}'."
                )
                os.environ[alias] = canonical_value
                continue
            os.environ[alias] = canonical_value
        os.environ[canonical] = canonical_value
        return canonical_value, tuple(warnings)

    if not alias_values:
        return None, tuple(warnings)

    alias, alias_value = next(iter(alias_values.items()))
    for other_alias, other_value in list(alias_values.items())[1:]:
        if other_value != alias_value:
            warnings.append(
                f"Alias '{other_alias}' conflicts with '{alias}'; using '{alias}' for canonical '{canonical}'."
            )
            os.environ[other_alias] = alias_value
    os.environ[canonical] = alias_value
    warnings.append(f"Alias '{alias}' normalized to canonical '{canonical}'.")
    return alias_value, tuple(warnings)


def _normalize_base_urls() -> tuple[str, ...]:
    warnings: list[str] = []
    for key in _BASE_URL_KEYS:
        value = os.environ.get(key, "").strip()
        if not value:
            continue
        normalized = value.rstrip("/")
        if normalized != value:
            os.environ[key] = normalized
    return tuple(warnings)


def _discover_configured_providers(
    occurrences: dict[str, list[_EnvOccurrence]],
    active_provider_groups: set[str],
) -> tuple[ConfiguredProviderInventory, ...]:
    providers: list[ConfiguredProviderInventory] = []
    for spec in _PROVIDER_ENV_SPECS:
        api_key_value = (
            os.environ.get(spec.api_key_env, "").strip()
            if spec.api_key_env is not None
            else ""
        )
        base_url_value = (
            os.environ.get(spec.base_url_env, "").strip()
            if spec.base_url_env is not None
            else ""
        )
        configured_api_key_keys = (
            _configured_occurrence_keys(occurrences, spec.api_key_env)
            if spec.api_key_env is not None
            else ()
        )
        configured_base_url_keys = (
            _configured_occurrence_keys(occurrences, spec.base_url_env)
            if spec.base_url_env is not None
            else ()
        )
        is_explicitly_configured = bool(configured_api_key_keys or configured_base_url_keys)
        if not is_explicitly_configured and spec.provider_group not in active_provider_groups:
            continue
        providers.append(
            ConfiguredProviderInventory(
                provider_group=spec.provider_group,
                api_key_env=spec.api_key_env,
                configured_api_key_keys=configured_api_key_keys,
                api_key_configured=(
                    True
                    if spec.api_key_env is None
                    else _is_configured_env_value(api_key_value)
                ),
                base_url_env=spec.base_url_env,
                configured_base_url_keys=configured_base_url_keys,
                resolved_base_url=(
                    base_url_value.rstrip("/")
                    if _is_configured_env_value(base_url_value)
                    else spec.canonical_base_url
                ),
                canonical_base_url=spec.canonical_base_url,
            )
        )
    return tuple(providers)


def _parse_optional_positive_int(key: str) -> int | None:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise EnvConfigError(f"{key} must be a positive integer when set.") from exc
    if value <= 0:
        raise EnvConfigError(f"{key} must be a positive integer when set.")
    return value


def _resolve_tier(
    *,
    tier_name: str,
    env_key: str | None,
    fallback_env_key: str | None,
    override_model_id: str | None,
    default_logical_id: str,
    fallback_logical_id: str,
) -> ResolvedTierSelection:
    actual_fallback = fallback_logical_id
    fallback_source = "catalog_default"
    if fallback_env_key:
        raw_fallback = os.environ.get(fallback_env_key, "").strip()
        if raw_fallback:
            actual_fallback = normalize_model_identifier(raw_fallback)
            fallback_source = fallback_env_key

    if env_key:
        raw_from_env = os.environ.get(env_key, "").strip()
        if raw_from_env:
            return ResolvedTierSelection(
                tier_name=tier_name,
                primary_logical_id=normalize_model_identifier(raw_from_env),
                fallback_logical_id=actual_fallback,
                primary_source=env_key,
                fallback_source=fallback_source,
            )

    if override_model_id:
        return ResolvedTierSelection(
            tier_name=tier_name,
            primary_logical_id=normalize_model_identifier(override_model_id),
            fallback_logical_id=actual_fallback,
            primary_source="PRIMARY_LLM_OVERRIDE",
            fallback_source=fallback_source,
        )

    return ResolvedTierSelection(
        tier_name=tier_name,
        primary_logical_id=default_logical_id,
        fallback_logical_id=actual_fallback,
        primary_source="catalog_default",
        fallback_source=fallback_source,
    )


def _active_provider_env_keys(resolved: ResolvedRuntimeEnv) -> tuple[str, ...]:
    keys: list[str] = []
    seen: set[str] = set()
    for logical_id in resolved.active_model_logical_ids():
        entry = get_model_entry(logical_id)
        api_key_env = (
            "GOOGLE_API_KEY"
            if entry.crewai_model.startswith("gemini/")
            else entry.api_key_env
        )
        if api_key_env and api_key_env not in seen:
            seen.add(api_key_env)
            keys.append(api_key_env)
        if entry.base_url_env and entry.base_url_env not in seen:
            seen.add(entry.base_url_env)
            keys.append(entry.base_url_env)
    return tuple(keys)


def _dotenv_paths(
    workspace_dir: Path | None,
    project_root: Path | None,
) -> tuple[Path, ...]:
    dotenv_paths: list[Path] = []
    if project_root is not None:
        dotenv_paths.append(project_root / ".env")
    if workspace_dir is not None:
        workspace_env = workspace_dir / ".env"
        if workspace_env not in dotenv_paths:
            dotenv_paths.append(workspace_env)
    return tuple(dotenv_paths)


def _resolve_runtime_env_internal(
    *,
    workspace_dir: Path | None,
    project_root: Path | None,
    primary_model_id_override: str | None,
    parse_env_files: bool,
) -> ResolvedRuntimeEnv:
    warnings: list[str] = []
    dotenv_paths = _dotenv_paths(workspace_dir, project_root)
    dotenv_occurrences: dict[str, list[_EnvOccurrence]] = {}

    if parse_env_files:
        for dotenv_path in dotenv_paths:
            warnings.extend(_validate_duplicate_keys(dotenv_path))
        dotenv_occurrences = _collect_dotenv_occurrences(dotenv_paths)

    for canonical, aliases in _ENV_ALIAS_MAP.items():
        _, alias_warnings = _resolve_alias_value(canonical, aliases)
        warnings.extend(alias_warnings)

    warnings.extend(_normalize_base_urls())

    orchestration_override = (
        primary_model_id_override or os.environ.get("PRIMARY_LLM", "").strip()
    )
    orchestration = _resolve_tier(
        tier_name="orchestration",
        env_key="ORCHESTRATION_MODEL",
        fallback_env_key="ORCHESTRATION_MODEL_FALLBACK",
        override_model_id=orchestration_override,
        default_logical_id=DEFAULT_ORCHESTRATION_MODEL,
        fallback_logical_id=DEFAULT_ORCHESTRATION_FALLBACK_MODEL,
    )
    level1 = _resolve_tier(
        tier_name="level1",
        env_key="L1_MODEL",
        fallback_env_key="L1_MODEL_FALLBACK",
        override_model_id=None,
        default_logical_id=DEFAULT_LEVEL1_MODEL,
        fallback_logical_id=DEFAULT_LEVEL1_FALLBACK_MODEL,
    )
    level2 = _resolve_tier(
        tier_name="level2",
        env_key="L2_MODEL",
        fallback_env_key="L2_MODEL_FALLBACK",
        override_model_id=None,
        default_logical_id=DEFAULT_LEVEL2_MODEL,
        fallback_logical_id=DEFAULT_LEVEL2_FALLBACK_MODEL,
    )
    level3 = _resolve_tier(
        tier_name="level3",
        env_key="L3_MODEL",
        fallback_env_key="L3_MODEL_FALLBACK",
        override_model_id=None,
        default_logical_id=DEFAULT_LEVEL3_MODEL,
        fallback_logical_id=DEFAULT_LEVEL3_FALLBACK_MODEL,
    )

    resolved = ResolvedRuntimeEnv(
        workspace_dir=workspace_dir,
        project_root=project_root,
        orchestration=orchestration,
        level1=level1,
        level2=level2,
        level3=level3,
        swarm=ResolvedSwarmConfig(
            level2=_parse_optional_positive_int("L2_AGENT_SWARMS"),
            level3=_parse_optional_positive_int("L3_AGENT_SWARMS"),
        ),
        warnings=collect_env_warnings(warnings),
        active_provider_env_keys=(),
    )

    return ResolvedRuntimeEnv(
        workspace_dir=resolved.workspace_dir,
        project_root=resolved.project_root,
        orchestration=resolved.orchestration,
        level1=resolved.level1,
        level2=resolved.level2,
        level3=resolved.level3,
        swarm=resolved.swarm,
        warnings=resolved.warnings,
        active_provider_env_keys=_active_provider_env_keys(resolved),
        configured_providers=_discover_configured_providers(
            dotenv_occurrences,
            {
                get_model_entry(logical_id).provider_group
                for logical_id in resolved.active_model_logical_ids()
            },
        ),
    )


def resolve_runtime_env(
    workspace_dir: str | Path,
    project_root: str | Path | None = None,
    *,
    primary_model_id_override: str | None = None,
) -> ResolvedRuntimeEnv:
    workspace_path = Path(workspace_dir).resolve()
    project_root_path = (
        Path(project_root).resolve() if project_root is not None else None
    )
    load_workspace_env(workspace_path, project_root=project_root_path)
    return _resolve_runtime_env_internal(
        workspace_dir=workspace_path,
        project_root=project_root_path,
        primary_model_id_override=primary_model_id_override,
        parse_env_files=True,
    )


def resolve_runtime_env_from_environ(
    *,
    primary_model_id_override: str | None = None,
) -> ResolvedRuntimeEnv:
    return _resolve_runtime_env_internal(
        workspace_dir=None,
        project_root=None,
        primary_model_id_override=primary_model_id_override,
        parse_env_files=False,
    )


def discover_configured_providers(
    workspace_dir: str | Path,
    *,
    project_root: str | Path | None = None,
) -> tuple[ConfiguredProviderInventory, ...]:
    return resolve_runtime_env(
        workspace_dir,
        project_root=project_root,
    ).configured_providers
