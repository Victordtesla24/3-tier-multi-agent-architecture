from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from pathlib import Path


_LANGUAGE_BY_SUFFIX = {
    ".py": "Python",
    ".md": "Markdown",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".sh": "Shell",
    ".dockerfile": "Dockerfile",
}

_SCAN_EXCLUDED_DIRS = {
    ".git",
    ".agent",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    ".tox",
    ".idea",
    ".vscode",
    "build",
    "dist",
    "workspaces",
}


def _run_git(project_root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _detect_primary_languages(project_root: Path, limit: int = 5000) -> list[str]:
    counts: Counter[str] = Counter()
    scanned = 0

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [directory for directory in dirs if directory not in _SCAN_EXCLUDED_DIRS]
        for file_name in files:
            if scanned >= limit:
                break
            path = Path(root) / file_name
            suffix = path.suffix.lower()
            language = _LANGUAGE_BY_SUFFIX.get(suffix)
            if language is None and path.name.lower() == "dockerfile":
                language = "Dockerfile"
            if language:
                counts[language] += 1
            scanned += 1
        if scanned >= limit:
            break

    return [name for name, _count in counts.most_common(4)]


def _existing_paths(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths if path.exists()]


def _capability_mapping_lines() -> list[str]:
    return [
        "- workspace_file_read/workspace_file_write -> Read and write repository files under workspace root.",
        "- project_root_file_read/project_root_file_write -> Maintain architecture/rules/reports/benchmark governance docs.",
        "- run_tests/run_benchmarks -> Execute validation and performance verification commands.",
        "- read_runtime_configuration/update_runtime_configuration -> Inspect and update active runtime .env keys.",
        "- acknowledge_ui_action -> Mutate shared A2UI state at /ack_event_01/visibility.",
        "- submit_objective -> Programmatically submit an objective/prompt into orchestration.",
        "- complete_task -> Emit deterministic completion signal (success|partial|blocked).",
    ]


def _read_recent_execution_events(workspace: Path, max_events: int = 5) -> list[str]:
    log_file = workspace / ".agent" / "memory" / "execution_log.json"
    if not log_file.exists():
        return ["- No execution log found."]

    try:
        payload = json.loads(log_file.read_text(encoding="utf-8"))
    except Exception:
        return ["- Execution log exists but could not be parsed."]

    events = payload.get("executions", [])
    if not isinstance(events, list) or not events:
        return ["- No prior execution events."]

    lines: list[str] = []
    for item in events[-max_events:]:
        timestamp = str(item.get("timestamp", "unknown-time"))
        state = str(item.get("state", "unknown-state"))
        event = str(item.get("event", "unknown-event"))
        lines.append(f"- {timestamp} | {state} | {event}")
    return lines


def _read_memory_highlights(workspace: Path) -> list[str]:
    files = [
        workspace / ".agent" / "memory" / "l1-memory.md",
        workspace / ".agent" / "memory" / "l2-memory.md",
        workspace / ".agent" / "memory" / "improvement-notes.md",
    ]
    highlights: list[str] = []
    for file_path in files:
        if not file_path.exists():
            continue
        lines = [
            line.strip()
            for line in file_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not lines:
            continue
        snippet = " ".join(lines[:2])[:240]
        highlights.append(f"- {file_path.name}: {snippet}")

    if not highlights:
        return ["- No l1/l2 memory summaries found."]
    return highlights


def build_orchestration_context_block(
    *,
    workspace: Path,
    project_root: Path,
    strict_provider_validation: bool,
    max_provider_4xx: int,
    fail_on_research_empty: bool,
) -> str:
    """
    Build a deterministic markdown context block for manager-task kickoff.
    """
    workspace = workspace.resolve()
    project_root = project_root.resolve()

    git_branch = _run_git(project_root, ["branch", "--show-current"])
    git_dirty = _run_git(project_root, ["status", "--porcelain"])
    primary_languages = _detect_primary_languages(project_root)

    notable_docs = _existing_paths(
        [
            project_root / "docs" / "architecture" / "multi-agent-3-level-architecture.md",
            project_root / "docs" / "architecture" / "prompt-reconstruction.md",
            project_root / "docs" / "reports" / "improvement_plan.md",
            project_root / "docs" / "reports" / "critical_analysis_report.md",
            project_root / "docs" / "reports" / "Test_Summary_Report.md",
            project_root / "docs" / "benchmarks" / "latest_results.md",
        ]
    )
    key_subdirs = _existing_paths(
        [
            workspace / ".agent" / "tmp",
            workspace / ".agent" / "memory",
            workspace / "docs",
            workspace / "src",
        ]
    )
    entry_scripts = _existing_paths(
        [
            project_root / "src" / "orchestrator" / "antigravity-cli.py",
            project_root / "benchmarks" / "run_benchmark.py",
        ]
    )

    lines: list[str] = []
    lines.append("## Environment Snapshot")
    lines.append(f"- Workspace: {workspace}")
    lines.append(f"- Project root: {project_root}")
    lines.append(f"- Git branch: {git_branch or 'unknown'}")
    lines.append(f"- Git dirty: {'yes' if bool(git_dirty) else 'no'}")
    lines.append(
        f"- Primary languages: {', '.join(primary_languages) if primary_languages else 'unknown'}"
    )
    lines.append(
        f"- Main entry scripts: {', '.join(entry_scripts) if entry_scripts else 'none detected'}"
    )
    lines.append("")
    lines.append("## Constraints & Preferences")
    lines.append(f"- strict_provider_validation: {strict_provider_validation}")
    lines.append(f"- max_provider_4xx: {max_provider_4xx}")
    lines.append(f"- fail_on_research_empty: {fail_on_research_empty}")
    lines.append("")
    lines.append("## Workspace Context")
    lines.append(
        f"- Key subdirectories: {', '.join(key_subdirs) if key_subdirs else 'none detected'}"
    )
    lines.append(
        f"- Notable docs: {', '.join(notable_docs) if notable_docs else 'none detected'}"
    )
    lines.append(
        "- Planning context sources: docs/architecture/*, docs/reports/*, docs/benchmarks/*"
    )
    lines.append("")
    lines.append("## Available Resources & Capabilities")
    lines.append(
        f"- Key files: {', '.join(notable_docs) if notable_docs else 'none detected'}"
    )
    lines.append(
        "- Actionable nouns: workspace files, architecture docs, reports, benchmarks, runtime config, tests, A2UI action state."
    )
    lines.append("- Tool-to-domain mapping:")
    lines.extend(_capability_mapping_lines())
    lines.append("")
    lines.append("## Recent Execution Activity")
    lines.extend(_read_recent_execution_events(workspace))
    lines.append("")
    lines.append("## Memory Highlights")
    lines.extend(_read_memory_highlights(workspace))

    return "\n".join(lines).strip() + "\n"
