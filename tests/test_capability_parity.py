from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from ast import literal_eval

from engine.orchestration_tools import (
    ACK_ACTION_ID,
    AcknowledgeUIActionTool,
    MAX_SUBMIT_OBJECTIVE_DEPTH,
    _ORCHESTRATION_DEPTH_ENV,
    SubmitObjectiveTool,
    read_runtime_configuration,
)
from engine.crew_orchestrator import CrewAIThreeTierOrchestrator
from engine.exceptions import OrchestrationDepthExceeded
from view.a2ui_protocol import acknowledgement_visibility_path, resolve_acknowledgement_data_model


def _dummy_matrix() -> SimpleNamespace:
    class _LLM:
        def __init__(self, model: str):
            self.model = model

    def tier(primary: str, fallback: str) -> SimpleNamespace:
        return SimpleNamespace(
            primary=_LLM(primary),
            fallback=_LLM(fallback),
        )
    return SimpleNamespace(
        orchestration=tier("openai/test-orch", "openai/test-orch-fallback"),
        level1=tier("openai/test-l1", "openai/test-l1-fallback"),
        level2=tier("openai/test-l2", "openai/test-l2-fallback"),
        level3=tier("openai/test-l3", "openai/test-l3-fallback"),
        tier_primary_logical_ids={
            "orchestration": "openai/test-orch",
            "level1": "openai/test-l1",
            "level2": "openai/test-l2",
            "level3": "openai/test-l3",
        },
        tier_fallback_logical_ids={
            "orchestration": "openai/test-orch-fallback",
            "level1": "openai/test-l1-fallback",
            "level2": "openai/test-l2-fallback",
            "level3": "openai/test-l3-fallback",
        },
        active_provider_env_keys=(),
        level2_swarm_count=None,
        level3_swarm_count=None,
        config_warnings=[],
    )


def _ui_action_ids() -> set[str]:
    source = (
        Path(__file__).resolve().parent.parent / "src" / "view" / "a2ui_protocol.py"
    ).read_text(encoding="utf-8")
    ids = set(re.findall(r'"actionId"\s*:\s*"([^"]+)"', source))
    constant_refs = set(re.findall(r'"actionId"\s*:\s*([A-Za-z_][A-Za-z0-9_]*)', source))
    for name in constant_refs:
        match = re.search(rf"^{name}\s*=\s*\"([^\"]+)\"", source, flags=re.MULTILINE)
        if match:
            ids.add(match.group(1))
    return ids


def test_ui_actions_require_agent_tools_and_manifest_registration(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.crew_orchestrator.build_model_matrix", lambda *args, **kwargs: _dummy_matrix())

    orchestrator = CrewAIThreeTierOrchestrator(
        workspace_dir=str(tmp_path),
        verbose=False,
        strict_provider_validation=False,
    )
    tool_names = {tool.name for tool in orchestrator._build_worker_tools()}
    manifest = orchestrator._worker_tooling_manifest()

    mapping = {
        "ack_event_01": "acknowledge_ui_action",
    }

    action_ids = _ui_action_ids()
    assert action_ids, "No UI action IDs discovered; parity test cannot validate coverage."
    for action_id in sorted(action_ids):
        assert action_id in mapping, f"Missing agent parity mapping for UI action '{action_id}'."
        tool_name = mapping[action_id]
        assert tool_name in tool_names, f"Missing tool '{tool_name}' for UI action '{action_id}'."
        assert tool_name in manifest, f"Tool '{tool_name}' missing from worker tooling manifest."


def test_acknowledge_tool_uses_shared_ack_pointer(tmp_path):
    tool = AcknowledgeUIActionTool(workspace=str(tmp_path))
    result = literal_eval(tool._run(action_id=ACK_ACTION_ID, acknowledged=True))

    expected_pointer = acknowledgement_visibility_path(ACK_ACTION_ID)
    assert result["shared_state_path"] == expected_pointer
    assert result["visibility"] is False

    state_file = tmp_path / ".agent" / "memory" / "a2ui_state.json"
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["data_model"][expected_pointer] is False


def test_submit_objective_tool_is_cli_prompt_equivalent(tmp_path, monkeypatch):
    def _fake_run_orchestration(cfg):
        return SimpleNamespace(
            success=True,
            workspace=cfg.workspace,
            run_id="run-123",
            completion_status="success",
            completion_summary="ok",
            final_output_path=cfg.workspace / ".agent" / "tmp" / "final_output.md",
            reconstructed_prompt_path=cfg.workspace / ".agent" / "tmp" / "reconstructed_prompt.md",
            research_context_path=cfg.workspace / ".agent" / "tmp" / "research-context.md",
            execution_log_path=cfg.workspace / ".agent" / "memory" / "execution_log.json",
            failed_stage=None,
            error=None,
        )

    monkeypatch.setattr("engine.orchestration_api.run_orchestration", _fake_run_orchestration)
    tool = SubmitObjectiveTool(workspace=str(tmp_path))
    result = literal_eval(tool._run(prompt="Ship feature parity"))

    assert result["success"] is True
    assert result["completion_status"] == "success"
    assert Path(result["workspace"]) == tmp_path.resolve()


def test_runtime_config_system_env_is_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-openai")
    monkeypatch.setenv("GOOGLE_API_KEY", "super-secret-google")
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-gemini")
    monkeypatch.setenv("ANTIGRAVITY_WORKSPACE_DIR", "/tmp/example")
    payload = read_runtime_configuration(
        project_root=tmp_path,
        workspace=tmp_path,
        include_system_env=True,
    )

    assert payload["system_env"]["OPENAI_API_KEY"] == "[REDACTED]"
    assert payload["system_env"]["GOOGLE_API_KEY"] == "[REDACTED]"
    assert payload["system_env"]["GEMINI_API_KEY"] == "[REDACTED]"
    assert payload["system_env"]["ANTIGRAVITY_WORKSPACE_DIR"] == "/tmp/example"


def test_submit_objective_rejects_excessive_recursion_depth(tmp_path, monkeypatch):
    monkeypatch.setenv(_ORCHESTRATION_DEPTH_ENV, str(MAX_SUBMIT_OBJECTIVE_DEPTH))
    tool = SubmitObjectiveTool(workspace=str(tmp_path))

    try:
        tool._run(prompt="nested objective")
        assert False, "Expected OrchestrationDepthExceeded"
    except OrchestrationDepthExceeded as exc:
        assert exc.depth == MAX_SUBMIT_OBJECTIVE_DEPTH


def test_submit_objective_logs_blocked_nested_attempt(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(_ORCHESTRATION_DEPTH_ENV, str(MAX_SUBMIT_OBJECTIVE_DEPTH))
    tool = SubmitObjectiveTool(workspace=str(tmp_path))

    with caplog.at_level("WARNING"):
        try:
            tool._run(prompt="nested objective")
            assert False, "Expected OrchestrationDepthExceeded"
        except OrchestrationDepthExceeded:
            pass

    assert "SUBMIT_OBJECTIVE_BLOCKED_NESTED" in caplog.text


def test_resolve_ack_data_model_uses_persisted_workspace_state(tmp_path):
    state_file = tmp_path / ".agent" / "memory" / "a2ui_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    pointer = acknowledgement_visibility_path(ACK_ACTION_ID)
    state_file.write_text(
        json.dumps({"data_model": {pointer: False}}, indent=2),
        encoding="utf-8",
    )

    data_model = resolve_acknowledgement_data_model({"workspace": str(tmp_path)})
    assert data_model[pointer] is False


def test_acknowledge_tool_logs_and_recovers_corrupt_state(tmp_path, caplog):
    state_file = tmp_path / ".agent" / "memory" / "a2ui_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    pointer = acknowledgement_visibility_path(ACK_ACTION_ID)
    state_file.write_text(
        '{"data_model":{"%s": false},"last_action":{"action_id":"%s"}}BROKEN'
        % (pointer, ACK_ACTION_ID),
        encoding="utf-8",
    )

    tool = AcknowledgeUIActionTool(workspace=str(tmp_path))
    with caplog.at_level("ERROR"):
        result = literal_eval(tool._run(action_id=ACK_ACTION_ID, acknowledged=False))

    assert "A2UI_STATE_CORRUPT_RECOVERED" in caplog.text
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["data_model"][pointer] is True
    assert result["visibility"] is True
