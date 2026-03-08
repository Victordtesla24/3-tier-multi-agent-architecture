from __future__ import annotations

from pathlib import Path
from typing import Callable

import re

from crewai import LLM


def load_prompt_template(
    name: str,
    *,
    workspace: Path,
    project_root: Path,
) -> str:
    """
    Load a prompt template from the architecture docs, preferring the
    repository-level docs and falling back to workspace-local copies.
    """
    candidate_paths = [
        project_root / "docs" / "architecture" / name,
        workspace / "docs" / "architecture" / name,
    ]

    for path in candidate_paths:
        if path.exists():
            return path.read_text(encoding="utf-8")

    raise FileNotFoundError(
        "Missing prompt template. "
        f"Checked: {', '.join(str(p) for p in candidate_paths)}"
    )


_SANITIZE_INJECTION_PATTERN = re.compile(
    r"(?i)\b(ignore previous instructions|you are now|system prompt|bypass|override)\b"
)
_SANITIZE_SCRIPT_PATTERN = re.compile(r"(?i)<script.*?>.*?</script>", re.DOTALL)
_INPUT_DATA_PATTERN = re.compile(
    r"<input_data>(.*?)</input_data>",
    flags=re.DOTALL | re.IGNORECASE,
)
_MARKDOWN_WRAPPED_INPUT_DATA_PATTERN = re.compile(
    r"`\s*<input_data>\s*`\s*(.*?)\s*`\s*</input_data>\s*`",
    flags=re.DOTALL | re.IGNORECASE,
)
_MARKDOWN_INPUT_DATA_PATTERN = re.compile(
    r"^##\s*Input Data\s*$\s*^```[^\n]*\n(.*?)^```",
    flags=re.DOTALL | re.IGNORECASE | re.MULTILINE,
)


def sanitize_user_input(raw_prompt: str) -> str:
    """
    Extract and sanitize user-provided payload, protecting against common
    prompt-injection and script payload patterns.
    """
    match = _INPUT_DATA_PATTERN.search(raw_prompt)
    if match is None:
        match = _MARKDOWN_WRAPPED_INPUT_DATA_PATTERN.search(raw_prompt)
    if match is None:
        match = _MARKDOWN_INPUT_DATA_PATTERN.search(raw_prompt)
    payload = match.group(1).strip() if match else raw_prompt.strip()
    # Normalize wrapped input_data variants (including backticked tag lines).
    payload = re.sub(r"(?im)^\s*`+\s*$", "", payload)
    payload = re.sub(r"(?im)^\s*`?\s*</?input_data>\s*`?\s*$", "", payload)

    sanitized = _SANITIZE_INJECTION_PATTERN.sub("[REDACTED]", payload)
    sanitized = _SANITIZE_SCRIPT_PATTERN.sub("[REMOVED SCRIPT]", sanitized)
    return sanitized.strip()


def llm_call(llm: LLM, *, runner: Callable[[LLM], str]) -> str:
    """
    Canonical primitive for invoking an LLM-backed runner.

    This keeps the call boundary explicit so orchestration layers can plug in
    telemetry, retries, or tier selection policy around a single capability.
    """
    return runner(llm)


def normalize_research_markdown(raw: str) -> str:
    """
    Normalise research agent output into the canonical markdown schema used by
    the orchestration pipeline.
    """
    body = raw.strip()
    required_markers = ("## Summary", "## Citations[]", "## MissingConfig[]", "## RiskNotes[]")
    if all(marker in body for marker in required_markers):
        return f"{body}\n"

    urls = _extract_urls(body)

    summary = body.split("\n", maxsplit=1)[0].strip()
    if not summary:
        summary = "Research agent returned empty output."

    missing_config: list[str] = []
    lowered = body.lower()
    if "missing configuration" in lowered:
        missing_config.append(body)
    if "no official or primary documentation sources were accessed" in lowered:
        missing_config.append("No primary-source citations were returned by the research agent.")

    risk_notes: list[str] = []
    if not urls:
        risk_notes.append("No citation URLs found; claims are unverifiable.")
    if "cannot provide verified constraints" in lowered:
        risk_notes.append("Research output explicitly states constraints were not verified.")

    citation_lines = "\n".join(f"- {url}" for url in urls) if urls else "- None"
    missing_lines = "\n".join(f"- {item}" for item in missing_config) if missing_config else "- None"
    risk_lines = "\n".join(f"- {item}" for item in risk_notes) if risk_notes else "- None"

    return (
        "## Summary\n"
        f"- {summary}\n\n"
        "## Citations[]\n"
        f"{citation_lines}\n\n"
        "## MissingConfig[]\n"
        f"{missing_lines}\n\n"
        "## RiskNotes[]\n"
        f"{risk_lines}\n"
    )


def _extract_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s)]+", text)
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        clean = url.rstrip(".,")
        if clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)
    return deduped


def write_workspace_file(
    workspace: Path,
    relative_path: str,
    content: str,
    *,
    encoding: str = "utf-8",
) -> Path:
    """
    Write text content under the active workspace, ensuring parent directories
    exist and returning the resolved file path.
    """
    workspace = workspace.resolve()
    target = (workspace / relative_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding=encoding)
    return target
