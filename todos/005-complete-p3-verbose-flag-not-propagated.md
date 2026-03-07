---
status: complete
priority: p3
issue_id: "005"
tags: [code-review, quality, configurability, cli]
dependencies: []
---

# Propagate Verbose Flag Through Orchestration Stack

## Problem Statement

The API/CLI surfaces capture a `verbose` setting, but state-machine orchestration currently instantiates the orchestrator with `verbose=True`, effectively ignoring caller intent.

## Findings

- `OrchestrationRunConfig` includes `verbose`.
- CLI passes `args.verbose` into orchestration config.
- `OrchestrationStateMachine` creates orchestrator with hardcoded `verbose=True`.
- Evidence:
  - `/src/engine/orchestration_api.py:23`
  - `/src/orchestrator/antigravity-cli.py:172`
  - `/src/engine/state_machine.py:275`

## Proposed Solutions

### Option 1: Thread Verbose Through State Machine (Recommended)

**Approach:** Add `verbose` field to `OrchestrationStateMachine` and pass it to `CrewAIThreeTierOrchestrator`.

**Pros:**
- Predictable behavior.
- Aligns config contract.

**Cons:**
- Requires constructor and call-site updates.

**Effort:** Small

**Risk:** Low

---

### Option 2: Remove Verbose From Public Config

**Approach:** If always-verbose is intended, remove exposed config field.

**Pros:**
- Eliminates misleading configuration.

**Cons:**
- Reduces runtime control.

**Effort:** Small

**Risk:** Low

## Recommended Action
Applied Option 1. Added `verbose` to `OrchestrationStateMachine`, passed it through from API config, and removed hardcoded `verbose=True` orchestrator construction.


## Technical Details

Affected components:
- CLI config behavior
- API config consistency

## Resources

- Files:
  - `src/engine/orchestration_api.py`
  - `src/engine/state_machine.py`
  - `src/orchestrator/antigravity-cli.py`

## Acceptance Criteria

- [x] Verbose setting behaves consistently across API and CLI calls.
- [x] Tests cover verbose true/false propagation.

## Work Log
### 2026-03-05 - Completed

**By:** Codex

**Actions:**
- Added `verbose` constructor parameter and instance state in `OrchestrationStateMachine`.
- Updated orchestrator construction to use `self.verbose`.
- Updated `run_orchestration` to pass `config.verbose` into the state machine.
- Added regression test for verbose propagation through the API run path.

**Validation:**
- `make test-pytest` (56 passed)
- `make test-e2e` (7 passed)

### 2026-03-05 - Initial Discovery

**By:** Codex

**Actions:**
- Traced verbose field from CLI to runtime orchestrator construction.
- Confirmed hardcoded override in state machine.

**Learnings:**
- Config fields should be either fully honored or removed to avoid operator confusion.
