from __future__ import annotations

from pathlib import Path

from engine.config_manager import merge_config_safely


def test_merge_config_safely_creates_parent_dirs_and_target_file(tmp_path):
    target = tmp_path / ".agent" / "tmp" / "mock_gemini.md"
    assert not target.exists()
    assert not target.parent.exists()

    merge_config_safely(
        str(target),
        {
            "orchestration_entry": ".agent/workflows/3-tier-orchestration.md",
            "default_model": "OpenAI GPT-5.4 (Latest Flagship)",
        },
    )

    assert target.parent.exists()
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "orchestration_entry" in content
    assert "default_model" in content
    assert Path(f"{target}.bak").exists()
