---
status: done
priority: p1
issue_id: "010"
tags: [code-review, security, configuration]
dependencies: []
---

# Runtime config tool can expose raw provider secrets

`read_runtime_configuration(include_system_env=True)` returns raw environment values for provider keys. Because this tool is available to worker agents, it can leak secrets into model context, outputs, or logs.

## Problem Statement

The tool response includes unredacted values from `_RUNTIME_KEYS` when `include_system_env=True`, including `OPENAI_API_KEY`, `GOOGLE_API_KEY`, and `GEMINI_API_KEY`.

Impact:
- Credential disclosure risk in generated outputs and telemetry.
- Increased blast radius if prompt-injected tasks request system env output.
- Violates least-privilege for worker tooling.

## Findings

- Secret values are returned directly:
  - `src/engine/orchestration_tools.py:167-172`
- Runtime key set includes provider secrets:
  - `src/engine/orchestration_tools.py:106-109`
- Tool is available to worker agent set:
  - `src/engine/crew_orchestrator.py:399-406`

## Proposed Solutions

### Option 1: Redact sensitive keys in tool output

**Approach:** Return only presence metadata for sensitive keys; never return raw values.

**Pros:**
- Fastest risk reduction.
- Keeps tool useful for diagnostics.

**Cons:**
- Loses exact-value introspection for debugging.

**Effort:** Small

**Risk:** Low

---

### Option 2: Remove `include_system_env` from worker-facing schema

**Approach:** Keep internal function support but do not expose this flag in `ReadRuntimeConfigTool` args.

**Pros:**
- Eliminates worker path to raw env.

**Cons:**
- Requires alternate secure admin path for deep debugging.

**Effort:** Small

**Risk:** Low

---

### Option 3: Scope tool by role/stage with policy gates

**Approach:** Allow detailed env only for privileged orchestration contexts; deny for L3 workers.

**Pros:**
- Better long-term governance.

**Cons:**
- More policy complexity.

**Effort:** Medium

**Risk:** Medium

## Recommended Action


## Technical Details

**Affected files:**
- `src/engine/orchestration_tools.py`
- `src/engine/crew_orchestrator.py`

**Related components:**
- Runtime configuration diagnostics
- Worker tool exposure controls

**Database changes (if any):**
- No

## Resources

- **PR:** https://github.com/Victordtesla24/3-tier-multi-agent-architecture/pull/1

## Acceptance Criteria

- [x] Raw API key values are never returned by worker-accessible tooling.
- [x] Tool output remains machine-readable and useful (presence/health metadata).
- [x] Tests verify redaction behavior for all sensitive runtime keys.

## Work Log

### 2026-03-09 - Initial Discovery

**By:** Codex (ce-review)

**Actions:**
- Audited runtime config read path and key lists.
- Verified worker tool registration and exposure.

**Learnings:**
- Diagnostic capabilities should separate secret-value access from agent-accessible tooling.

## Notes

- P1 security issue; blocks merge until mitigated.

## Resolution Notes

- Added runtime env redaction in `src/engine/orchestration_tools.py` (`_is_sensitive_env_key`, `_redact_env_entry`) and applied it to `read_runtime_configuration(include_system_env=True)`.
- Expanded regression coverage in `tests/test_capability_parity.py::test_runtime_config_system_env_is_redacted` for `OPENAI_API_KEY`, `GOOGLE_API_KEY`, and `GEMINI_API_KEY`.
