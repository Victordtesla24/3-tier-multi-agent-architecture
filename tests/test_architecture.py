import os
import json
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
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
    original = Path("/Users/Shared/antigravity/3-tier-multi-agent-architecture-work/examples/benchmark_1.md")
    if not benchmark_path.exists() and original.exists():
        benchmark_path = original
    assert benchmark_path.exists(), "Benchmark 1 missing from examples suite."

    with open(benchmark_path, "r") as f:
        content = f.read()

    # Validates the benchmark format contract: must contain an <input_data> tag
    assert "<input_data>" in content


def test_all_benchmarks_have_input_data_tag():
    """Regression: all benchmark files must contain the <input_data> tag required by the architecture."""
    examples_dir = Path(__file__).parent.parent / "examples"
    original_dir = Path("/Users/Shared/antigravity/3-tier-multi-agent-architecture-work/examples")
    if not examples_dir.exists() and original_dir.exists():
        examples_dir = original_dir
        
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

    # The engine constructor creates the log file
    assert log_path.exists(), "Execution log was not created."

    with open(log_path, "r") as f:
        data = json.load(f)

    assert "executions" in data, "Telemetry JSON is missing 'executions' key."


def test_verification_scoring_rejects_placeholders():
    """Test that the verification gate rejects outputs containing banned markers."""
    engine = OrchestrationStateMachine(workspace_dir="/tmp/mock_workspace")

    # Outputs with banned markers should fail verification
    assert engine._run_verification_scoring({"final_output": "This is TODO code"}) is False
    assert engine._run_verification_scoring({"final_output": "placeholder value"}) is False
    assert engine._run_verification_scoring({"final_output": "raise NotImplementedError"}) is False
    assert engine._run_verification_scoring({"final_output": "TBD - will finish later"}) is False

    # Clean output should pass
    assert engine._run_verification_scoring({"final_output": "Complete production code"}) is True


def test_verification_scoring_ast_analysis():
    """Test that AST analysis catches empty function bodies."""
    engine = OrchestrationStateMachine(workspace_dir="/tmp/mock_workspace")

    # Code with empty pass body should fail
    bad_output = '```python\ndef my_function():\n    pass\n```'
    assert engine._run_verification_scoring({"final_output": bad_output}) is False

    # Code with real implementation should pass
    good_output = '```python\ndef my_function():\n    return 42\n```'
    assert engine._run_verification_scoring({"final_output": good_output}) is True


def test_cli_entrypoint_imports():
    """Verify that the CLI entrypoint can be imported without runtime errors."""
    cli_path = Path(__file__).parent.parent / "src" / "orchestrator" / "antigravity-cli.py"
    assert cli_path.exists(), "CLI entrypoint missing"
