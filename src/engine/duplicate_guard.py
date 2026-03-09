from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

_MANAGED_DIRECTORY_PREFIXES = (
    ".agent/rules",
    ".agent/workflows",
    ".github/workflows",
    "benchmarks",
    "docs",
    "examples",
    "scripts",
    "src",
    "tests",
)
_MANAGED_ROOT_FILES = {
    ".env.template",
    ".gitignore",
    "Makefile",
    "README.md",
    "package.json",
    "pyproject.toml",
    "pyrightconfig.json",
}
_IGNORED_WALK_PREFIXES = (
    ".agent/memory",
    ".agent/tmp",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "htmlcov",
    "node_modules",
    "tmp",
    "workspaces",
)
_TEXT_SUFFIXES = {
    ".cfg",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True)
class DuplicateContentViolation:
    canonical_path: str
    duplicate_path: str


@dataclass(frozen=True)
class DuplicateDirectoryViolation:
    duplicate_path: str


@dataclass(frozen=True)
class SymlinkViolation:
    path: str


class DuplicateContentError(ValueError):
    def __init__(self, *, target_path: str, canonical_path: str):
        super().__init__(
            "Refusing to create duplicate managed content at "
            f"'{target_path}' because the same content already exists at "
            f"'{canonical_path}'. Update the canonical file instead."
        )
        self.target_path = target_path
        self.canonical_path = canonical_path


def normalise_relative_path(path: str | Path) -> str:
    raw = Path(path).as_posix()
    if raw == ".":
        return ""
    return raw.lstrip("./")


def is_ignored_walk_path(relative_path: str) -> bool:
    normalised = normalise_relative_path(relative_path)
    return any(
        normalised == prefix or normalised.startswith(f"{prefix}/")
        for prefix in _IGNORED_WALK_PREFIXES
    )


def is_managed_path(relative_path: str) -> bool:
    normalised = normalise_relative_path(relative_path)
    if normalised in _MANAGED_ROOT_FILES:
        return True
    return any(
        normalised == prefix or normalised.startswith(f"{prefix}/")
        for prefix in _MANAGED_DIRECTORY_PREFIXES
    )


def is_text_candidate(relative_path: str) -> bool:
    normalised = normalise_relative_path(relative_path)
    if normalised in _MANAGED_ROOT_FILES:
        return True
    path = Path(normalised)
    return path.suffix.lower() in _TEXT_SUFFIXES


def should_enforce_duplicate_guard(relative_path: str) -> bool:
    normalised = normalise_relative_path(relative_path)
    return (
        bool(normalised)
        and is_managed_path(normalised)
        and is_text_candidate(normalised)
        and not is_ignored_walk_path(normalised)
    )


def assert_no_duplicate_content(root: Path, relative_path: str, content: str) -> None:
    root = root.resolve()
    normalised_target = normalise_relative_path(relative_path)
    if not should_enforce_duplicate_guard(normalised_target):
        return

    target_path = (root / normalised_target).resolve()
    target_signature = _content_signature(normalised_target, content)

    for existing in _iter_managed_text_files(root):
        if existing == target_path:
            continue
        existing_relative = normalise_relative_path(existing.relative_to(root))
        if _content_signature(
            existing_relative, existing.read_text(encoding="utf-8")
        ) == target_signature:
            raise DuplicateContentError(
                target_path=normalised_target,
                canonical_path=existing_relative,
            )


def find_duplicate_content(root: Path) -> tuple[DuplicateContentViolation, ...]:
    root = root.resolve()
    buckets: dict[str, str] = {}
    duplicates: list[DuplicateContentViolation] = []

    for path in _iter_managed_text_files(root):
        relative = normalise_relative_path(path.relative_to(root))
        signature = _content_signature(relative, path.read_text(encoding="utf-8"))
        canonical = buckets.get(signature)
        if canonical is None:
            buckets[signature] = relative
            continue
        duplicates.append(
            DuplicateContentViolation(
                canonical_path=canonical,
                duplicate_path=relative,
            )
        )

    return tuple(duplicates)


def find_duplicate_repo_directories(root: Path) -> tuple[DuplicateDirectoryViolation, ...]:
    root = root.resolve()
    repo_name = root.name
    duplicates: list[DuplicateDirectoryViolation] = []

    for current_root, dirnames, _filenames in os.walk(root):
        current_path = Path(current_root)
        current_relative = normalise_relative_path(current_path.relative_to(root))
        filtered_dirnames: list[str] = []
        for dirname in dirnames:
            candidate_relative = normalise_relative_path(
                Path(current_relative) / dirname if current_relative else dirname
            )
            if is_ignored_walk_path(candidate_relative):
                continue
            filtered_dirnames.append(dirname)
            if dirname == repo_name:
                duplicates.append(
                    DuplicateDirectoryViolation(duplicate_path=candidate_relative)
                )
        dirnames[:] = filtered_dirnames

    return tuple(sorted(duplicates, key=lambda item: item.duplicate_path))


def find_symlink_paths(root: Path) -> tuple[SymlinkViolation, ...]:
    root = root.resolve()
    violations: list[SymlinkViolation] = []

    for current_root, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current_root)
        current_relative = normalise_relative_path(current_path.relative_to(root))
        filtered_dirnames: list[str] = []

        for dirname in dirnames:
            candidate_relative = normalise_relative_path(
                Path(current_relative) / dirname if current_relative else dirname
            )
            if is_ignored_walk_path(candidate_relative):
                continue
            candidate_path = root / candidate_relative
            if candidate_path.is_symlink():
                violations.append(SymlinkViolation(path=candidate_relative))
                continue
            filtered_dirnames.append(dirname)

        dirnames[:] = filtered_dirnames

        for filename in filenames:
            candidate_relative = normalise_relative_path(
                Path(current_relative) / filename if current_relative else filename
            )
            if is_ignored_walk_path(candidate_relative):
                continue
            candidate_path = root / candidate_relative
            if candidate_path.is_symlink():
                violations.append(SymlinkViolation(path=candidate_relative))

    return tuple(sorted(violations, key=lambda item: item.path))


def _iter_managed_text_files(root: Path) -> list[Path]:
    candidates: set[Path] = set()

    for relative in _MANAGED_ROOT_FILES:
        path = root / relative
        if path.is_file():
            candidates.add(path.resolve())

    for prefix in _MANAGED_DIRECTORY_PREFIXES:
        base = root / prefix
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            relative = normalise_relative_path(path.relative_to(root))
            if should_enforce_duplicate_guard(relative):
                candidates.add(path.resolve())

    return sorted(
        candidates,
        key=lambda item: normalise_relative_path(item.relative_to(root)),
    )


def _content_signature(relative_path: str, content: str) -> str:
    normalised = content.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    if Path(relative_path).suffix.lower() == ".json":
        try:
            parsed = json.loads(normalised)
        except json.JSONDecodeError:
            return normalised
        return json.dumps(
            parsed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    return normalised
