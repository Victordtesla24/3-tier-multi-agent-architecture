---
status: complete
priority: p3
issue_id: "006"
tags: [code-review, quality, testing, ci]
dependencies: []
---

# Include New Workstream Tests in Default Make Targets

## Problem Statement

A new test module exists but is not included in default `make test-pytest` / `make test` targets, which can allow regressions to bypass standard local/CI workflows.

## Findings

- `tests/test_improvement_plan_workstreams.py` exists and passes.
- Makefile targets explicitly list test files and exclude this module.
- Evidence:
  - `/tests/test_improvement_plan_workstreams.py:1`
  - `/Makefile:27`
  - `/Makefile:33`

## Proposed Solutions

### Option 1: Add Module to Existing Explicit Targets (Recommended)

**Approach:** Append `test_improvement_plan_workstreams.py` to `test-pytest` target list.

**Pros:**
- Minimal change.
- Keeps deterministic curated test set.

**Cons:**
- Requires future manual updates when adding files.

**Effort:** Small

**Risk:** Low

---

### Option 2: Shift to Pattern-Based Collection

**Approach:** Run `pytest tests/` with markers/exclusions instead of explicit file list.

**Pros:**
- Automatically includes new tests.

**Cons:**
- May run slower or include unstable tests unless carefully scoped.

**Effort:** Medium

**Risk:** Medium

## Recommended Action
Applied Option 1. Added `test_improvement_plan_workstreams.py` to `test-audit` and `test-pytest` default Make targets. Also added the new hardening suite to the same targets to keep these fixes covered.


## Technical Details

Affected components:
- Makefile test orchestration
- CI/local confidence in new workstream coverage

## Resources

- Files:
  - `Makefile`
  - `tests/test_improvement_plan_workstreams.py`

## Acceptance Criteria

- [x] Default `make test` path executes new workstream tests.
- [x] CI output shows module executed.

## Work Log
### 2026-03-05 - Completed

**By:** Codex

**Actions:**
- Updated Makefile explicit pytest lists to include `test_improvement_plan_workstreams.py`.
- Included `test_orchestration_hardening.py` in default curated targets.
- Verified collection and execution through `make test-pytest`.

**Validation:**
- `make test-pytest` (56 passed, includes workstream + hardening modules)
- `make test-e2e` (7 passed)

### 2026-03-05 - Initial Discovery

**By:** Codex

**Actions:**
- Compared Makefile test targets against test directory contents.
- Confirmed omission of new workstream test module.

**Learnings:**
- Curated test lists require discipline; add guardrails to prevent silent omissions.
