---
status: done
priority: p2
issue_id: "012"
tags: [code-review, quality, observability, data-integrity]
dependencies: []
---

# Corrupt A2UI state file is silently reset to empty payload

When `.agent/memory/a2ui_state.json` is malformed, `acknowledge_ui_action` catches all parse errors and resets payload to `{}` without warning.

## Problem Statement

Silent reset destroys previous state and eliminates forensic context needed to diagnose corruption.

Impact:
- Potential loss of unrelated future A2UI state fields.
- No traceability for state corruption incidents.
- Harder operational debugging.

## Findings

- Broad exception swallow and payload reset:
  - `src/engine/orchestration_tools.py:232-236`
- No telemetry/log output on state recovery path.

## Proposed Solutions

### Option 1: Fail closed with explicit error

**Approach:** Raise structured error when state file is invalid JSON.

**Pros:**
- Prevents silent data loss.
- Forces explicit remediation.

**Cons:**
- Can block acknowledgement path during corruption.

**Effort:** Small

**Risk:** Low

---

### Option 2: Recover with backup + warning telemetry

**Approach:** Move corrupt file to `.bak`, initialize fresh state, emit warning event/log.

**Pros:**
- Maintains availability while preserving evidence.

**Cons:**
- Slightly more implementation complexity.

**Effort:** Small

**Risk:** Low

---

### Option 3: Validate schema with versioned state envelope

**Approach:** Store `{version, data_model, metadata}` and validate before writes.

**Pros:**
- Better long-term resilience.

**Cons:**
- Requires migration path for existing files.

**Effort:** Medium

**Risk:** Medium

## Recommended Action


## Technical Details

**Affected files:**
- `src/engine/orchestration_tools.py`

**Related components:**
- A2UI state persistence
- Runtime observability

**Database changes (if any):**
- No

## Resources

- **PR:** https://github.com/Victordtesla24/3-tier-multi-agent-architecture/pull/1

## Acceptance Criteria

- [x] Corrupt state handling preserves evidence and emits explicit diagnostics.
- [x] No silent state wipe occurs without log/telemetry.
- [x] Regression test covers malformed JSON state behavior.

## Work Log

### 2026-03-09 - Initial Discovery

**By:** Codex (ce-review)

**Actions:**
- Audited state-file parse and recovery path.
- Identified silent reset semantics and missing diagnostics.

**Learnings:**
- State recovery paths need explicit observability to avoid hidden data loss.

## Notes

- P2 quality/reliability issue.

## Resolution Notes

- Implemented corruption-recovery path in `src/engine/orchestration_tools.py` using `_recover_state_payload_from_corruption()` and salvage helper `_extract_object_for_key()`.
- Added explicit telemetry log marker `A2UI_STATE_CORRUPT_RECOVERED` with path/error/snippet context.
- Added regression coverage in `tests/test_capability_parity.py::test_acknowledge_tool_logs_and_recovers_corrupt_state`.
