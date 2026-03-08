---
title: "fix: codebase review, debug, and targeted refactor"
type: fix
status: completed
date: 2026-03-09
---

# fix: codebase review, debug, and targeted refactor

## Overview

Run a focused quality pass on the current branch by reviewing the codebase, reproducing high-risk defects, implementing targeted fixes/refactors, and validating behavior with tests.

## Problem Statement / Motivation

There are open reliability concerns and ready todo findings in the current branch. We need to convert review findings into concrete fixes with minimal, production-safe refactoring.

## Scope

- [x] Perform review-first analysis of current branch code and existing todo findings.
- [x] Reproduce at least one high-priority bug and fix it.
- [x] Apply targeted refactor only where it improves correctness/maintainability.
- [x] Validate changes with focused tests and keep behavior deterministic.

## Acceptance Criteria

- [x] At least one P1/P2 reliability issue is fixed in source code.
- [x] Relevant tests pass for the changed area.
- [x] Refactor does not alter unrelated behavior.
- [x] Plan checkboxes are fully updated to reflect work completion.

## Implementation Plan

### Phase 1: Review and triage

- [x] Inspect current branch diffs and `todos/` items marked `ready`.
- [x] Select one high-severity issue with clear repro path.
- [x] Capture root cause and impacted modules.

### Phase 2: Debug and fix

- [x] Reproduce failure via tests or deterministic command.
- [x] Implement minimal fix in affected module(s).
- [x] Add/update tests to prevent regression.

### Phase 3: Refactor and verify

- [x] Apply small refactor around touched code to improve clarity/safety.
- [x] Run targeted test suite for changed components.
- [x] Update plan completion state and summarize outcomes.

## Candidate Sources

- `todos/009-ready-p1-a2ui-ack-state-not-consumed-by-view-agent.md`
- `todos/010-ready-p1-runtime-config-tool-exposes-secrets.md`
- `todos/011-ready-p1-unbounded-nested-orchestration-via-submit-objective-tool.md`
- `todos/012-ready-p2-ack-state-corruption-fallback-loses-existing-data.md`
- `src/view/a2ui_protocol.py`
- `src/engine/orchestration_tools.py`
- `src/engine/runtime_graph.py`

## Pipeline Defaults

- Non-interactive execution.
- Deterministic defaults for ambiguous branch/tooling choices.
- Headless mode for browser-test step.

## Deepened Plan Notes

- Triage prioritized P1 reliability issue `todos/011-ready-p1-unbounded-nested-orchestration-via-submit-objective-tool.md`.
- Deterministic policy selected: block nested `submit_objective` once depth is non-zero.
- Added explicit warning telemetry for blocked nested attempts to improve forensic visibility.

## Execution Summary

- Hardened nested orchestration guard:
  - `src/engine/orchestration_tools.py`
  - `MAX_SUBMIT_OBJECTIVE_DEPTH` reduced from `3` to `1`.
  - Added warning log: `SUBMIT_OBJECTIVE_BLOCKED_NESTED`.
- Added regression test coverage:
  - `tests/test_capability_parity.py::test_submit_objective_logs_blocked_nested_attempt`
- Verification:
  - `PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_capability_parity.py tests/test_orchestration_hardening.py -q`
  - `17 passed`
