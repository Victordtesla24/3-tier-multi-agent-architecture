from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent / "src"))

from engine.context_builder import build_orchestration_context_block
from engine.orchestration_tools import run_benchmarks, run_tests
from engine.project_root_tools import ProjectRootFileReadTool, ProjectRootFileWriteTool
from engine.verification_primitives import (
    contains_banned_markers,
    extract_python_blocks,
    has_empty_implementations,
)


def test_verification_primitives_detect_banned_markers():
    text = "def f():\n    pass\n# TODO later\n"
    hits = contains_banned_markers(text)
    assert "pass-only implementation" in hits
    assert "TODO comment marker" in hits


def test_verification_primitives_extract_and_parse_python_blocks():
    output = "x\n```python\ndef f():\n    return 1\n```\ny"
    blocks = extract_python_blocks(output)
    assert len(blocks) == 1
    has_empty, parse_error = has_empty_implementations(blocks[0])
    assert has_empty is False
    assert parse_error is None


def test_verification_primitives_flag_empty_implementation():
    block = "def f():\n    pass\n"
    has_empty, parse_error = has_empty_implementations(block)
    assert parse_error is None
    assert has_empty is True


def test_context_builder_produces_required_sections(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / ".agent" / "memory").mkdir(parents=True)
    log_file = workspace / ".agent" / "memory" / "execution_log.json"
    log_file.write_text(
        json.dumps(
            {
                "executions": [
                    {
                        "timestamp": "2026-03-05T00:00:00Z",
                        "state": "RESEARCH",
                        "event": "STATE_TRANSITION",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    context = build_orchestration_context_block(
        workspace=workspace,
        project_root=tmp_path,
        strict_provider_validation=True,
        max_provider_4xx=12,
        fail_on_research_empty=False,
    )

    assert "## Environment Snapshot" in context
    assert "## Constraints & Preferences" in context
    assert "strict_provider_validation: True" in context
    assert "max_provider_4xx: 12" in context
    assert "## Recent Execution Activity" in context


def test_project_root_tools_enforce_whitelist(tmp_path):
    project_root = tmp_path / "repo"
    (project_root / "docs" / "architecture").mkdir(parents=True)
    reader = ProjectRootFileReadTool(project_root=str(project_root))
    writer = ProjectRootFileWriteTool(project_root=str(project_root))

    write_result = writer._run("docs/architecture/test.md", "ok")
    assert write_result == "Wrote docs/architecture/test.md"
    assert reader._run("docs/architecture/test.md") == "ok"

    with pytest.raises(ValueError):
        writer._run("docs/reports/forbidden.md", "nope")


def test_health_tools_return_machine_readable_results(tmp_path):
    project_root = tmp_path / "repo"
    project_root.mkdir()

    tests_result = run_tests(
        project_root=project_root,
        command=[sys.executable, "-c", "print('tests ok')"],
        timeout_seconds=30,
    )
    assert tests_result["success"] is True
    assert tests_result["returncode"] == 0
    assert "tests ok" in tests_result["stdout"]
    assert isinstance(tests_result["duration_seconds"], float)

    benchmarks_result = run_benchmarks(
        project_root=project_root,
        command=[sys.executable, "-c", "print('bench ok')"],
        timeout_seconds=30,
    )
    assert benchmarks_result["success"] is True
    assert benchmarks_result["returncode"] == 0
    assert "bench ok" in benchmarks_result["stdout"]
