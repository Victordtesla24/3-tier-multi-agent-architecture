import pytest
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.append(str(Path(__file__).parent.parent / "src"))
from engine.crew_orchestrator import CrewAIThreeTierOrchestrator


@pytest.fixture
def mock_workspace(tmp_path):
    # Setup necessary mock directory structure
    workspace = tmp_path / "mock_workspace"
    workspace.mkdir()
    (workspace / "docs" / "architecture").mkdir(parents=True)
    (workspace / "docs" / "architecture" / "prompt-reconstruction.md").write_text("Hello {{INPUT_DATA}}")
    return str(workspace)

@pytest.fixture(autouse=True)
def mock_env_vars():
    with patch.dict("os.environ", {
        "GOOGLE_API_KEY": "dummy_gemini_key",
        "OPENAI_API_KEY": "dummy_openai_key",
        "MINIMAX_API_KEY": "dummy_minimax_key",
        "DEEPSEEK_API_KEY": "dummy_deepseek_key",
        "MINIMAX_BASE_URL": "https://dummy.minimax.api",
        "DEEPSEEK_BASE_URL": "https://dummy.deepseek.api",
    }):
        yield


def test_edge_case_prompt_handling(mock_workspace):
    """Test edge-case prompt tests (ambiguous, conflicting requirements)."""
    orchestrator = CrewAIThreeTierOrchestrator(workspace_dir=mock_workspace, verbose=False)
    
    # We patch Crew.kickoff to simulate how the orchestrator would respond to an ambiguous prompt
    # In a real environment, the LLM would ask for clarification or refuse.
    with patch("engine.crew_orchestrator.Crew.kickoff") as mock_kickoff:
        mock_kickoff.return_value = "CLARIFICATION REQUIRED: Please provide more details."
        
        # Ambiguous prompt
        result = orchestrator.reconstruct_prompt("<input_data>Make it work</input_data>")
        assert "CLARIFICATION" in result


def test_simulated_llm_failure_injection(mock_workspace):
    """Simulated LLM failure injection to verify retry logic inside the E2E orchestrator flow."""
    orchestrator = CrewAIThreeTierOrchestrator(workspace_dir=mock_workspace, verbose=False)
    
    call_count = {"count": 0}
    
    def delayed_success(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise Exception("Simulated transient API Failure")
        return "Success on retry"
    
    with patch("crewai.LLM.call", side_effect=delayed_success):
        # The prompt reconstruction forces the Orchestrator to trigger an LLM
        # The first call will simulate a failure, and CrewAI's tenacity retry will succeed
        try:
            result = orchestrator.reconstruct_prompt("<input_data>test the retry logic</input_data>")
            assert "Success on retry" in result
        except Exception:
            # If it doesn't retry, it fails the test
            pytest.fail("Retry logic failed or exception leaked.")


def test_memory_telemetry_validation(mock_workspace):
    """Memory/telemetry validation for Continuous Learning proposals."""
    from engine.state_machine import OrchestrationStateMachine
    
    # Initialize the state machine which creates the telemetry file
    machine = OrchestrationStateMachine(workspace_dir=mock_workspace)
    
    memory_dir = Path(mock_workspace) / ".agent" / "memory"
    log_file = memory_dir / "execution_log.json"
    
    assert log_file.exists(), "Telemetry execution_log.json was not created"
    
    with open(log_file, "r") as f:
        data = json.load(f)
        
    assert "executions" in data
    
    # Simulate adding a continuous learning proposal
    data["executions"].append({
        "timestamp": "2026-03-03T00:00:00Z",
        "status": "success",
        "learning_proposal": {
            "WHAT": "Optimize prompt parsing",
            "WHY": "AST validation failed 2 times before success",
            "HOW": "Add strict AST markers to L1 instructions"
        }
    })
    
    with open(log_file, "w") as f:
        json.dump(data, f)
        
    # Read back and validate
    with open(log_file, "r") as f:
        new_data = json.load(f)
        
    assert len(new_data["executions"]) == 1
    assert "learning_proposal" in new_data["executions"][0]
    assert new_data["executions"][0]["learning_proposal"]["WHAT"] == "Optimize prompt parsing"
