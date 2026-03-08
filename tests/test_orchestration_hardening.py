from __future__ import annotations

import os
import sys
from ast import literal_eval
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.append(str(Path(__file__).parent.parent / "src"))

from engine.context_builder import _detect_primary_languages
from engine.crewai_storage import bootstrap_crewai_storage
from engine.orchestration_api import OrchestrationRunConfig, run_orchestration
from engine.orchestration_tools import (
    ReadRuntimeConfigTool,
    RunBenchmarksTool,
    RunTestsTool,
    UpdateRuntimeConfigTool,
)


def test_health_tools_disallow_command_override_in_schema():
    tests_tool = RunTestsTool(project_root="/tmp")
    benchmarks_tool = RunBenchmarksTool(project_root="/tmp")
    assert "command" not in tests_tool.args_schema.model_fields
    assert "command" not in benchmarks_tool.args_schema.model_fields


def test_health_tools_reject_command_kwarg(tmp_path):
    tests_tool = RunTestsTool(project_root=str(tmp_path))
    benchmarks_tool = RunBenchmarksTool(project_root=str(tmp_path))

    with pytest.raises(TypeError):
        tests_tool._run(command="pytest tests")  # type: ignore[call-arg]

    with pytest.raises(TypeError):
        benchmarks_tool._run(command="python benchmarks/run_benchmark.py")  # type: ignore[call-arg]


def test_runtime_config_tools_are_bound_to_active_workspace(tmp_path):
    project_root = tmp_path / "project"
    workspace = tmp_path / "workspace"
    external_workspace = tmp_path / "external"
    project_root.mkdir()
    workspace.mkdir()
    external_workspace.mkdir()
    (external_workspace / ".env").write_text(
        "ANTIGRAVITY_WORKSPACE_DIR=/outside\n", encoding="utf-8"
    )

    read_tool = ReadRuntimeConfigTool(
        project_root=str(project_root),
        workspace=str(workspace),
    )
    read_payload = literal_eval(read_tool._run())

    assert Path(read_payload["workspace"]) == workspace.resolve()
    assert "workspace" not in read_tool.args_schema.model_fields

    with pytest.raises(TypeError):
        read_tool._run(str(external_workspace))  # type: ignore[call-arg]

    update_tool = UpdateRuntimeConfigTool(workspace=str(workspace))
    update_payload = literal_eval(
        update_tool._run({"ANTIGRAVITY_WORKSPACE_DIR": str(workspace)})
    )

    assert Path(update_payload["workspace_env_path"]) == workspace.resolve() / ".env"
    assert "workspace" not in update_tool.args_schema.model_fields
    assert "outside" in (external_workspace / ".env").read_text(encoding="utf-8")

    with pytest.raises(TypeError):
        update_tool._run(str(external_workspace), {})  # type: ignore[call-arg]


def test_crewai_storage_rebinds_per_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("CREWAI_STORAGE_DIR", "/tmp/prebound")
    monkeypatch.setenv("CREWAI_HOME", "/tmp/prebound")

    workspace_one = tmp_path / "workspace_one"
    workspace_two = tmp_path / "workspace_two"

    first = bootstrap_crewai_storage(workspace_one)
    second = bootstrap_crewai_storage(workspace_two)

    assert first != second
    assert os.environ["CREWAI_STORAGE_DIR"] == str(second)
    assert os.environ["CREWAI_HOME"] == str(second)


def test_detect_primary_languages_skips_heavy_directories(tmp_path):
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "ignored.py").write_text(
        "print('ignored')\n", encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "readme.md").write_text("# kept\n", encoding="utf-8")

    languages = _detect_primary_languages(tmp_path, limit=100)

    assert "Markdown" in languages
    assert "Python" not in languages


def test_run_orchestration_propagates_verbose_flag(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class _FakeStateMachine:
        def __init__(
            self,
            workspace_dir: str,
            *,
            verbose: bool,
            strict_provider_validation: bool,
            max_provider_4xx: int,
            fail_on_research_empty: bool,
        ):
            captured["workspace_dir"] = workspace_dir
            captured["verbose"] = verbose
            captured["strict_provider_validation"] = strict_provider_validation
            captured["max_provider_4xx"] = max_provider_4xx
            captured["fail_on_research_empty"] = fail_on_research_empty
            self.run_id = "fake-run"
            self.provider_4xx_count = 0

        def execute_pipeline_with_metadata(self, raw_prompt: str):
            return True, {
                "run_id": "fake-run",
                "execution_log_path": str(
                    tmp_path / "workspace" / ".agent" / "memory" / "execution_log.json"
                ),
                "final_output_path": str(
                    tmp_path / "workspace" / ".agent" / "tmp" / "final_output.md"
                ),
                "reconstructed_prompt_path": str(
                    tmp_path
                    / "workspace"
                    / ".agent"
                    / "tmp"
                    / "reconstructed_prompt.md"
                ),
                "research_context_path": str(
                    tmp_path / "workspace" / ".agent" / "tmp" / "research-context.md"
                ),
                "provider_4xx_count": 0,
                "completion_status": "success",
                "completion_summary": "ok",
                "failed_stage": None,
                "stage_progress": {},
            }

        def get_completion_snapshot(self):
            return {
                "completion_status": "success",
                "completion_summary": "ok",
                "failed_stage": None,
                "stage_progress": {},
            }

    monkeypatch.setattr(
        "engine.orchestration_api.OrchestrationStateMachine",
        _FakeStateMachine,
    )

    config = OrchestrationRunConfig(
        prompt="smoke",
        workspace=tmp_path / "workspace",
        strict_provider_validation=False,
        verbose=True,
    )
    result = run_orchestration(config)

    assert result.success is True
    assert captured["verbose"] is True


def test_run_orchestration_preflight_uses_env_resolved_active_tiers(
    monkeypatch, tmp_path
):
    captured: dict[str, object] = {}

    class _FakeStateMachine:
        def __init__(self, *args, **kwargs):
            captured["constructed"] = True
            self.run_id = "fake-run"
            self.provider_4xx_count = 0

        def execute_pipeline_with_metadata(self, raw_prompt: str):
            return True, {
                "run_id": "fake-run",
                "execution_log_path": str(
                    tmp_path / "workspace" / ".agent" / "memory" / "execution_log.json"
                ),
                "final_output_path": str(
                    tmp_path / "workspace" / ".agent" / "tmp" / "final_output.md"
                ),
                "reconstructed_prompt_path": str(
                    tmp_path
                    / "workspace"
                    / ".agent"
                    / "tmp"
                    / "reconstructed_prompt.md"
                ),
                "research_context_path": str(
                    tmp_path / "workspace" / ".agent" / "tmp" / "research-context.md"
                ),
                "provider_4xx_count": 0,
                "completion_status": "success",
                "completion_summary": "ok",
                "failed_stage": None,
                "stage_progress": {},
            }

        def get_completion_snapshot(self):
            return {
                "completion_status": "success",
                "completion_summary": "ok",
                "failed_stage": None,
                "stage_progress": {},
            }

    monkeypatch.setattr(
        "engine.orchestration_api.OrchestrationStateMachine",
        _FakeStateMachine,
    )
    monkeypatch.setattr("engine.orchestration_api._project_root", lambda: tmp_path)
    with patch.dict(
        "os.environ",
        {
            "PRIMARY_LLM": "openai/gpt-5.4",
            "ORCHESTRATION_MODEL": "gemini/gemini-3.1-pro-preview",
            "L1_MODEL": "openai/gpt-5.2-codex",
            "L2_MODEL": "ollama/qwen3:8b",
            "L3_MODEL": "ollama/qwen2.5-coder:7b",
            "GOOGLE_API_KEY": "real_google",
            "OPENAI_API_KEY": "real_openai",
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        },
        clear=True,
    ):
        result = run_orchestration(
            OrchestrationRunConfig(
                prompt="smoke",
                workspace=tmp_path / "workspace",
                strict_provider_validation=True,
            )
        )

    assert result.success is True
    assert captured["constructed"] is True


def test_makefile_default_targets_include_workstream_suite():
    makefile = (Path(__file__).parent.parent / "Makefile").read_text(encoding="utf-8")
    assert makefile.count("test_improvement_plan_workstreams.py") >= 2


def test_tier1_manager_drops_unsupported_openai_proxy_params(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from engine.llm_config import model_spec_from_catalog
    from orchestrator.tier1_manager import GlobalMemorySnapshot, Tier2DomainAgent

    captured: dict[str, object] = {}

    async def _fake_acompletion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
        )

    monkeypatch.setattr(
        "orchestrator.tier1_manager._resolved_level2_spec",
        lambda: model_spec_from_catalog("ollama/qwen3:8b"),
    )
    monkeypatch.setattr(
        "orchestrator.tier1_manager.litellm.acompletion", _fake_acompletion
    )
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    agent = Tier2DomainAgent(
        agent_id="agent-1",
        domain_type="Research",
        memory_snapshot=GlobalMemorySnapshot(user_id="user-1"),
    )
    result = asyncio.run(
        agent.execute_fsm_playbook({"directive": "Analyze local architecture docs."})
    )

    assert result.status == "COMPLETED"
    assert captured["drop_params"] is True
    assert captured["api_base"] == "http://127.0.0.1:11434"
    assert "api_key" not in captured
    assert "reasoning_effort" not in captured
