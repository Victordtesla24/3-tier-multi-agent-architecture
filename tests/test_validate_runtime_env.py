from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch


def _load_validate_runtime_env_module():
    project_root = Path(__file__).resolve().parent.parent
    sys.path.append(str(project_root / "src"))
    script_path = project_root / "scripts" / "validate_runtime_env.py"
    spec = importlib.util.spec_from_file_location(
        "validate_runtime_env_script", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validate_runtime_env_structural_audit_prints_matrix(tmp_path, capsys):
    module = _load_validate_runtime_env_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".env").write_text(
        "\n".join(
            [
                "PRIMARY_LLM=openai/gpt-5.4",
                "ORCHESTRATION_MODEL=gemini/gemini-3.1-pro-preview",
                "L1_MODEL=openai/gpt-5.3-codex",
                "L2_MODEL=ollama/qwen3:8b",
                "L3_MODEL=ollama/qwen2.5-coder:7b",
                "L2_AGENT_SWARMS=2",
                "L3_AGENT_SWARMS=3",
                "GOOGLE_API_KEY=dummy_google",
                "OPENAI_API_KEY=dummy_openai",
                "OLLAMA_BASE_URL=http://127.0.0.1:11434/",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    status = module.main(
        [
            "--workspace",
            str(workspace),
            "--project-root",
            str(workspace),
        ]
    )
    output = capsys.readouterr().out

    assert status == 0
    assert "EFFECTIVE_TIER_MATRIX" in output
    assert "- orchestration: gemini/gemini-3.1-pro-preview" in output
    assert "- level1: openai/gpt-5.2-codex" in output
    assert "- level2: ollama/qwen3:8b" in output
    assert "- level3: ollama/qwen2.5-coder:7b" in output
    assert "SWARM_CAPS" in output
    assert "- level2: 2" in output
    assert "- level3: 3" in output
    assert "OLLAMA_BASE_URL" in output
    assert "http://127.0.0.1:11434" in output


def test_validate_runtime_env_live_mode_reports_safely(tmp_path, monkeypatch, capsys):
    module = _load_validate_runtime_env_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fake_secret = "super-secret-key"
    (workspace / ".env").write_text(
        "\n".join(
            [
                "ORCHESTRATION_MODEL=gemini/gemini-3.1-pro-preview",
                "L1_MODEL=openai/gpt-5.3-codex",
                "L2_MODEL=ollama/qwen3:8b",
                "L3_MODEL=ollama/qwen2.5-coder:14b",
                "GOOGLE_API_KEY=dummy_google",
                "OPENAI_API_KEY=dummy_openai",
                "OLLAMA_BASE_URL=http://127.0.0.1:11434",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class _FakeLLM:
        def call(self, _prompt: str) -> str:
            return "OK"

    import engine.llm_config as llm_config

    monkeypatch.setattr(llm_config, "build_llm", lambda _spec: _FakeLLM())

    with patch.dict("os.environ", {}, clear=True):
        status = module.main(
            [
                "--workspace",
                str(workspace),
                "--project-root",
                str(workspace),
                "--live",
            ]
        )
    output = capsys.readouterr().out

    assert status == 0
    assert "LIVE_PROBES" in output
    assert "level3: ok [ollama/qwen2.5-coder:14b]" in output
    assert "OLLAMA_BASE_URL" in output
    assert fake_secret not in output


def test_validate_runtime_env_probe_configured_providers_writes_json_report(
    tmp_path,
    monkeypatch,
    capsys,
):
    module = _load_validate_runtime_env_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    report_path = tmp_path / "provider-report.json"
    (workspace / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=dummy_openai",
                "GOOGLE_API_KEY=dummy_google",
                "OLLAMA_BASE_URL=http://127.0.0.1:11434",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class _FakeTarget:
        provider_id = "google"
        provider_group = "Google AI"
        probe_name = "generate_content"
        endpoint = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent"
        model = "gemini-3.1-pro-preview"

    class _FakeResult:
        def __init__(self):
            self.target = _FakeTarget()
            self.success = True
            self.failure_classification = None
            self.http_status = 200
            self.latency_ms = 123
            self.response_preview = "ACK"

        def to_dict(self):
            return {
                "target": {
                    "provider_id": self.target.provider_id,
                    "provider_group": self.target.provider_group,
                    "probe_name": self.target.probe_name,
                    "method": "POST",
                    "endpoint": self.target.endpoint,
                    "model": self.target.model,
                },
                "success": self.success,
                "failure_classification": self.failure_classification,
                "http_status": self.http_status,
                "latency_ms": self.latency_ms,
                "response_preview": self.response_preview,
            }

    monkeypatch.setattr(
        module, "probe_configured_providers", lambda *_args, **_kwargs: (_FakeResult(),)
    )

    with patch.dict("os.environ", {}, clear=True):
        status = module.main(
            [
                "--workspace",
                str(workspace),
                "--project-root",
                str(workspace),
                "--probe-configured-providers",
                "--report-path",
                str(report_path),
            ]
        )

    output = capsys.readouterr().out
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert status == 0
    assert "CONFIGURED_PROVIDER_PROBES" in output
    assert "google.generate_content: ok" in output
    assert report["provider_probe_results"][0]["http_status"] == 200
    assert report["configured_providers"][0]["provider_group"] == "OpenAI"


def test_validate_runtime_env_probe_configured_providers_returns_non_zero_on_failure(
    tmp_path,
    monkeypatch,
    capsys,
):
    module = _load_validate_runtime_env_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = "super-secret-key"
    (workspace / ".env").write_text(
        "\n".join(
            [
                f"OPENAI_API_KEY={secret}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class _FakeTarget:
        provider_id = "openai"
        provider_group = "OpenAI"
        probe_name = "chat_completions"
        endpoint = "https://api.openai.com/v1/chat/completions"
        model = "gpt-4o-mini"

    class _FakeResult:
        def __init__(self):
            self.target = _FakeTarget()
            self.success = False
            self.failure_classification = "auth_invalid"
            self.http_status = 401
            self.latency_ms = 111
            self.response_preview = "[REDACTED]"

        def to_dict(self):
            return {
                "target": {
                    "provider_id": self.target.provider_id,
                    "provider_group": self.target.provider_group,
                    "probe_name": self.target.probe_name,
                    "method": "POST",
                    "endpoint": self.target.endpoint,
                    "model": self.target.model,
                },
                "success": self.success,
                "failure_classification": self.failure_classification,
                "http_status": self.http_status,
                "latency_ms": self.latency_ms,
                "response_preview": self.response_preview,
            }

    monkeypatch.setattr(
        module, "probe_configured_providers", lambda *_args, **_kwargs: (_FakeResult(),)
    )

    with patch.dict("os.environ", {}, clear=True):
        status = module.main(
            [
                "--workspace",
                str(workspace),
                "--project-root",
                str(workspace),
                "--probe-configured-providers",
            ]
        )

    output = capsys.readouterr().out
    assert status == 1
    assert "classification=auth_invalid" in output
    assert secret not in output
