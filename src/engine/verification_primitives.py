from __future__ import annotations

import ast
import re
import subprocess
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class BannedMarkerSpec:
    """Single banned-marker rule with compiled regex and human-readable label."""
    pattern: re.Pattern[str]
    label: str


_BANNED_MARKER_REGISTRY: tuple[BannedMarkerSpec, ...] = (
    BannedMarkerSpec(re.compile(r"(?im)^\s*(#|//)\s*TODO\b"), "TODO comment marker"),
    BannedMarkerSpec(re.compile(r"(?im)^\s*TODO\b"), "TODO marker"),
    BannedMarkerSpec(re.compile(r"(?im)\bTBD\b"), "TBD marker"),
    BannedMarkerSpec(re.compile(r"(?im)\bFIXME\b"), "FIXME marker"),
    BannedMarkerSpec(re.compile(r"(?im)\braise\s+NotImplementedError\b"), "NotImplementedError stub"),
    BannedMarkerSpec(re.compile(r"(?im)^\s*pass\s*(#.*)?$"), "pass-only implementation"),
    BannedMarkerSpec(re.compile(r"(?im)<\s*placeholder\s*>"), "<placeholder> token"),
    BannedMarkerSpec(re.compile(r"(?im)\{\{\s*.*placeholder.*\}\}"), "{{placeholder}} token"),
    BannedMarkerSpec(
        re.compile(r"(?i)\bthrow\s+new\s+Error\s*\(\s*['\"]not\s+implemented"),
        "JS NotImplemented throw",
    ),
)


def get_banned_marker_registry() -> tuple[BannedMarkerSpec, ...]:
    """Public accessor for the canonical banned-marker registry.

    All modules that need to check for banned markers MUST use this function
    rather than maintaining a private copy of the patterns.
    """
    return _BANNED_MARKER_REGISTRY

CodeLanguage = Literal["python", "javascript", "typescript", "bash", "shell", "sh"]

_FENCED_BLOCK_PATTERN = re.compile(
    r"```(python|javascript|typescript|js|ts|bash|shell|sh)\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)

_LANG_NORMALIZE: dict[str, CodeLanguage] = {
    "python": "python",
    "javascript": "javascript",
    "js": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "bash": "bash",
    "shell": "shell",
    "sh": "sh",
}


@dataclass(frozen=True)
class CodeBlock:
    language: CodeLanguage
    source: str


def contains_banned_markers(text: str) -> list[str]:
    """Return the list of lexical policy markers detected in the supplied text."""
    hits: list[str] = []
    for spec in _BANNED_MARKER_REGISTRY:
        if spec.pattern.search(text):
            hits.append(spec.label)
    return hits


def extract_code_blocks(text: str) -> list[CodeBlock]:
    """Extract all fenced code blocks with recognised language tags."""
    blocks: list[CodeBlock] = []
    for match in _FENCED_BLOCK_PATTERN.finditer(text):
        raw_lang = match.group(1).lower()
        lang = _LANG_NORMALIZE.get(raw_lang)
        if lang is not None:
            blocks.append(CodeBlock(language=lang, source=match.group(2)))
    return blocks


def extract_python_blocks(text: str) -> list[str]:
    """Backward-compatible: extract only Python fenced blocks as raw strings."""
    return [b.source for b in extract_code_blocks(text) if b.language == "python"]


def _iter_definition_nodes(tree: ast.AST) -> Iterable[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node


def has_empty_implementations(code: str) -> tuple[bool, str | None]:
    """Parse Python code and detect definitions with a pass-only body."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, str(exc)

    for node in _iter_definition_nodes(tree):
        body = getattr(node, "body", [])
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            return True, None

    return False, None


def validate_javascript_syntax(code: str) -> str | None:
    """Validate JavaScript/TypeScript syntax using Node.js --check if available.

    Returns None if valid, or an error string if invalid or Node is not installed.
    """
    node_bin = shutil.which("node")
    if node_bin is None:
        return None

    try:
        result = subprocess.run(
            [node_bin, "--check", "--input-type=module"],
            input=code,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return result.stderr.strip() or "JavaScript syntax error (unknown)"
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"JavaScript validation failed: {exc}"

    return None


def validate_shell_syntax(code: str) -> str | None:
    """Validate shell script syntax using bash -n if available.

    Returns None if valid, or an error string if invalid.
    """
    bash_bin = shutil.which("bash")
    if bash_bin is None:
        return None

    try:
        result = subprocess.run(
            [bash_bin, "-n"],
            input=code,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return result.stderr.strip() or "Shell syntax error (unknown)"
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"Shell validation failed: {exc}"

    return None


def validate_code_block(block: CodeBlock) -> tuple[bool, str | None, bool]:
    """Validate a code block based on its language.

    Returns: (has_empty_impl, syntax_error_or_None, is_validated)
    - has_empty_impl: True if empty implementations detected (Python only)
    - syntax_error: error string if syntax validation failed, else None
    - is_validated: True if the language was actually validated
    """
    if block.language == "python":
        has_empty, parse_error = has_empty_implementations(block.source)
        return has_empty, parse_error, True

    if block.language in ("javascript", "typescript"):
        err = validate_javascript_syntax(block.source)
        return False, err, err is not None or shutil.which("node") is not None

    if block.language in ("bash", "shell", "sh"):
        err = validate_shell_syntax(block.source)
        return False, err, err is not None or shutil.which("bash") is not None

    return False, None, False
