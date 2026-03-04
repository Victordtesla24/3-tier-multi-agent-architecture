# Improvement Plan Execution Backlog (Swarm Mode)

## Objective
Execute the architecture upgrades as a deterministic, trackable work program with explicit task ownership, acceptance checks, and completion state.

## Swarm Workstreams
- **W1 — Entrypoints & API Surface:** unify CLI/chat/agent invocation paths.
- **W2 — Tooling & Safety:** add safe file tools and operational tools with strict interfaces.
- **W3 — Orchestration Context:** inject environment, memory, and runtime preferences into agent kickoff.
- **W4 — Verification Hardening:** decompose monolithic verification into reusable primitives.
- **W5 — Memory & Continuous Learning:** post-run proposal generation + gated apply flow.
- **W6 — Workspace/Docs/Benchmark UX:** normalize workspace visibility and evidence artifacts.

## Task List

### W1 — Entrypoints & API Surface
- [x] Add a first-class orchestration entrypoint equivalent to CLI flags (`prompt`, `workspace`, `strict_provider_validation`, `max_provider_4xx`, `fail_on_research_empty`, `verbose`).
  - Implemented in `src/engine/orchestration_api.py` with `OrchestrationRunConfig` + `run_orchestration`.
- [x] Align chat/agent invocation with explicit `submit_prompt` and `run_objective` functions.
  - Implemented in `src/engine/orchestration_api.py`.
- [x] Factor workflow into fully explicit primitives (`load_prompt_template`, `sanitize_user_input`, `llm_call`, `normalize_research_markdown`, `write_workspace_file`) and use them as composable capability tools.
- [x] Thin orchestration methods (`reconstruct_prompt`, `run_research`, `execute`, `execute_pipeline`) so sequencing/policy lives in agent prompts, not method internals.

### W2 — Tooling & Safety
- [x] Add safe project-root file tools with strict whitelist for `.agent/rules/*`, `.agent/workflows/*`, and `docs/architecture/*`.
  - Implemented in `src/engine/project_root_tools.py`.
- [x] Add operational health tools with machine-readable output for tests and benchmarks.
  - Implemented in `src/engine/orchestration_tools.py`: `run_tests`, `run_benchmarks`, and BaseTool wrappers.
- [x] Add runtime config observability/modification tools.
  - Implemented in `src/engine/orchestration_tools.py`: `read_runtime_configuration`, `update_runtime_configuration`.
- [x] Standardize all tool interfaces to capability-only contracts and move model/fallback/retry policy fully into agent/system prompts.

### W3 — Orchestration Context
- [x] Add explicit context builder in state-machine pipeline before hierarchical execution.
  - Implemented in `src/engine/context_builder.py` and wired from `src/engine/state_machine.py`.
- [x] Inject `Constraints & Preferences` (`strict_provider_validation`, `max_provider_4xx`, `fail_on_research_empty`) into orchestration context.
- [x] Inject memory/activity context from `.agent/memory/execution_log.json` and optional `l1-memory.md`/`l2-memory.md` into manager kickoff context.
- [x] Inject explicit tooling manifest into worker agent backstory.
  - Wired in `src/engine/crew_orchestrator.py`.
- [x] Inject explicit environment snapshot (branch, dirty state, primary languages, entry scripts).

### W4 — Verification Hardening
- [x] Decouple verification into reusable primitives:
  - `contains_banned_markers(text)`
  - `extract_python_blocks(output)`
  - `has_empty_implementations(code)`
  - Implemented in `src/engine/verification_primitives.py` and consumed by `src/engine/state_machine.py`.
- [x] Add a dedicated verification agent flow that decides when/how to apply each primitive.

### W5 — Memory & Continuous Learning
- [x] Implement continuous-learning toolchain:
  - proposal generation (`WHAT/WHY/HOW`) as structured output,
  - proposal presentation via host surface,
  - gated `apply_architecture_upgrade` using explicit approval token/phrase.
- [x] Add explicit post-verification continuous-learning stage that writes Improvement Notes and feeds them into subsequent runs.

### W6 — Workspace/Docs/Benchmark UX
- [x] Unify CrewAI storage under `<workspace>/.agent/memory/crewai_storage`.
  - Implemented via `src/engine/crewai_storage.py` and wired in CLI.
- [x] Surface benchmark/telemetry paths in CLI UX output.
  - Implemented in `src/orchestrator/antigravity-cli.py`.
- [x] Standardize primary workspace pattern (`<project>/workspaces/...` with env override support).
  - Implemented in CLI defaults.
- [ ] Treat `docs/reports/*` and `docs/benchmarks/*` as first-class planning context in agent toolchain.
- [ ] Document `.agent/tmp` and `.agent/memory` as inspectable shared workspace artifacts in architecture/user docs.

## Validation Tasks
- [x] Add tests for new workstream primitives and tooling contracts.
  - Implemented: `tests/test_improvement_plan_workstreams.py`.
- [x] Run full repository test suite and triage failures.
- [x] Run benchmark harness and attach machine-readable output to reports.

## Current Execution Notes
- This pass executed W2/W3/W4 core implementation slices and added contract tests.
- Remaining backlog is intentionally left as unchecked execution work for subsequent swarm passes.
