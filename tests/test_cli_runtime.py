"""CLI runtime regression tests for initialization UX and lightweight execution flow."""

import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path

from engine.logging_utils import redact_sensitive_text
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
    monkeypatch.setattr(
        "engine.orchestration_api.run_orchestration",
        lambda cfg: SimpleNamespace(
            success=True,
            workspace=cfg.workspace,
            prompt=cfg.prompt,
            strict_provider_validation=cfg.strict_provider_validation,
            max_provider_4xx=cfg.max_provider_4xx,
            fail_on_research_empty=cfg.fail_on_research_empty,
            run_id="test-run-id",
            execution_log_path=cfg.workspace / ".agent" / "memory" / "execution_log.json",
            final_output_path=cfg.workspace / ".agent" / "tmp" / "final_output.md",
            reconstructed_prompt_path=cfg.workspace / ".agent" / "tmp" / "reconstructed_prompt.md",
            research_context_path=cfg.workspace / ".agent" / "tmp" / "research-context.md",
            provider_4xx_count=0,
            completion_status="success",
            completion_summary="ok",
            failed_stage=None,
            execution_mode="task_graph",
            plan_id="plan-123",
            task_count=2,
            parallel_batch_count=1,
            worker_retry_count=0,
            task_failure_count=0,
            stage_progress={},
            error=None,
        ),
    )

    exit_code = module.main()
    captured = capsys.readouterr()
    stdout_lines = [line for line in captured.out.splitlines() if line.strip()]

    assert exit_code == 0
    assert stdout_lines[0] == STATUS_BANNER


def test_log_redaction_masks_api_keys():
    sample = (
        "POST https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3-pro-preview:generateContent?key=TEST_EXAMPLE_KEY_123"
    )
    redacted = redact_sensitive_text(sample)
    assert "TEST_EXAMPLE_KEY_123" not in redacted
    assert "key=[REDACTED]" in redacted
