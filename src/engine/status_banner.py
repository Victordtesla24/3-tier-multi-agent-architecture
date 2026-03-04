"""Canonical status banner for runtime/chat initialization surfaces."""

STATUS_BANNER = "3-tier-multi-agent-architecture Status: ON 🟢"


def emit_status_banner() -> None:
    """Print the canonical runtime status banner."""
    print(STATUS_BANNER, flush=True)
