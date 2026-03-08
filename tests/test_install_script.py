from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path


def _parse_env(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        payload[key] = value.strip().strip('"')
    return payload


def _copy_tree(src: Path, dest: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def _prepare_repo_copy(tmp_path: Path) -> Path:
    project_root = Path(__file__).resolve().parent.parent
    repo_copy = tmp_path / "repo"
    repo_copy.mkdir()

    for relative in (
        "install.sh",
        "scripts/integrate_crewai.sh",
        ".env.template",
        ".agent",
        "docs/architecture",
        "src/engine/__init__.py",
        "src/engine/model_catalog.py",
        "src/engine/runtime_env.py",
        "src/engine/config_manager.py",
        "src/engine/workspace_tools.py",
        "src/engine/project_root_tools.py",
    ):
        _copy_tree(project_root / relative, repo_copy / relative)

    install_path = repo_copy / "install.sh"
    install_path.chmod(install_path.stat().st_mode | stat.S_IXUSR)
    integrate_path = repo_copy / "scripts" / "integrate_crewai.sh"
    integrate_path.chmod(integrate_path.stat().st_mode | stat.S_IXUSR)

    test_support = repo_copy / "test_support" / "crewai"
    test_support.mkdir(parents=True)
    (test_support / "__init__.py").write_text("", encoding="utf-8")
    (test_support / "tools.py").write_text(
        "class BaseTool:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (repo_copy / "test_support" / "pydantic.py").write_text(
        "class BaseModel:\n"
        "    pass\n"
        "\n"
        "def Field(default=None, **kwargs):\n"
        "    return default\n",
        encoding="utf-8",
    )
    return repo_copy


def _prepare_fake_bin(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()

    uv_path = fake_bin / "uv"
    uv_path.write_text(
        "#!/bin/sh\n"
        'echo "fake uv $@" >> "$UV_FAKE_LOG"\n'
        'if [ -n "$UV_PROJECT_ENVIRONMENT" ]; then\n'
        '  mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"\n'
        f'  ln -sf "{sys.executable}" "$UV_PROJECT_ENVIRONMENT/bin/python"\n'
        f'  ln -sf "{sys.executable}" "$UV_PROJECT_ENVIRONMENT/bin/python3"\n'
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    uv_path.chmod(0o755)

    curl_path = fake_bin / "curl"
    curl_path.write_text(
        "#!/bin/sh\n" 'echo "fake curl $@" >> "$CURL_FAKE_LOG"\n' "exit 0\n",
        encoding="utf-8",
    )
    curl_path.chmod(0o755)

    python_path = fake_bin / "python3"
    python_path.write_text(
        "#!/bin/sh\n" f'exec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    python_path.chmod(0o755)

    return fake_bin


def _run_installer(
    repo_copy: Path,
    tmp_path: Path,
    *,
    model_id: str,
    api_key: str,
) -> subprocess.CompletedProcess[str]:
    fake_home = tmp_path / "home"
    gemini_dir = fake_home / ".gemini"
    gemini_dir.mkdir(parents=True)
    (gemini_dir / "GEMINI.md").write_text("existing: true\n", encoding="utf-8")

    fake_bin = _prepare_fake_bin(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(fake_home),
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "ANTIGRAVITY_NONINTERACTIVE": "1",
            "ANTIGRAVITY_MODEL_ID": model_id,
            "ANTIGRAVITY_API_KEY": api_key,
            "UV_FAKE_LOG": str(tmp_path / "uv.log"),
            "CURL_FAKE_LOG": str(tmp_path / "curl.log"),
        }
    )

    return subprocess.run(
        ["bash", "install.sh"],
        cwd=repo_copy,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_integrate_crewai(
    repo_copy: Path,
    tmp_path: Path,
) -> subprocess.CompletedProcess[str]:
    fake_bin = _prepare_fake_bin(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
            "PYTHONPATH": str(repo_copy / "test_support"),
            "UV_FAKE_LOG": str(tmp_path / "uv.log"),
            "CURL_FAKE_LOG": str(tmp_path / "curl.log"),
        }
    )

    return subprocess.run(
        ["bash", "scripts/integrate_crewai.sh"],
        cwd=repo_copy,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_install_script_noninteractive_openai_default(tmp_path):
    repo_copy = _prepare_repo_copy(tmp_path)
    result = _run_installer(
        repo_copy,
        tmp_path,
        model_id="openai/gpt-5.4",
        api_key="test-openai-key",
    )

    assert result.returncode == 0, result.stderr + result.stdout

    env_payload = _parse_env(repo_copy / ".env")
    assert env_payload["PRIMARY_LLM"] == "openai/gpt-5.4"
    assert env_payload["ORCHESTRATION_MODEL"] == "openai/gpt-5.4"
    assert env_payload["L1_MODEL"] == "openai/gpt-5.4"
    assert env_payload["L2_MODEL"] == "openai/gpt-5.4"
    assert env_payload["L3_MODEL"] == "openai/gpt-5.4"
    assert env_payload["L2_AGENT_SWARMS"] == "2"
    assert env_payload["L3_AGENT_SWARMS"] == "3"
    assert env_payload["OPENAI_API_KEY"] == "test-openai-key"
    assert env_payload["GOOGLE_API_KEY"] == "your_google_api_key_here"
    assert env_payload["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"

    gemini_md = (tmp_path / "home" / ".gemini" / "GEMINI.md").read_text(
        encoding="utf-8"
    )
    assert "default_model: OpenAI GPT-5.4 (Latest Flagship)" in gemini_md


def test_install_script_noninteractive_ollama_selection(tmp_path):
    repo_copy = _prepare_repo_copy(tmp_path)
    result = _run_installer(
        repo_copy,
        tmp_path,
        model_id="ollama/qwen3:14b",
        api_key="",
    )

    assert result.returncode == 0, result.stderr + result.stdout

    env_payload = _parse_env(repo_copy / ".env")
    assert env_payload["PRIMARY_LLM"] == "ollama/qwen3:14b"
    assert env_payload["ORCHESTRATION_MODEL"] == "ollama/qwen3:14b"
    assert env_payload["L1_MODEL"] == "ollama/qwen3:14b"
    assert env_payload["L2_MODEL"] == "ollama/qwen3:14b"
    assert env_payload["L3_MODEL"] == "ollama/qwen3:14b"
    assert env_payload["L2_AGENT_SWARMS"] == "2"
    assert env_payload["L3_AGENT_SWARMS"] == "3"
    assert env_payload["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"
    assert env_payload["OPENAI_API_KEY"] == "your_openai_api_key_here"
    assert env_payload["GOOGLE_API_KEY"] == "your_google_api_key_here"

    gemini_md = (tmp_path / "home" / ".gemini" / "GEMINI.md").read_text(
        encoding="utf-8"
    )
    assert "default_model: Ollama Qwen 3 14B (Reasoning)" in gemini_md


def test_install_script_noninteractive_deepseek_selection(tmp_path):
    repo_copy = _prepare_repo_copy(tmp_path)
    result = _run_installer(
        repo_copy,
        tmp_path,
        model_id="deepseek/deepseek-chat",
        api_key="test-deepseek-key",
    )

    assert result.returncode == 0, result.stderr + result.stdout

    env_payload = _parse_env(repo_copy / ".env")
    assert env_payload["PRIMARY_LLM"] == "deepseek/deepseek-chat"
    assert env_payload["ORCHESTRATION_MODEL"] == "deepseek/deepseek-chat"
    assert env_payload["DEEPSEEK_API_KEY"] == "test-deepseek-key"
    assert env_payload["DEEPSEEK_BASE_URL"] == "https://api.deepseek.com/v1"
    assert env_payload["GOOGLE_API_KEY"] == "your_google_api_key_here"
    assert env_payload["OPENAI_API_KEY"] == "your_openai_api_key_here"
    assert env_payload["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"

    gemini_md = (tmp_path / "home" / ".gemini" / "GEMINI.md").read_text(
        encoding="utf-8"
    )
    assert "default_model: DeepSeek Chat (Reasoning/Coding)" in gemini_md


def test_install_script_normalizes_existing_matrix_and_repairs_missing_newline(
    tmp_path,
):
    repo_copy = _prepare_repo_copy(tmp_path)
    (repo_copy / ".env").write_text(
        "\n".join(
            [
                "L1_MODEL=openai/gpt-5.2-codex",
                "L2_MODEL=ollama/qwen3:14b",
                "L3_MODEL=ollama/qwen2.5-coder:14b",
                "L2_AGENT_SWARMS=9",
                "L3_AGENT_SWARMS=11",
                "OLLAMA_BASE_URL=http://127.0.0.1:11434",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_installer(
        repo_copy,
        tmp_path,
        model_id="openai/gpt-5.4",
        api_key="test-openai-key",
    )

    assert result.returncode == 0, result.stderr + result.stdout

    env_payload = _parse_env(repo_copy / ".env")
    assert env_payload["PRIMARY_LLM"] == "openai/gpt-5.4"
    assert env_payload["ORCHESTRATION_MODEL"] == "openai/gpt-5.4"
    assert env_payload["L1_MODEL"] == "openai/gpt-5.4"
    assert env_payload["L2_MODEL"] == "openai/gpt-5.4"
    assert env_payload["L3_MODEL"] == "openai/gpt-5.4"
    assert env_payload["L2_AGENT_SWARMS"] == "2"
    assert env_payload["L3_AGENT_SWARMS"] == "3"
    assert env_payload["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"


def test_integrate_crewai_handles_empty_runtime_warnings(tmp_path):
    repo_copy = _prepare_repo_copy(tmp_path)
    (repo_copy / ".env").write_text(
        "\n".join(
            [
                'PRIMARY_LLM="gemini/gemini-3.1-pro-preview"',
                'ORCHESTRATION_MODEL="gemini/gemini-3.1-pro-preview"',
                'GOOGLE_API_KEY="test-google-key"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_integrate_crewai(repo_copy, tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "CrewAI integration complete!" in result.stdout
    assert "❌ ERROR:" not in result.stdout
    assert "local CrewAI tool compatibility check passed" in result.stdout
