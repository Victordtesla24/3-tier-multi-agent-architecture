---
title: "fix: README clean-room E2E operational readiness"
type: fix
status: completed
date: 2026-03-09
---

# fix: README clean-room E2E operational readiness

## Overview

Bring the repository to a deterministic state where a fresh user can follow README commands from a clean clone and complete installation, validation, tests, benchmark, and CLI workflow without manual hacks.

## Problem Statement / Motivation

Current clean-room runs mostly pass, but the final standalone CLI usage flow remains unstable and can stall or fail to emit final artifacts. This blocks end-to-end operational readiness.

## Proposed Solution

Harden prompt extraction and routing in runtime graph, stabilize worker/evaluator completion semantics for prompt-rewrite flows, and keep retry behavior bounded and deterministic. Re-run the full clean-room loop after each source patch until all README steps pass.

## Technical Considerations

- Runtime graph task classification must reliably classify rewrite-prompt style requests.
- Worker tool selection must map generic aliases and avoid model-specific tool-call dead ends.
- Evaluator acceptance criteria must reflect intended artifact output for prompt-only tasks.
- Clean-room simulation must run from a fully reset `testing_folder` clone each iteration.

## System-Wide Impact

- **Interaction graph**: CLI prompt -> runtime graph intent/task extraction -> crew orchestrator worker/evaluator loop -> execution artifact persistence.
- **Error propagation**: extraction/routing errors trigger retries and can deadlock completion.
- **State lifecycle risks**: partial runs can leave no output artifact while appearing active.
- **API surface parity**: CLI invocation and scripted invocation must share consistent behavior.
- **Integration test scenarios**: prompt rewrite request with XML/markdown wrappers; tool alias mapping; provider-tier fallback behavior.

## Acceptance Criteria

- [x] Fresh clean-room clone follows README commands exactly with no undocumented manual steps.
- [x] `uv sync --all-extras --python 3.12` succeeds from clean clone.
- [x] `./scripts/integrate_crewai.sh` succeeds.
- [x] runtime env validation command succeeds with real `.env`.
- [x] `make test-pytest` and `make benchmark` succeed.
- [x] README CLI usage command completes and writes expected artifact(s).
- [x] No infinite retry loop in worker/evaluator for rewrite-prompt objective.
- [x] New and updated tests cover extraction/routing/evaluator behavior.

## Implementation Plan

### Phase 1: Stabilize rewrite-prompt flow

- [x] Audit `runtime_graph.py` and `workflow_primitives.py` for extraction/classification gaps.
- [x] Patch extraction for wrapped `<input_data>` variants and normalize captured payload.
- [x] Patch routing logic for rewrite-prompt objective to deterministic task assignment.
- [x] Add/adjust tests in `tests/test_runtime_graph.py`.

Implementation details:
- Extraction contracts to keep green:
  - `tests/test_runtime_graph.py::test_sanitize_user_input_extracts_markdown_input_data_block`
  - `tests/test_runtime_graph.py::test_sanitize_user_input_extracts_backticked_input_data_tags`
  - `tests/test_contracts.py::test_input_data_extraction_contract`
- Routing contracts to keep green:
  - `tests/test_runtime_graph.py::test_semantic_task_planner_fast_path_prompt_rewrite_from_wrapped_prompt`
- Deterministic behavior:
  - Always strip wrapper artifacts (backticks/newlines) before intent matching.
  - Prefer explicit rewrite intent fast path before broad planner heuristics.

### Phase 2: Harden orchestration convergence

- [x] Audit `crew_orchestrator.py` worker/evaluator loop behavior for prompt-only tasks.
- [x] Patch evaluator criteria and/or completion contract to accept valid prompt artifact output.
- [x] Ensure retries are bounded and stop on successful prompt artifact.
- [x] Add/adjust tests for tool alias normalization and convergence semantics.

Implementation details:
- Existing guardrail tests:
  - `tests/test_runtime_graph.py::test_task_graph_worker_normalizes_generic_read_tools_and_reroutes_off_ollama`
  - `tests/test_runtime_graph.py::test_task_graph_worker_keeps_l3_tier_for_toolless_tasks`
- Required convergence policy:
  - If evaluator confirms requirement coverage and artifact shape is valid, stop retry loop immediately.
  - For prompt-only objectives, treat structured prompt output as terminal success, not partial progress.
  - Keep tier fallback explicit and telemetry-backed (`execution_mode=task_graph` metadata remains intact).

### Phase 3: Full clean-room validation loop

- [x] Reset `/Users/Shared/antigravity/testing_folder` and reclone from source.
- [x] Execute README install/setup/validation/test/benchmark/CLI sequence in order.
- [x] Capture logs for each command and verify expected outputs/artifacts.
- [x] If a step fails, patch only source repo, then restart from clean clone.
- [x] Mark all acceptance criteria complete once every step passes in one uninterrupted run.

Execution matrix (must pass in one run):
1. `./install.sh`
2. `uv sync --all-extras --python 3.12`
3. `./scripts/integrate_crewai.sh`
4. `PYTHONPATH=src uv run python scripts/validate_runtime_env.py --workspace . --project-root . --live --probe-configured-providers`
5. `make test-pytest`
6. `make benchmark`
7. README CLI usage command from the usage section, with expected artifact write under workspace.

Pipeline defaults:
- Non-interactive mode for all prompts and flow decisions.
- Headless mode for any browser automation.
- Recreate clean clone for every remediation cycle; never hot-fix inside testing folder.

## Dependencies & Risks

- Provider availability and API key validity can influence live validation behavior.
- Tool-call behavior may differ across model/provider combinations; fallback policy must remain explicit and test-covered.

## Sources & References

- README execution target: `README.md`
- Runtime flow modules: `src/engine/runtime_graph.py`, `src/engine/workflow_primitives.py`, `src/engine/crew_orchestrator.py`
- Existing test coverage: `tests/test_runtime_graph.py`, `tests/test_improvement_plan_workstreams.py`
