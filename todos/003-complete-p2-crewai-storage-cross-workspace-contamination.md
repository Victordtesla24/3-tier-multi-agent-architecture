---
status: complete
priority: p2
issue_id: "003"
tags: [code-review, reliability, state-isolation, orchestration]
dependencies: []
---

# Rebind CrewAI Storage Per Workspace Instead of setdefault

## Problem Statement

Storage bootstrap uses `os.environ.setdefault`, which can preserve previously bound storage directories in long-lived processes. Subsequent runs for different workspaces may share persisted state unexpectedly.

## Findings

- `CREWAI_STORAGE_DIR` and `CREWAI_HOME` are set with `setdefault`.
- If environment variables are already present, workspace rebinding does not occur.
- Evidence:
  - `/src/engine/crewai_storage.py:30`
  - `/src/engine/crewai_storage.py:31`

## Proposed Solutions

### Option 1: Force Rebind to Current Workspace (Recommended)

**Approach:** Replace `setdefault` with direct assignment for `CREWAI_STORAGE_DIR` and `CREWAI_HOME`.

**Pros:**
- Deterministic workspace isolation per run.
- Minimal complexity.

**Cons:**
- Might override caller-intended custom path unless explicit opt-out is added.

**Effort:** Small

**Risk:** Low

---

### Option 2: Add Explicit `force` Parameter + Guard

**Approach:** Default to rebind; allow opt-out only through explicit bootstrap options.

**Pros:**
- Flexible while still safe by default.

**Cons:**
- Additional API surface and test cases.

**Effort:** Medium

**Risk:** Low

## Recommended Action
Applied Option 1. Replaced `setdefault` with direct assignment in storage bootstrap so each workspace run deterministically rebinds CrewAI storage.


## Technical Details

Affected components:
- Runtime storage bootstrap
- Multi-workspace orchestration flows

## Resources

- Files:
  - `src/engine/crewai_storage.py`

## Acceptance Criteria

- [x] New workspace run always binds storage to that workspace by default.
- [x] Tests cover two different workspace bootstraps in a single process.
- [x] Documentation explains override behavior if supported.

## Work Log
### 2026-03-05 - Completed

**By:** Codex

**Actions:**
- Updated `bootstrap_crewai_storage` to always assign `CREWAI_STORAGE_DIR` and `CREWAI_HOME`.
- Added regression test that bootstraps two workspaces in one process and verifies rebinding.

**Validation:**
- `make test-pytest` (56 passed)
- `make test-e2e` (7 passed)

### 2026-03-05 - Initial Discovery

**By:** Codex

**Actions:**
- Reviewed environment bootstrap behavior.
- Assessed multi-run contamination risk for persistent hosts.

**Learnings:**
- `setdefault` is unsafe when per-run isolation is required.
