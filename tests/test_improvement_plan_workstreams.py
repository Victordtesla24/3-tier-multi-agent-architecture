from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent / "src"))

from engine.continuous_learning import generate_improvement_proposal
from engine.context_builder import build_orchestration_context_block
from engine.orchestration_tools import run_benchmarks, run_tests
from engine.project_root_tools import ProjectRootFileReadTool, ProjectRootFileWriteTool
from engine.verification_primitives import (
    contains_banned_markers,
    extract_code_blocks,
    extract_python_blocks,
    has_empty_implementations,
    validate_javascript_syntax,
    validate_shell_syntax,
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


def test_verification_primitives_extract_multi_language_blocks():
    output = (
        "```javascript\nconst x = 1;\n```\n"
        "```bash\necho ok\n```\n"
    )
    blocks = extract_code_blocks(output)

    assert [(block.language, block.source) for block in blocks] == [
        ("javascript", "const x = 1;"),
        ("bash", "echo ok"),
    ]


def test_verification_primitives_detect_javascript_not_implemented_marker():
    hits = contains_banned_markers('throw new Error("not implemented")')
    assert "JS NotImplemented throw" in hits


def test_verification_primitives_validate_javascript_and_shell_syntax():
    js_error = validate_javascript_syntax("const = ;")
    shell_error = validate_shell_syntax("if then")

    if shutil.which("node") is None:
        assert js_error is None
    else:
        assert js_error is not None
        assert "SyntaxError" in js_error

    if shutil.which("bash") is None:
        assert shell_error is None
    else:
        assert shell_error is not None
        assert "syntax error" in shell_error.lower()


def test_context_builder_produces_required_sections(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / ".agent" / "memory").mkdir(parents=True)
    (tmp_path / "docs" / "reports").mkdir(parents=True)
    (tmp_path / "docs" / "benchmarks").mkdir(parents=True)
    (tmp_path / "docs" / "reports" / "critical_analysis_report.md").write_text("# report\n", encoding="utf-8")
    (tmp_path / "docs" / "benchmarks" / "latest_results.md").write_text("# bench\n", encoding="utf-8")
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
    assert "docs/reports/*" in context
    assert "critical_analysis_report.md" in context
    assert "latest_results.md" in context


def test_generate_improvement_proposal_reads_nested_pipeline_complete_events(tmp_path):
    workspace = tmp_path / "workspace"
    log_dir = workspace / ".agent" / "memory"
    log_dir.mkdir(parents=True)
    (log_dir / "execution_log.json").write_text(
        json.dumps(
            {
                "executions": [
                    {
                        "timestamp": "2026-03-07T00:00:00Z",
                        "run_id": "run-1",
                        "state": "RESEARCH",
                        "event": "PIPELINE_COMPLETE",
                        "details": {
                            "success": False,
                            "completion_status": "blocked",
                            "failed_stage": "RESEARCH",
                            "error_type": "TimeoutError",
                            "error": "timed out while querying provider",
                            "stage_progress": {
                                "RESEARCH": {
                                    "status": "failed",
                                    "notes": "timed out",
                                    "started_at": "2026-03-07T00:00:00Z",
                                    "finished_at": "2026-03-07T00:01:12Z",
                                    "duration_s": 72.4,
                                }
                            },
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    proposal = generate_improvement_proposal(workspace)

    assert "Analyzed 1 recorded pipeline execution(s)" in proposal
    assert "[RESEARCH] TimeoutError: 1 occurrence(s)" in proposal
    assert "RESEARCH: median 72.4s across 1 samples" in proposal
    assert "Stage 'RESEARCH' timed out in 100% of runs." in proposal


def test_generate_improvement_proposal_reads_task_graph_metrics(tmp_path):
    workspace = tmp_path / "workspace"
    log_dir = workspace / ".agent" / "memory"
    log_dir.mkdir(parents=True)
    (log_dir / "execution_log.json").write_text(
        json.dumps(
            {
                "executions": [
                    {
                        "timestamp": "2026-03-07T00:00:00Z",
                        "run_id": "run-2",
                        "state": "ORCHESTRATION_L1",
                        "event": "PIPELINE_COMPLETE",
                        "details": {
                            "success": True,
                            "completion_status": "success",
                            "failed_stage": None,
                            "execution_mode": "task_graph",
                            "plan_id": "plan-123",
                            "task_count": 3,
                            "parallel_batch_count": 2,
                            "worker_retry_count": 2,
                            "task_failure_count": 0,
                            "stage_progress": {},
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    proposal = generate_improvement_proposal(workspace)

    assert "avg tasks/run 3.0" in proposal
    assert "avg batches/run 2.0" in proposal
    assert "avg worker retries/run 2.0" in proposal
    assert "Workers are retrying 2.0 time(s) per run on average." in proposal


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
