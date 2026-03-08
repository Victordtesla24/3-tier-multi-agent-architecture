from __future__ import annotations

import socket
from pathlib import Path
import sys
from unittest.mock import patch
from urllib import error

sys.path.append(str(Path(__file__).parent.parent / "src"))


def _write_full_provider_env(
    workspace: Path,
    *,
    google_key: str = "real-google-secret",
    deepseek_key: str = "real-deepseek-secret",
) -> None:
    (workspace / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=real-openai-secret",
                f"GEMINI_API_KEY={google_key}",
                f"DEEPSEEK_API_KEY={deepseek_key}",
                "DEEPSEEK_BASE_URL=https://api.deepseek.com/v1",
                "OLLAMA_BASE_URL=http://127.0.0.1:11434/",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_classify_failure_distinguishes_provider_error_modes():
    from engine.provider_healthchecks import _classify_failure

    assert _classify_failure(401, "invalid api key") == "auth_invalid"
    assert (
        _classify_failure(
            404,
            "models/gemini-3.1-pro-preview is not found for API version v1beta",
        )
        == "model_unavailable"
    )
    assert _classify_failure(404, "route not found") == "endpoint_misconfigured"
    assert _classify_failure(None, "request timed out") == "timeout"
    assert _classify_failure(500, "unexpected upstream failure") == "unknown"


def test_probe_configured_providers_handles_aliases_and_redacts_secrets(
    tmp_path,
    monkeypatch,
):
    from engine.provider_healthchecks import probe_configured_providers

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    google_secret = "super-secret-google"
    _write_full_provider_env(workspace, google_key=google_secret)

    def _fake_get(url, *, headers, timeout_s):
        del headers, timeout_s
        return 200, f"models ok {url}", 12

    def _fake_post_json(url, payload, *, headers, timeout_s):
        del payload, timeout_s
        auth_value = headers.get("Authorization", "")
        if "generativelanguage.googleapis.com" in url:
            auth_value = "real-google-secret"
        return 200, f"probe ok {auth_value}", 34

    monkeypatch.setattr("engine.provider_healthchecks._get", _fake_get)
    monkeypatch.setattr("engine.provider_healthchecks._post_json", _fake_post_json)

    with patch.dict("os.environ", {}, clear=True):
        results = probe_configured_providers(workspace, workspace)

    google_results = [
        result for result in results if result.target.provider_id == "google"
    ]
    openai_result = next(
        result for result in results if result.target.provider_id == "openai"
    )
    deepseek_result = next(
        result for result in results if result.target.provider_id == "deepseek"
    )
    ollama_result = next(
        result for result in results if result.target.provider_id == "ollama"
    )

    assert len(google_results) == 2
    assert all(result.success is True for result in google_results)
    assert openai_result.target.endpoint == "https://api.openai.com/v1/chat/completions"
    assert deepseek_result.target.endpoint == "https://api.deepseek.com/v1/chat/completions"
    assert deepseek_result.target.model == "deepseek-chat"
    assert google_results[0].configured_api_key_keys == ("GEMINI_API_KEY",)
    assert google_secret not in google_results[0].response_preview
    assert "[REDACTED]" in google_results[0].response_preview
    assert ollama_result.configured_api_key_keys == ()
    assert ollama_result.configured_base_url_keys == ("OLLAMA_BASE_URL",)
    assert ollama_result.target.endpoint == "http://127.0.0.1:11434/api/tags"


def test_probe_configured_providers_probes_deepseek(tmp_path, monkeypatch):
    from engine.provider_healthchecks import probe_configured_providers

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    deepseek_secret = "super-secret-deepseek"
    _write_full_provider_env(workspace, deepseek_key=deepseek_secret)

    def _fake_get(url, *, headers, timeout_s):
        del headers, timeout_s
        return 200, f"models ok {url}", 12

    def _fake_post_json(url, payload, *, headers, timeout_s):
        del payload, timeout_s
        if "api.deepseek.com" in url:
            return 200, f"probe ok {headers.get('Authorization', '')}", 22
        return 200, "ok", 10

    monkeypatch.setattr("engine.provider_healthchecks._get", _fake_get)
    monkeypatch.setattr("engine.provider_healthchecks._post_json", _fake_post_json)

    with patch.dict("os.environ", {}, clear=True):
        results = probe_configured_providers(workspace, workspace)

    deepseek_result = next(
        result for result in results if result.target.provider_id == "deepseek"
    )
    assert deepseek_result.success is True
    assert deepseek_secret not in deepseek_result.response_preview
    assert "[REDACTED]" in deepseek_result.response_preview


def test_probe_configured_providers_classifies_auth_invalid(tmp_path, monkeypatch):
    from engine.provider_healthchecks import probe_configured_providers

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _write_full_provider_env(workspace)

    def _fake_get(url, *, headers, timeout_s):
        del url, headers, timeout_s
        return 200, "models ok", 10

    def _fake_post_json(url, payload, *, headers, timeout_s):
        del payload, headers, timeout_s
        if "api.openai.com" in url:
            return 401, '{"error":{"message":"invalid api key"}}', 55
        return 200, "ok", 10

    monkeypatch.setattr("engine.provider_healthchecks._get", _fake_get)
    monkeypatch.setattr("engine.provider_healthchecks._post_json", _fake_post_json)

    with patch.dict("os.environ", {}, clear=True):
        results = probe_configured_providers(workspace, workspace)

    openai_result = next(
        result for result in results if result.target.provider_id == "openai"
    )
    assert openai_result.success is False
    assert openai_result.failure_classification == "auth_invalid"
    assert openai_result.http_status == 401


def test_probe_configured_providers_classifies_timeout_and_redacts_secret(
    tmp_path,
    monkeypatch,
):
    from engine.provider_healthchecks import probe_configured_providers

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    google_secret = "super-secret-google"
    _write_full_provider_env(workspace, google_key=google_secret)
    env_path = workspace / ".env"
    env_path.write_text(
        env_path.read_text(encoding="utf-8").replace(
            "GEMINI_API_KEY=super-secret-google",
            f"GEMINI_API_KEY={google_secret}",
        ),
        encoding="utf-8",
    )

    def _fake_get(url, *, headers, timeout_s):
        del url, headers, timeout_s
        return 200, "models ok", 10

    def _fake_post_json(url, payload, *, headers, timeout_s):
        del payload, headers, timeout_s
        if "generativelanguage.googleapis.com" in url:
            raise error.URLError(socket.timeout(f"timed out {google_secret}"))
        return 200, "ok", 10

    monkeypatch.setattr("engine.provider_healthchecks._get", _fake_get)
    monkeypatch.setattr("engine.provider_healthchecks._post_json", _fake_post_json)

    with patch.dict("os.environ", {}, clear=True):
        results = probe_configured_providers(workspace, workspace)

    google_result = next(
        result
        for result in results
        if result.target.provider_id == "google"
        and result.target.probe_name == "generate_content"
    )
    assert google_result.success is False
    assert google_result.failure_classification == "timeout"
    assert google_secret not in google_result.response_preview
    assert "[REDACTED]" in google_result.response_preview
