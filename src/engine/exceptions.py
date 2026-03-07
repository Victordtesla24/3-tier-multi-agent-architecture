from __future__ import annotations

from typing import Any


class PipelineError(Exception):
    """Base exception for all pipeline-level failures."""

    def __init__(self, message: str, *, stage: str | None = None, metadata: dict[str, Any] | None = None):
        super().__init__(message)
        self.stage = stage
        self.metadata = metadata or {}


class ProviderExhaustedError(PipelineError):
    """Raised when both primary and fallback LLM providers have failed for a stage."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        primary_error: Exception,
        fallback_error: Exception,
        tier: str = "unknown",
    ):
        super().__init__(message, stage=stage, metadata={
            "tier": tier,
            "primary_error_type": type(primary_error).__name__,
            "primary_error_msg": str(primary_error),
            "fallback_error_type": type(fallback_error).__name__,
            "fallback_error_msg": str(fallback_error),
        })
        self.primary_error = primary_error
        self.fallback_error = fallback_error
        self.tier = tier


class VerificationFailedError(PipelineError):
    """Raised when the verification agent rejects pipeline output."""

    def __init__(
        self,
        message: str,
        *,
        banned_markers: list[str] | None = None,
        syntax_errors: list[str] | None = None,
        empty_implementations: int = 0,
    ):
        super().__init__(message, stage="verification", metadata={
            "banned_markers": banned_markers or [],
            "syntax_errors": syntax_errors or [],
            "empty_implementations": empty_implementations,
        })
        self.banned_markers = banned_markers or []
        self.syntax_errors = syntax_errors or []
        self.empty_implementations = empty_implementations


class EnvironmentConfigError(PipelineError):
    """Raised when required environment variables or credentials are missing."""

    def __init__(self, message: str, *, missing_keys: list[str] | None = None):
        super().__init__(message, stage="init", metadata={
            "missing_keys": missing_keys or [],
        })
        self.missing_keys = missing_keys or []


class SoftFailureError(PipelineError):
    """Raised when an LLM returns a refusal or non-actionable response."""

    def __init__(self, message: str, *, stage: str, model: str = "unknown"):
        super().__init__(message, stage=stage, metadata={"model": model})
        self.model = model


class ResearchEmptyError(PipelineError):
    """Raised when the research stage produces no actionable content."""

    def __init__(self, message: str = "Research stage returned empty or non-actionable content."):
        super().__init__(message, stage="research")
