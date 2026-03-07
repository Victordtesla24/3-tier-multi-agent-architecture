---
status: complete
priority: p1
issue_id: "002"
tags: [code-review, security, configuration, workspace-boundary]
dependencies: []
---

# Enforce Active Workspace Boundary for Runtime Config Tools

## Problem Statement

Runtime configuration tools accept caller-provided workspace paths and perform `.env` reads/writes against that path without binding to the orchestrator's active workspace. This allows out-of-scope configuration mutation.

## Findings

- `_ReadConfigArgs` and `_UpdateConfigArgs` include free-form `workspace` inputs.
- `ReadRuntimeConfigTool._run` and `UpdateRuntimeConfigTool._run` pass user-supplied workspace directly.
- `update_runtime_configuration` writes to `<workspace>/.env` after only key allowlisting.
- Evidence:
  - `/src/engine/orchestration_tools.py:203`
  - `/src/engine/orchestration_tools.py:207`
  - `/src/engine/orchestration_tools.py:286`
  - `/src/engine/orchestration_tools.py:302`

## Proposed Solutions

### Option 1: Remove Workspace Input from Tool Args (Recommended)

**Approach:** Inject workspace at tool construction time and remove `workspace` arg from public tool API.

**Pros:**
- Hard guarantees on workspace scoping.
- Simplifies tool contract.

**Cons:**
- Requires refactor of existing callers/tests.

**Effort:** Medium

**Risk:** Low

---

### Option 2: Validate Workspace Against Active Root

**Approach:** Keep workspace arg but reject values that are not equal to active workspace or outside allowed root.

**Pros:**
- Smaller refactor.
- Keeps explicit input for diagnostics.

**Cons:**
- More complex validation paths.
- Higher chance of validation bugs than Option 1.

**Effort:** Medium

**Risk:** Medium

## Recommended Action
Applied Option 1. Removed user-provided workspace arguments from runtime config tools and bound both tools to the orchestrator's active workspace at construction time.


## Technical Details

Affected components:
- Runtime config tools
- Workspace trust boundary
- Environment mutation paths

## Resources

- Files:
  - `src/engine/orchestration_tools.py`

## Acceptance Criteria

- [x] Config tools cannot read or write `.env` outside active workspace.
- [x] Unit tests assert rejection for external paths.
- [x] Tool descriptions explicitly state enforced workspace scope.

## Work Log
### 2026-03-05 - Completed

**By:** Codex

**Actions:**
- Removed `workspace` from `_ReadConfigArgs`/`_UpdateConfigArgs`.
- Added `workspace` as a fixed tool instance field for `ReadRuntimeConfigTool` and `UpdateRuntimeConfigTool`.
- Updated orchestrator tool registration to inject active workspace path.
- Added regression tests validating bound workspace behavior and rejection of workspace overrides.

**Validation:**
- `make test-pytest` (56 passed)
- `make test-e2e` (7 passed)

### 2026-03-05 - Initial Discovery

**By:** Codex

**Actions:**
- Traced tool schema inputs to file writes.
- Verified absence of active-workspace enforcement.
- Classified as P1 due to boundary escape and config mutation risk.

**Learnings:**
- Workspace-scoped tools should avoid user-controlled absolute path selectors.
