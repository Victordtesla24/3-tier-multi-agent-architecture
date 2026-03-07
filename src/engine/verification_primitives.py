from __future__ import annotations

import ast
import re
from collections.abc import Iterable


_BANNED_MARKERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?im)^\s*(#|//)\s*TODO\b"), "TODO comment marker"),
    (re.compile(r"(?im)^\s*TODO\b"), "TODO marker"),
    (re.compile(r"(?im)\bTBD\b"), "TBD marker"),
    (re.compile(r"(?im)\bFIXME\b"), "FIXME marker"),
    (re.compile(r"(?im)\braise\s+NotImplementedError\b"), "NotImplementedError stub"),
    (re.compile(r"(?im)^\s*pass\s*(#.*)?$"), "pass-only implementation"),
    (re.compile(r"(?im)<\s*placeholder\s*>"), "<placeholder> token"),
    (re.compile(r"(?im)\{\{\s*.*placeholder.*\}\}"), "{{placeholder}} token"),
)


def contains_banned_markers(text: str) -> list[str]:
    """
    Return the list of lexical policy markers detected in the supplied text.
    """
    hits: list[str] = []
    for pattern, marker_name in _BANNED_MARKERS:
        if pattern.search(text):
            hits.append(marker_name)
    return hits


def extract_python_blocks(text: str) -> list[str]:
    """
    Extract fenced python blocks from markdown-like output.
    """
    return re.findall(r"```python\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)


def _iter_definition_nodes(tree: ast.AST) -> Iterable[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node


def has_empty_implementations(code: str) -> tuple[bool, str | None]:
    """
    Parse `code` and detect definitions with a pass-only body.

    Returns:
      - (True, None) if an empty implementation is detected
      - (False, None) when code is syntactically valid and passes the check
      - (False, "<error>") when parsing fails
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, str(exc)

    for node in _iter_definition_nodes(tree):
        body = getattr(node, "body", [])
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            return True, None

    return False, None
