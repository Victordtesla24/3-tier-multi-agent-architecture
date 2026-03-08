---
status: complete
priority: p1
issue_id: "011"
tags: [code-review, reliability, performance, architecture]
dependencies: []
---

# SubmitObjective tool enables unbounded nested orchestration

`submit_objective` is exposed to worker agents without explicit recursion guard, quota, or stage policy. A worker can trigger orchestration recursively and amplify runtime cost/failure cascades.

## Problem Statement

The tool directly calls `run_orchestration` and is available in worker tooling. There is no guardrail preventing nested self-invocation loops or objective fan-out from generated tasks.

Impact:
- Runaway resource consumption.
- Hard-to-debug recursive execution trees.
- Potential provider budget exhaustion and unstable execution behavior.

## Findings

- Recursive-capable implementation:
  - `src/engine/orchestration_tools.py:268-302`
- Tool exposed to worker runtime:
  - `src/engine/crew_orchestrator.py:404-406`
- Tool discoverable in worker manifest:
  - `src/engine/crew_orchestrator.py:279-281`

## Proposed Solutions

### Option 1: Hard block nested submissions from worker context

**Approach:** Add context/run-depth guard (`ANTIGRAVITY_RUN_DEPTH`), reject tool use when depth > 0.

**Pros:**
- Deterministic prevention of recursive loops.

**Cons:**
- Removes some advanced orchestration chaining use-cases.

**Effort:** Small

**Risk:** Low

---

### Option 2: Allow bounded nesting with strict quota

**Approach:** Permit one nested run max and enforce token/time/provider budgets per parent run.

**Pros:**
- Preserves limited chaining flexibility.

**Cons:**
- More moving parts and policy complexity.

**Effort:** Medium

**Risk:** Medium

---

### Option 3: Remove from worker toolset, keep orchestration-only endpoint

**Approach:** Keep API primitive but only expose to trusted orchestration tier or external API callers.

**Pros:**
- Strong least-privilege boundary.

**Cons:**
- Workers cannot spawn follow-on objectives directly.

**Effort:** Small

**Risk:** Low

## Recommended Action


## Technical Details

**Affected files:**
- `src/engine/orchestration_tools.py`
- `src/engine/crew_orchestrator.py`

**Related components:**
- Task graph execution and tool policy
- Provider budget controls

**Database changes (if any):**
- No

## Resources

- **PR:** https://github.com/Victordtesla24/3-tier-multi-agent-architecture/pull/1

## Acceptance Criteria

- [x] Worker context cannot trigger unbounded nested orchestration.
- [x] Explicit guard (depth/quota/policy) is implemented and tested.
- [x] Telemetry captures blocked nested submission attempts.

## Work Log

### 2026-03-09 - Initial Discovery

**By:** Codex (ce-review)

**Actions:**
- Reviewed new objective-submission primitive and worker tool registration.
- Traced call path into orchestration API.

**Learnings:**
- Action parity tooling still needs strict runtime governance to avoid self-amplifying loops.

### 2026-03-09 - Resolved in SLFG execution

**By:** Codex (`slfg` finalize)

**Actions:**
- Enforced strict nested submission policy in `src/engine/orchestration_tools.py` by reducing `MAX_SUBMIT_OBJECTIVE_DEPTH` to `1` (depth `>=1` now blocked).
- Added explicit blocked-attempt telemetry: `SUBMIT_OBJECTIVE_BLOCKED_NESTED`.
- Added regression coverage in `tests/test_capability_parity.py::test_submit_objective_logs_blocked_nested_attempt`.
- Re-ran targeted verification suite:
  - `PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_capability_parity.py tests/test_orchestration_hardening.py -q`

**Learnings:**
- Deterministic recursion caps plus explicit logging provide both blast-radius control and incident forensics.

## Notes

- P1 reliability/performance risk.
