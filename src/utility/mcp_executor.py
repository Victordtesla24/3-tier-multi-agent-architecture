"""
Enhancement 2: Fault-Tolerant MCP Utility Agent Execution Engine
Addresses Critique 2 – Brittleness in Utility Agent MCP Interoperability.

Implements a stateful Circuit Breaker pattern to protect the overall system from
external API outages, combined with an Exponential Backoff algorithm to smoothly
handle transient network limits (e.g., HTTP 429 errors).

Mathematical progression: E(t) = min(E_max, E_base * 2^n)
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict

# Configure module-level logging for Utility Execution
logger = logging.getLogger("MCP_Tier3_Executor")
logger.setLevel(logging.DEBUG)


class CircuitBreakerOpenException(Exception):
    """
    Custom exception raised when the MCP circuit breaker is in the OPEN state,
    preventing further network calls to a failing external service.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MCPUtilityExecutor:
    """
    Tier 3 Execution Engine for interacting with Model Context Protocol (MCP) servers.
    Implements a mathematically sound Exponential Backoff mechanism and a stateful
    Circuit Breaker to prevent cascading failures up to the Tier 2 Domain Agents.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout_seconds: int = 30,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = timedelta(seconds=recovery_timeout_seconds)
        self.failure_count: int = 0
        self.last_failure_time: datetime = datetime.min
        self.state: str = "CLOSED"  # Valid states: CLOSED, OPEN, HALF_OPEN

    def _check_circuit(self) -> None:
        """
        Evaluates the current state of the circuit before authorizing execution.
        Handles transitions from OPEN to HALF_OPEN based on recovery timeouts.
        """
        if self.state == "OPEN":
            elapsed = datetime.now() - self.last_failure_time
            if elapsed > self.recovery_timeout:
                logger.warning(
                    "Circuit recovery timeout reached. Transitioning: OPEN -> HALF_OPEN"
                )
                self.state = "HALF_OPEN"
            else:
                remaining = self.recovery_timeout - elapsed
                raise CircuitBreakerOpenException(
                    f"MCP Tool execution blocked. Circuit OPEN. "
                    f"Time remaining: {remaining}"
                )

    def _record_failure(self) -> None:
        """
        Increments the failure counter and trips the circuit to OPEN if the
        threshold is breached.
        """
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        logger.debug(
            f"Failure recorded. Current failure count: {self.failure_count}"
        )

        if self.failure_count >= self.failure_threshold and self.state != "OPEN":
            logger.error(
                "Failure threshold breached. "
                "Circuit transition: CLOSED/HALF_OPEN -> OPEN"
            )
            self.state = "OPEN"

    def _record_success(self) -> None:
        """
        Resets the failure counter and secures the circuit breaker upon successful
        execution.
        """
        if self.state != "CLOSED":
            logger.info(
                "Successful execution recorded. "
                "Circuit transition: HALF_OPEN -> CLOSED"
            )
        self.failure_count = 0
        self.state = "CLOSED"

    async def execute_mcp_tool(
        self,
        tool_func: Callable[..., Any],
        params: Dict[str, Any],
        max_retries: int = 4,
    ) -> Any:
        """
        Executes a deterministic Tier 3 task with robust exponential backoff.
        Implements the mathematical progression: E(t) = min(E_max, E_base * 2^n)
        """
        self._check_circuit()
        base_delay_seconds: float = 1.0
        max_delay_seconds: float = 16.0

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Executing MCP Tool '{tool_func.__name__}' | "
                    f"Attempt {attempt + 1}/{max_retries}"
                )

                # Await the target MCP network call/execution
                result = await tool_func(**params)

                # If execution completes without exception, record success and return
                self._record_success()
                return result

            except asyncio.TimeoutError as e:
                logger.warning(f"MCP Tool Execution Timeout: {e}")
                self._record_failure()
            except Exception as e:
                logger.error(f"MCP Tool Execution Error: {str(e)}")
                self._record_failure()

            # If the final attempt fails, exhaust the process
            if attempt == max_retries - 1:
                logger.critical(
                    f"MCP Tool '{tool_func.__name__}' exhausted all "
                    f"{max_retries} retries."
                )
                raise RuntimeError(
                    f"Tier 3 MCP Execution permanently failed for: "
                    f"{tool_func.__name__}"
                )

            # Calculate and apply exponential backoff before the next iteration
            delay = min(max_delay_seconds, base_delay_seconds * (2**attempt))
            logger.info(
                f"Applying exponential backoff. "
                f"Suspending task for {delay} seconds..."
            )
            await asyncio.sleep(delay)


# ==========================================
# Production Tier 3 MCP Tool: SQLite Schema Introspection
# ==========================================


async def fetch_database_schema(target_db: str) -> Dict[str, Any]:
    """
    Tier 3 MCP tool: performs real SQLite database introspection.

    Connects to the specified SQLite database file, queries the sqlite_master
    table for all user-defined tables, and returns their names.

    Raises:
        FileNotFoundError: if the database path does not exist.
        RuntimeError: if the SQLite introspection query fails.
    """
    db_path = Path(target_db)
    if not db_path.exists():
        raise FileNotFoundError(
            f"SQLite database not found at path: '{target_db}'. "
            "Ensure the path is absolute or relative to the working directory."
        )

    def _introspect() -> list[str]:
        try:
            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name;"
                )
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise RuntimeError(
                f"SQLite introspection failed for '{target_db}': {exc}"
            ) from exc

    tables = await asyncio.to_thread(_introspect)
    return {
        "status": "success",
        "schema": tables,
        "database": str(db_path.resolve()),
    }
