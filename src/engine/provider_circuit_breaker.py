from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock

logger = logging.getLogger("ProviderCircuitBreaker")


@dataclass
class _ProviderState:
    consecutive_failures: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False


class ProviderCircuitBreaker:
    """Cross-stage circuit breaker that prevents redundant calls to failing providers.

    States:
      - CLOSED: normal operation, requests pass through.
      - OPEN: provider is considered down; calls are rejected immediately.
      - HALF-OPEN: after recovery_window_seconds, a single probe call is allowed.

    Thread-safe for use across concurrent pipeline stages.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_window_seconds: float = 60.0,
    ):
        self._failure_threshold = failure_threshold
        self._recovery_window = recovery_window_seconds
        self._providers: dict[str, _ProviderState] = {}
        self._lock = Lock()

    def _get_state(self, provider_key: str) -> _ProviderState:
        if provider_key not in self._providers:
            self._providers[provider_key] = _ProviderState()
        return self._providers[provider_key]

    def is_available(self, provider_key: str) -> bool:
        """Check whether the provider circuit is closed or half-open (probe allowed)."""
        with self._lock:
            state = self._get_state(provider_key)
            if not state.is_open:
                return True
            elapsed = time.monotonic() - state.last_failure_time
            if elapsed >= self._recovery_window:
                logger.info(
                    f"Circuit half-open for '{provider_key}' after "
                    f"{elapsed:.1f}s. Allowing probe request."
                )
                return True
            return False

    def record_success(self, provider_key: str) -> None:
        """Reset the circuit to CLOSED after a successful call."""
        with self._lock:
            state = self._get_state(provider_key)
            if state.consecutive_failures > 0 or state.is_open:
                logger.info(f"Circuit closed for '{provider_key}' after successful call.")
            state.consecutive_failures = 0
            state.is_open = False
            state.last_failure_time = 0.0

    def record_failure(self, provider_key: str) -> None:
        """Increment failure count and open the circuit if threshold is breached."""
        with self._lock:
            state = self._get_state(provider_key)
            state.consecutive_failures += 1
            state.last_failure_time = time.monotonic()
            if state.consecutive_failures >= self._failure_threshold:
                if not state.is_open:
                    logger.warning(
                        f"Circuit OPEN for '{provider_key}' after "
                        f"{state.consecutive_failures} consecutive failures. "
                        f"Blocking for {self._recovery_window}s."
                    )
                state.is_open = True

    def get_status(self) -> dict[str, dict[str, object]]:
        """Return a snapshot of all tracked provider circuit states."""
        with self._lock:
            return {
                key: {
                    "consecutive_failures": s.consecutive_failures,
                    "is_open": s.is_open,
                    "seconds_since_last_failure": (
                        round(time.monotonic() - s.last_failure_time, 2)
                        if s.last_failure_time > 0
                        else None
                    ),
                }
                for key, s in self._providers.items()
            }
