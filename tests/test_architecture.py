import os
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

    # In a real environment, the state machine would execute this content via LLM and assert structured outputs.
    assert "<input_data>" in content
    
    engine = OrchestrationStateMachine(workspace_dir="/tmp/mock_workspace")
    
    # We simulate a "success" based on the mock output
    result = engine.execute_pipeline(raw_prompt=content)
    assert result is True, "Pipeline execution failed the highly optimized probabilistic evaluation."
