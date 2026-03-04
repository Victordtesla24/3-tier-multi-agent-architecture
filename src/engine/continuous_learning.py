from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_execution_log(log_path: Path) -> Dict[str, Any]:
    if not log_path.exists():
        return {"executions": []}
    try:
        return json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        return {"executions": []}


def _summarise_executions(executions: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
    run_count = len(executions)
    states: List[str] = []
    for item in executions[-10:]:
        state = str(item.get("state", "unknown-state"))
        event = str(item.get("event", "unknown-event"))
        states.append(f"- {state}: {event}")
    return run_count, states


def generate_improvement_proposal(workspace: Path) -> str:
    """
    Build a structured WHAT/WHY/HOW improvement proposal from the execution log.
    """
    workspace = workspace.resolve()
    log_path = workspace / ".agent" / "memory" / "execution_log.json"
    payload = _load_execution_log(log_path)
    executions = payload.get("executions", [])
    if not isinstance(executions, list):
        executions = []

    run_count, recent_states = _summarise_executions(executions)

    what_lines = [
        f"- Observed {run_count} recorded pipeline execution(s) in this workspace.",
    ]
    if recent_states:
        what_lines.append("- Recent execution states:")
        what_lines.extend(recent_states)

    why_lines = [
        "- Consolidating recent execution behaviour helps the orchestration tier "
        "reason about recurring failure modes and verification outcomes.",
        "- Capturing these notes as markdown keeps them available to future runs "
        "without changing core engine logic.",
    ]

    how_lines = [
        "- Use these notes as input when refining prompts, model choices, or "
        "tooling contracts.",
        "- When specific states repeatedly appear before failures, consider "
        "tightening verification or adding targeted health checks around them.",
    ]

    proposal = [
        "# Continuous Improvement Proposal",
        "",
        "## WHAT",
        *what_lines,
        "",
        "## WHY",
        *why_lines,
        "",
        "## HOW",
        *how_lines,
        "",
    ]
    return "\n".join(proposal)


_EXPECTED_APPROVAL_TOKEN = "AG-APPLY-IMPROVEMENT"


def apply_architecture_upgrade(
    workspace: Path,
    proposal_markdown: str,
    *,
    approval_token: str,
) -> Path | None:
    """
    Gated application of an architecture improvement proposal.

    The proposal is only persisted if the caller provides the expected approval
    token. This keeps the engine deterministic while allowing the host surface
    (CLI, MCP, or UI) to control when upgrades are accepted.
    """
    if not approval_token or approval_token != _EXPECTED_APPROVAL_TOKEN:
        # Intentionally no write without an explicit, correct token.
        return None

    workspace = workspace.resolve()
    target = workspace / ".agent" / "memory" / "improvement-notes.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(proposal_markdown, encoding="utf-8")
    return target

