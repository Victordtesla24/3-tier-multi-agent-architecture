---
title: "fix: update README content while preserving existing look-and-feel"
type: fix
status: completed
date: 2026-03-09
---

# fix: update README content while preserving existing look-and-feel

## Overview

Update `README.md` to improve operational clarity and command fidelity without changing its visual style, section hierarchy, or presentation language.

## Problem Statement / Motivation

README drift can break clean-room onboarding and cause command failures even when the architecture is correct. We need targeted content corrections while keeping the current executive narrative structure, badges, tables, and diagram style intact.

## Scope

- [x] Preserve current README look-and-feel: headings, markdown structure, table/diagram style, badge style, and narrative voice.
- [x] Update only content that affects execution accuracy, command correctness, and reproducibility.
- [x] Keep edits minimal and localized; avoid full rewrites.

## Acceptance Criteria

- [x] README still renders with the same visual structure and formatting style.
- [x] Commands documented in README are accurate for the current repository.
- [x] Any corrected command paths and examples are runnable from project root.
- [x] No unrelated sections are reworded unnecessarily.

## Implementation Plan

### Phase 1: Baseline + drift detection

- [x] Scan `README.md` for command snippets, setup steps, and operational claims likely to drift.
- [x] Cross-check command snippets against current repository files/scripts/Make targets.
- [x] Identify the minimal set of lines requiring correction.

### Phase 2: Minimal in-place updates

- [x] Apply small line-level edits in `README.md` only where drift exists.
- [x] Retain existing section order, tone, and formatting conventions.
- [x] Avoid introducing new visual patterns.

### Phase 3: Verification

- [x] Validate edited commands against repository reality (`Makefile`, `scripts/`, CLI entry points).
- [x] Run lightweight checks for accidental formatting regressions.
- [x] Mark completion checkboxes in this plan.

## Deepened Plan Notes

- Verified the CLI workspace precedence from source (`src/orchestrator/antigravity-cli.py`) before editing docs.
- Constrained edits to one operationally incorrect README line to preserve style fidelity.
- Verified no markdown structural drift by limiting the patch to inline text replacement.

## Execution Summary

- Corrected README workspace fallback order to match runtime behavior:
  1. `ANTIGRAVITY_WORKSPACE_DIR`
  2. `ANTIGRAVITY_WORKSPACE_ROOT`
  3. `<project_root>`

## Files Involved

- `README.md`
- `Makefile`
- `scripts/integrate_crewai.sh`
- `scripts/validate_runtime_env.py`
- `src/orchestrator/antigravity-cli.py`

## Risks

- Over-editing can alter the established look-and-feel.
- Under-editing can leave operational drift unresolved.

## Mitigation

- Apply only deterministic, high-confidence corrections.
- Keep patch scoped to affected lines and re-check markdown structure after edits.
