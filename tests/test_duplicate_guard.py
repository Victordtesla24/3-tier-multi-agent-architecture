from __future__ import annotations

import pytest

from engine.duplicate_guard import (
    DuplicateContentError,
    find_duplicate_content,
    find_duplicate_repo_directories,
    find_symlink_paths,
)
from engine.project_root_tools import ProjectRootFileWriteTool
from engine.workflow_primitives import write_workspace_file
from engine.workspace_tools import WorkspaceFileWriteTool


def test_find_duplicate_content_detects_identical_managed_files(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts" / "bootstrap.py").write_text(
        "print('same')\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "copy.py").write_text("print('same')\n", encoding="utf-8")

    violations = find_duplicate_content(tmp_path)

    assert len(violations) == 1
    assert {violations[0].canonical_path, violations[0].duplicate_path} == {
        "scripts/bootstrap.py",
        "src/copy.py",
    }


def test_find_duplicate_repo_directories_detects_nested_repo_copy(tmp_path):
    duplicate_dir = tmp_path / tmp_path.name
    duplicate_dir.mkdir()

    violations = find_duplicate_repo_directories(tmp_path)

    assert [violation.duplicate_path for violation in violations] == [tmp_path.name]


def test_find_symlink_paths_detects_nonignored_symlink(tmp_path):
    target = tmp_path / "src"
    target.mkdir()
    (tmp_path / "linked-src").symlink_to(target, target_is_directory=True)

    violations = find_symlink_paths(tmp_path)

    assert [violation.path for violation in violations] == ["linked-src"]


def test_workspace_file_write_rejects_duplicate_managed_content(tmp_path):
    source_file = tmp_path / "src" / "existing.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("print('same')\n", encoding="utf-8")

    tool = WorkspaceFileWriteTool(workspace_root=str(tmp_path))

    with pytest.raises(DuplicateContentError, match="src/existing.py"):
        tool._run("scripts/copy.py", "print('same')\n")

    assert not (tmp_path / "scripts" / "copy.py").exists()


def test_workspace_file_write_allows_idempotent_overwrite_same_path(tmp_path):
    source_file = tmp_path / "src" / "existing.py"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("print('same')\n", encoding="utf-8")

    tool = WorkspaceFileWriteTool(workspace_root=str(tmp_path))

    assert tool._run("src/existing.py", "print('same')\n") == "Wrote src/existing.py"


def test_project_root_file_write_rejects_duplicate_governance_doc(tmp_path):
    report = tmp_path / "docs" / "reports" / "summary.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# Summary\n", encoding="utf-8")

    tool = ProjectRootFileWriteTool(project_root=str(tmp_path))

    with pytest.raises(DuplicateContentError, match="docs/reports/summary.md"):
        tool._run("docs/reports/summary-copy.md", "# Summary\n")


def test_write_workspace_file_skips_ephemeral_outputs(tmp_path):
    write_workspace_file(tmp_path, ".agent/tmp/first.md", "same\n")
    write_workspace_file(tmp_path, ".agent/tmp/second.md", "same\n")

    assert (
        (tmp_path / ".agent" / "tmp" / "first.md").read_text(encoding="utf-8")
        == "same\n"
    )
    assert (
        (tmp_path / ".agent" / "tmp" / "second.md").read_text(encoding="utf-8")
        == "same\n"
    )
