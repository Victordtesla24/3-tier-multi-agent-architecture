from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCatalogEntry:
    display_label: str
    logical_id: str
    crewai_model: str
    provider_group: str
    api_key_env: str | None
    base_url_env: str | None = None
    default_base_url: str | None = None
    requested_thinking: str | None = None
    runtime_reasoning_effort: str | None = None
    requested_temperature: float | None = None
    selectable_as_primary: bool = True


MODEL_CATALOG: tuple[ModelCatalogEntry, ...] = (
    ModelCatalogEntry(
        display_label="OpenAI GPT-5.4 (Latest Flagship)",
        logical_id="openai/gpt-5.4",
        crewai_model="openai/gpt-5.4",
        provider_group="OpenAI",
        api_key_env="OPENAI_API_KEY",
        requested_thinking="xHigh",
        runtime_reasoning_effort="high",
        requested_temperature=0.15,
    ),
    ModelCatalogEntry(
        display_label="OpenAI GPT-5.2 Codex (Coding Specialist)",
        logical_id="openai/gpt-5.2-codex",
        crewai_model="openai/gpt-5.2-codex",
        provider_group="OpenAI",
        api_key_env="OPENAI_API_KEY",
        requested_thinking="xHigh",
        runtime_reasoning_effort="high",
        requested_temperature=0.15,
    ),
    ModelCatalogEntry(
        display_label="Google Gemini 3.1 Pro Preview (Reasoning)",
        logical_id="gemini/gemini-3.1-pro-preview",
        crewai_model="gemini/gemini-3.1-pro-preview",
        provider_group="Google AI",
        api_key_env="GOOGLE_API_KEY",
        requested_thinking="High",
        requested_temperature=0.15,
    ),
    ModelCatalogEntry(
        display_label="DeepSeek Chat (Reasoning/Coding)",
        logical_id="deepseek/deepseek-chat",
        crewai_model="deepseek/deepseek-chat",
        provider_group="DeepSeek",
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_BASE_URL",
        default_base_url="https://api.deepseek.com/v1",
        requested_thinking="High",
        requested_temperature=0.15,
    ),
    ModelCatalogEntry(
        display_label="Ollama Qwen 3 14B (Reasoning)",
        logical_id="ollama/qwen3:14b",
        crewai_model="ollama/qwen3:14b",
        provider_group="Ollama",
        api_key_env=None,
        base_url_env="OLLAMA_BASE_URL",
        default_base_url="http://127.0.0.1:11434",
        requested_thinking="High",
        requested_temperature=0.15,
    ),
    ModelCatalogEntry(
        display_label="Ollama Qwen 3 8B (Balanced)",
        logical_id="ollama/qwen3:8b",
        crewai_model="ollama/qwen3:8b",
        provider_group="Ollama",
        api_key_env=None,
        base_url_env="OLLAMA_BASE_URL",
        default_base_url="http://127.0.0.1:11434",
        requested_thinking="High",
        requested_temperature=0.15,
    ),
    ModelCatalogEntry(
        display_label="Ollama Qwen 2.5 Coder 14B (Coding)",
        logical_id="ollama/qwen2.5-coder:14b",
        crewai_model="ollama/qwen2.5-coder:14b",
        provider_group="Ollama",
        api_key_env=None,
        base_url_env="OLLAMA_BASE_URL",
        default_base_url="http://127.0.0.1:11434",
        requested_thinking="High",
        requested_temperature=0.15,
    ),
    ModelCatalogEntry(
        display_label="Ollama Qwen 2.5 Coder 7B (Lightweight Coding)",
        logical_id="ollama/qwen2.5-coder:7b",
        crewai_model="ollama/qwen2.5-coder:7b",
        provider_group="Ollama",
        api_key_env=None,
        base_url_env="OLLAMA_BASE_URL",
        default_base_url="http://127.0.0.1:11434",
        requested_thinking="High",
        requested_temperature=0.15,
    ),
)

PRIMARY_PROVIDER_GROUPS: tuple[str, ...] = (
    "OpenAI",
    "Google AI",
    "DeepSeek",
    "Ollama",
)

DEFAULT_ORCHESTRATION_MODEL = "openai/gpt-5.4"
DEFAULT_ORCHESTRATION_FALLBACK_MODEL = "openai/gpt-5.2-codex"
DEFAULT_LEVEL1_MODEL = "gemini/gemini-3.1-pro-preview"
DEFAULT_LEVEL1_FALLBACK_MODEL = "ollama/qwen3:14b"
DEFAULT_LEVEL2_MODEL = "ollama/qwen3:8b"
DEFAULT_LEVEL2_FALLBACK_MODEL = "ollama/qwen3:14b"
DEFAULT_LEVEL3_MODEL = "ollama/qwen2.5-coder:7b"
DEFAULT_LEVEL3_FALLBACK_MODEL = "ollama/qwen2.5-coder:14b"
DEFAULT_L2_AGENT_SWARMS = 2
DEFAULT_L3_AGENT_SWARMS = 3

_ENTRY_BY_LOGICAL_ID = {entry.logical_id: entry for entry in MODEL_CATALOG}


def get_model_entry(logical_id: str) -> ModelCatalogEntry:
    try:
        return _ENTRY_BY_LOGICAL_ID[logical_id]
    except KeyError as exc:
        supported = ", ".join(sorted(_ENTRY_BY_LOGICAL_ID))
        raise KeyError(
            f"Unknown model logical_id='{logical_id}'. Supported: {supported}"
        ) from exc


def iter_primary_model_entries() -> tuple[ModelCatalogEntry, ...]:
    return tuple(entry for entry in MODEL_CATALOG if entry.selectable_as_primary)


def iter_primary_entries_by_group() -> (
    tuple[tuple[str, tuple[ModelCatalogEntry, ...]], ...]
):
    grouped: list[tuple[str, tuple[ModelCatalogEntry, ...]]] = []
    primary_entries = iter_primary_model_entries()
    for group in PRIMARY_PROVIDER_GROUPS:
        members = tuple(
            entry for entry in primary_entries if entry.provider_group == group
        )
        if members:
            grouped.append((group, members))
    return tuple(grouped)


def catalog_rows() -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for entry in iter_primary_model_entries():
        rows.append(
            {
                "display_label": entry.display_label,
                "logical_id": entry.logical_id,
                "crewai_model": entry.crewai_model,
                "provider_group": entry.provider_group,
                "api_key_env": entry.api_key_env or "",
                "base_url_env": entry.base_url_env or "",
                "default_base_url": entry.default_base_url or "",
                "requested_thinking": entry.requested_thinking or "",
                "runtime_reasoning_effort": entry.runtime_reasoning_effort or "",
                "requested_temperature": (
                    f"{entry.requested_temperature:.2f}"
                    if entry.requested_temperature is not None
                    else ""
                ),
            }
        )
    return tuple(rows)


def default_runtime_notes(logical_id: str) -> tuple[str, ...]:
    entry = get_model_entry(logical_id)
    notes: list[str] = []
    if entry.logical_id.startswith("openai/gpt-5"):
        notes.append(
            "Requested thinking=xHigh normalizes to runtime reasoning_effort=high "
            "because the installed CrewAI/LiteLLM surface exposes low|medium|high."
        )
        notes.append(
            "Requested temperature=0.15 is omitted at runtime for GPT-5 family models "
            "because OpenAI GPT-5 reasoning models reject temperature."
        )
    elif entry.logical_id.startswith("gemini/gemini-3"):
        notes.append(
            "Requested thinking=High relies on Gemini 3 default high thinking because "
            "the current CrewAI integration does not expose thinkingLevel directly."
        )
        notes.append("Requested temperature=0.15 is applied at runtime.")
    elif entry.provider_group == "DeepSeek":
        notes.append(
            "Runs against the official DeepSeek OpenAI-compatible API using "
            "DEEPSEEK_API_KEY and DEEPSEEK_BASE_URL."
        )
        notes.append(
            "Requested thinking is satisfied by model/runtime defaults; no "
            "provider-specific reasoning_effort parameter is injected."
        )
        if entry.requested_temperature is not None:
            notes.append(
                f"Requested temperature={entry.requested_temperature:.2f} is applied at runtime."
            )
    elif entry.provider_group == "Ollama":
        notes.append(
            "Runs through the local Ollama runtime over OLLAMA_BASE_URL and does not "
            "require an API key."
        )
        notes.append(
            "Requested thinking is satisfied by the model/runtime defaults; no "
            "provider-specific reasoning_effort parameter is injected."
        )
        if entry.requested_temperature is not None:
            notes.append(
                f"Requested temperature={entry.requested_temperature:.2f} is applied at runtime."
            )
    elif entry.runtime_reasoning_effort:
        notes.append(
            f"Requested thinking={entry.requested_thinking} maps to "
            f"runtime reasoning_effort={entry.runtime_reasoning_effort}."
        )
        if entry.requested_temperature is not None:
            notes.append(
                f"Requested temperature={entry.requested_temperature:.2f} is applied at runtime."
            )
    return tuple(notes)


def active_matrix_logical_ids(primary_model_id: str | None = None) -> tuple[str, ...]:
    return (
        primary_model_id or DEFAULT_ORCHESTRATION_MODEL,
        DEFAULT_ORCHESTRATION_FALLBACK_MODEL,
        DEFAULT_LEVEL1_MODEL,
        DEFAULT_LEVEL1_FALLBACK_MODEL,
        DEFAULT_LEVEL2_MODEL,
        DEFAULT_LEVEL2_FALLBACK_MODEL,
        DEFAULT_LEVEL3_MODEL,
        DEFAULT_LEVEL3_FALLBACK_MODEL,
    )


def active_matrix_env_defaults(
    primary_model_id: str | None = None,
) -> tuple[tuple[str, str], ...]:
    defaults: list[tuple[str, str]] = []
    seen: set[str] = set()
    placeholder_by_key = {
        "GOOGLE_API_KEY": "your_google_api_key_here",
        "OPENAI_API_KEY": "your_openai_api_key_here",
        "DEEPSEEK_API_KEY": "your_deepseek_api_key_here",
        "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
    }

    selected_primary = primary_model_id or DEFAULT_ORCHESTRATION_MODEL
    selected_level_model = primary_model_id or None

    tier_defaults = (
        ("PRIMARY_LLM", selected_primary),
        ("ORCHESTRATION_MODEL", selected_primary),
        ("L1_MODEL", selected_level_model or DEFAULT_LEVEL1_MODEL),
        ("L2_MODEL", selected_level_model or DEFAULT_LEVEL2_MODEL),
        ("L3_MODEL", selected_level_model or DEFAULT_LEVEL3_MODEL),
        ("L2_AGENT_SWARMS", str(DEFAULT_L2_AGENT_SWARMS)),
        ("L3_AGENT_SWARMS", str(DEFAULT_L3_AGENT_SWARMS)),
    )
    for key, value in tier_defaults:
        if key not in seen:
            seen.add(key)
            defaults.append((key, value))

    for logical_id in active_matrix_logical_ids(primary_model_id):
        entry = get_model_entry(logical_id)
        if entry.api_key_env and entry.api_key_env not in seen:
            seen.add(entry.api_key_env)
            defaults.append((entry.api_key_env, placeholder_by_key[entry.api_key_env]))
        if entry.base_url_env and entry.base_url_env not in seen:
            seen.add(entry.base_url_env)
            defaults.append(
                (
                    entry.base_url_env,
                    entry.default_base_url or placeholder_by_key[entry.base_url_env],
                )
            )
    return tuple(defaults)
