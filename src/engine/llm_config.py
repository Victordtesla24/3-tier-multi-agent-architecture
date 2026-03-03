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
    base_url_env: Optional[str] = None


class EnvConfigError(RuntimeError):
    pass


def load_workspace_env(workspace_dir: str | Path) -> None:
    """
    Loads .env from the workspace root if present.
    """
    p = Path(workspace_dir).resolve()
    dotenv_path = p / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path, override=False)


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
    openai_key = os.environ.get("OPENAI_API_KEY")

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
    if not openai_key:
        raise EnvConfigError("Missing OPENAI_API_KEY.")

    kwargs: dict[str, Any] = dict(
        model=spec.crewai_model,
        api_key=openai_key,
        temperature=0.2,
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


class FallbackLLM:
    """
    A strict primary→fallback wrapper implementing autonomous routing with try/except.
    Duck-type compatible with CrewAI's LLM class — exposes the same interface:
    call(), supports_function_calling(), supports_stop_words(), get_context_window_size().
    """

    def __init__(self, *, name: str, primary: LLM, fallback: LLM):
        self._name = name
        self._primary = primary
        self._fallback = fallback
        # Expose attributes that CrewAI may inspect
        self.model = name
        self.temperature = getattr(primary, "temperature", None)
        self.callbacks = getattr(primary, "callbacks", [])

    def set_callbacks(self, callbacks):
        """Propagate callback registration to both underlying LLMs."""
        self._primary.set_callbacks(callbacks)
        self._fallback.set_callbacks(callbacks)
        self.callbacks = callbacks

    def set_env_callbacks(self, callbacks):
        """Propagate env callback registration to both underlying LLMs."""
        if hasattr(self._primary, "set_env_callbacks"):
            self._primary.set_env_callbacks(callbacks)
        if hasattr(self._fallback, "set_env_callbacks"):
            self._fallback.set_env_callbacks(callbacks)

    def call(
        self,
        messages,
        tools: Optional[list[dict]] = None,
        callbacks: Optional[list[Any]] = None,
        available_functions: Optional[dict[str, Any]] = None,
    ) -> str:
        try:
            result = self._primary.call(
                messages,
                tools=tools,
                callbacks=callbacks,
                available_functions=available_functions,
            )
            # Soft-failure telemetry detection
            if not result or str(result).isspace():
                raise ValueError("Soft-Failure: Primary LLM returned empty response.")
            if "I cannot fulfill this request" in str(result) or "As an AI language model" in str(result):
                raise ValueError("Soft-Failure: Primary LLM generated a structural refusal.")
            return result
        except Exception as primary_error:
            try:
                return self._fallback.call(
                    messages,
                    tools=tools,
                    callbacks=callbacks,
                    available_functions=available_functions,
                )
            except Exception as fallback_error:
                raise RuntimeError(
                    f"LLM fallback exhausted for '{self._name}'. "
                    f"Primary failed with {type(primary_error).__name__}: {primary_error}. "
                    f"Fallback failed with {type(fallback_error).__name__}: {fallback_error}."
                ) from fallback_error

    def supports_function_calling(self) -> bool:
        sp = getattr(self._primary, "supports_function_calling", None)
        sf = getattr(self._fallback, "supports_function_calling", None)
        if callable(sp) and callable(sf):
            return bool(sp() and sf())
        return True

    def supports_stop_words(self) -> bool:
        sp = getattr(self._primary, "supports_stop_words", None)
        sf = getattr(self._fallback, "supports_stop_words", None)
        if callable(sp) and callable(sf):
            return bool(sp() and sf())
        return True

    def get_context_window_size(self) -> int:
        gp = getattr(self._primary, "get_context_window_size", None)
        if callable(gp):
            return int(gp())
        return 4096


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
    base_url_env="MINIMAX_BASE_URL",
)

L2_PRIMARY = ModelSpec(
    logical_id="MiniMax/Minimax-m2.5",
    crewai_model="openai/minimax-m2.5",
    effort=Effort.LOW,
    base_url_env="MINIMAX_BASE_URL",
)

L2_FALLBACK = ModelSpec(
    logical_id="deepseek/deepseek-v3.2",
    crewai_model="openai/deepseek-v3.2",
    effort=Effort.LOW,
    base_url_env="DEEPSEEK_BASE_URL",
)


@dataclass(frozen=True)
class ModelMatrix:
    orchestration: FallbackLLM
    level1: FallbackLLM
    level2: FallbackLLM


def build_model_matrix(workspace_dir: str | Path) -> ModelMatrix:
    load_workspace_env(workspace_dir)

    # Validate that the minimum env surface exists up-front.
    require_env(["OPENAI_API_KEY"], label="OpenAI API key")
    require_env(["GOOGLE_API_KEY", "GEMINI_API_KEY"], label="Google Gemini API key")
    require_env(["MINIMAX_BASE_URL"], label="MiniMax OpenAI-compatible base URL")
    require_env(["DEEPSEEK_BASE_URL"], label="DeepSeek OpenAI-compatible base URL")

    orch_primary = build_llm(ORCHESTRATION_PRIMARY)
    orch_fallback = build_llm(ORCHESTRATION_FALLBACK)

    l1_primary = build_llm(L1_PRIMARY)
    l1_fallback = build_llm(L1_FALLBACK)

    l2_primary = build_llm(L2_PRIMARY)
    l2_fallback = build_llm(L2_FALLBACK)

    return ModelMatrix(
        orchestration=FallbackLLM(
            name="orchestration-tier",
            primary=orch_primary,
            fallback=orch_fallback,
        ),
        level1=FallbackLLM(
            name="level1-tier",
            primary=l1_primary,
            fallback=l1_fallback,
        ),
        level2=FallbackLLM(
            name="level2-tier",
            primary=l2_primary,
            fallback=l2_fallback,
        ),
    )
