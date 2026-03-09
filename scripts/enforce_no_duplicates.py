from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"


def _load_duplicate_guard():
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    from engine.duplicate_guard import (
        find_duplicate_content,
        find_duplicate_repo_directories,
        find_symlink_paths,
    )

    return find_duplicate_content, find_duplicate_repo_directories, find_symlink_paths


def main() -> int:
    (
        find_duplicate_content,
        find_duplicate_repo_directories,
        find_symlink_paths,
    ) = _load_duplicate_guard()
    symlink_paths = find_symlink_paths(PROJECT_ROOT)
    duplicate_directories = find_duplicate_repo_directories(PROJECT_ROOT)
    duplicate_files = find_duplicate_content(PROJECT_ROOT)

    if symlink_paths:
        print("Symlinks detected:")
        for violation in symlink_paths:
            print(f" - {violation.path}")

    if duplicate_directories:
        print("Duplicate repository directories detected:")
        for violation in duplicate_directories:
            print(f" - {violation.duplicate_path}")

    if duplicate_files:
        print("Duplicate managed files detected:")
        for violation in duplicate_files:
            print(
                f" - {violation.duplicate_path} duplicates {violation.canonical_path}"
            )

    if symlink_paths or duplicate_directories or duplicate_files:
        return 1

    print("Duplicate content audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
