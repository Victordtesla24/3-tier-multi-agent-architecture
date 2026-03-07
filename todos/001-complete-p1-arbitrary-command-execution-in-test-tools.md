---
status: complete
priority: p1
issue_id: "001"
tags: [code-review, security, command-execution, agent-tools]
dependencies: []
---

# Restrict Arbitrary Command Execution in Test Tools

## Problem Statement

Agent-exposed operational tools intended for tests and benchmarks currently accept arbitrary command strings and execute them via subprocess. This enables unintended command execution beyond the tool's stated scope.

## Findings

- `RunTestsTool` accepts a free-form `command` argument and executes it after `shlex.split`.
- `RunBenchmarksTool` follows the same pattern.
- These tools are included in the default worker tool list, so the execution agent can invoke them.
- Evidence:
  - `/src/engine/orchestration_tools.py:195` (`_CommandArgs.command`)
  - `/src/engine/orchestration_tools.py:232` (`RunTestsTool._run`)
  - `/src/engine/orchestration_tools.py:251` (`RunBenchmarksTool._run`)
  - `/src/engine/crew_orchestrator.py:160` (tool registration)

## Proposed Solutions

### Option 1: Remove Command Override (Recommended)

**Approach:** Delete `command` from tool args and force fixed internal commands.

**Pros:**
- Eliminates command-injection class risk for these tools.
- Aligns behavior with tool descriptions.

**Cons:**
- Reduces debugging flexibility for custom commands.

**Effort:** Small

**Risk:** Low

---

### Option 2: Strict Allowlist Validation

**Approach:** Keep `command` but validate against a strict allowlist (e.g., exact `make test-pytest`, `pytest tests`, benchmark script only).

**Pros:**
- Preserves limited flexibility.
- Prevents arbitrary command execution.

**Cons:**
- More logic to maintain.
- Risk of bypass if parser/normalization is weak.

**Effort:** Medium

**Risk:** Medium

## Recommended Action
Applied Option 1. Removed public `command` overrides from `RunTestsTool` and `RunBenchmarksTool` so agent-exposed execution is fixed to internal defaults, with regression coverage in `tests/test_orchestration_hardening.py`.


## Technical Details

Affected components:
- Tool argument schemas
- Worker tool execution boundary
- Agent safety model for operational tools

## Resources

- PR/branch scope: `feat/agent-native-improvement-plan`
- Files:
  - `src/engine/orchestration_tools.py`
  - `src/engine/crew_orchestrator.py`

## Acceptance Criteria

- [x] `run_tests` cannot execute arbitrary external binaries.
- [x] `run_benchmarks` cannot execute arbitrary external binaries.
- [x] Tool docs match enforced behavior.
- [x] Regression tests cover blocked commands.

## Work Log
### 2026-03-05 - Completed

**By:** Codex

**Actions:**
- Removed `command` from agent tool arg schemas and `_run` signatures.
- Kept internal `run_tests`/`run_benchmarks` helpers flexible for non-agent test harnesses.
- Added hardening tests to assert schema restrictions and `command` kwarg rejection.

**Validation:**
- `make test-pytest` (56 passed)
- `make test-e2e` (7 passed)

### 2026-03-05 - Initial Discovery

**By:** Codex

**Actions:**
- Reviewed tool input schemas and subprocess execution path.
- Cross-checked worker tool exposure in orchestrator.
- Assessed blast radius as agent-level command execution capability.

**Learnings:**
- Operational tools must be capability-bounded, not generic shell gateways.
