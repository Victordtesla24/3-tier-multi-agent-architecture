import os
import json
import subprocess
import pytest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent / "src"))
from engine.state_machine import OrchestrationStateMachine


def test_engine_initialization():
    """Test that the python programmatic engine initializes correctly."""
    engine = OrchestrationStateMachine(workspace_dir="/tmp/mock_workspace")
    assert engine.state == "INIT"
    assert engine.max_retries == 3


def test_benchmark_parsing():
    """Test that a benchmark prompt from examples/ maps cleanly to execution context."""
    benchmark_path = Path(__file__).parent.parent / "examples" / "benchmark_1.md"
    assert benchmark_path.exists(), "Benchmark 1 missing from examples suite."

    with open(benchmark_path, "r") as f:
        content = f.read()

    # Validates the benchmark format contract: must contain an <input_data> tag
    assert "<input_data>" in content

    engine = OrchestrationStateMachine(workspace_dir="/tmp/mock_workspace")

    # Full pipeline execution against the benchmark prompt
    result = engine.execute_pipeline(raw_prompt=content)
    assert result is True, "Pipeline execution failed the highly optimized probabilistic evaluation."


def test_all_benchmarks_have_input_data_tag():
    """Regression: all benchmark files must contain the <input_data> tag required by the architecture."""
    examples_dir = Path(__file__).parent.parent / "examples"
    benchmarks = list(examples_dir.glob("benchmark_*.md"))
    assert len(benchmarks) >= 4, f"Expected at least 4 benchmarks, found {len(benchmarks)}"

    for bm in benchmarks:
        with open(bm, "r") as f:
            content = f.read()
        assert "<input_data>" in content, f"Benchmark {bm.name} is missing the required <input_data> tag."


def test_pipeline_telemetry_is_written():
    """Test that executing the pipeline generates a valid structured telemetry JSON file."""
    workspace = "/tmp/test_telemetry_workspace"
    log_path = Path(workspace) / ".agent" / "memory" / "execution_log.json"

    # Clean slate
    if log_path.exists():
        log_path.unlink()

    engine = OrchestrationStateMachine(workspace_dir=workspace)
    result = engine.execute_pipeline(raw_prompt="benchmark telemetry verification test")

    assert result is True
    assert log_path.exists(), "Execution log was not created."

    with open(log_path, "r") as f:
        data = json.load(f)

    assert "executions" in data, "Telemetry JSON is missing 'executions' key."
    assert len(data["executions"]) > 0, "No telemetry events were written."
    assert data["executions"][-1]["event"] == "PIPELINE_COMPLETE"
    assert data["executions"][-1]["details"]["success"] is True


def test_cli_entrypoint_executes_successfully():
    """Integration test: verify the CLI entrypoint runs end-to-end without error."""
    cli_path = Path(__file__).parent.parent / "src" / "orchestrator" / "antigravity-cli.py"
    result = subprocess.run(
        [
            sys.executable,
            str(cli_path),
            "--workspace", "/tmp/test_cli_workspace",
            "--prompt", "integration test: verify CLI pipeline execution",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"CLI exited with code {result.returncode}.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "Pipeline executed successfully" in result.stdout or "Pipeline executed successfully" in result.stderr
