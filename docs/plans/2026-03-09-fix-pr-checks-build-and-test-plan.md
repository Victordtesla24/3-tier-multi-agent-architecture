---
title: "fix: restore build_and_test PR checks"
type: fix
status: completed
date: 2026-03-09
---

# fix: restore build_and_test PR checks

## Overview

Unblock PR #1 failing GitHub check `build_and_test` by fixing CI command compatibility and aligning tests with current installer matrix behavior.

## Problem Statement

- [x] `Validate Configuration Merger Atomic Safety` failed because `src/engine/config_manager.py` attempted `touch()` on `.agent/tmp/mock_gemini.md` without ensuring parent directories exist.
- [x] Installer tests expected all tiers (`L1/L2/L3`) to mirror the selected `PRIMARY_LLM`, which no longer matches the current documented matrix defaults.

## Implementation Plan

### Phase 1: Reproduce and triage
- [x] Inspect failing GitHub Actions job logs for PR #1.
- [x] Reproduce CI failure locally with the same command.
- [x] Confirm root cause in `src/engine/config_manager.py`.

### Phase 2: Fix and harden
- [x] Patch config merger to create parent directories before touching target file.
- [x] Add regression test ensuring nested target paths are created safely.
- [x] Update installer tests to match current tiered-default contract.

### Phase 3: Validate
- [x] Run CI parity command: `PYTHONPATH=src python src/engine/config_manager.py .agent/tmp/mock_gemini.md`.
- [x] Run targeted tests for changed areas.
- [x] Run CI-equivalent audit + test command set used in workflow.

## Files Changed

- `src/engine/config_manager.py`
- `tests/test_config_manager.py` (new)
- `tests/test_install_script.py`

## Validation Evidence

- `PYTHONPATH=src ./.venv/bin/python src/engine/config_manager.py .agent/tmp/mock_gemini.md` ✅
- `PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_config_manager.py tests/test_install_script.py -q` → `6 passed` ✅
- `PYTHONPATH=../src ../.venv/bin/python -m pytest test_architecture.py test_crewai_integration.py test_contracts.py test_cli_runtime.py test_e2e.py -v -p no:cacheprovider` (from `tests/`) → `76 passed` ✅
- `ruff check src/engine/config_manager.py tests/test_config_manager.py tests/test_install_script.py` ✅

## Post-Deploy Monitoring & Validation

No additional operational monitoring required: this change is CI/test/installer-path hardening with no runtime production behavior impact.
