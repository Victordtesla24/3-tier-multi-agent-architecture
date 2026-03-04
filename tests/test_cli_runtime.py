"""CLI runtime regression tests for initialization UX and lightweight execution flow."""

import importlib.util
import sys
from pathlib import Path

from engine.status_banner import STATUS_BANNER


def _load_cli_module():
    cli_path = Path(__file__).parent.parent / "src" / "orchestrator" / "antigravity-cli.py"
    spec = importlib.util.spec_from_file_location("antigravity_cli_entrypoint", cli_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_cli_emits_canonical_status_banner_first_line(tmp_path, monkeypatch, capsys):
    module = _load_cli_module()
    workspace = tmp_path / "cli_workspace"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "antigravity-cli.py",
            "--prompt",
            "smoke test",
            "--workspace",
            str(workspace),
        ],
    )

    monkeypatch.setattr(module.ArchitectureHealer, "validate_and_heal", lambda *args, **kwargs: True)
    monkeypatch.setattr(module.OrchestrationStateMachine, "execute_pipeline", lambda *args, **kwargs: True)

    exit_code = module.main()
    captured = capsys.readouterr()
    stdout_lines = [line for line in captured.out.splitlines() if line.strip()]

    assert exit_code == 0
    assert stdout_lines[0] == STATUS_BANNER
