---
status: complete
priority: p1
issue_id: "008"
tags: [python, readme, installation, clean-room, validation, crewai]
dependencies: []
---

# README clean-room validation loop

Execute the clean-room README simulation from `docs/plans/2026-03-08-fix-readme-clean-room-execution-fidelity-plan.md`, patch the source repository for each defect found, and keep looping until the documented install, validation, testing, and runtime flow succeeds from `/Users/Shared/antigravity/testing_folder`.

## Problem Statement

The repository must prove that a first-time user can follow the README from a pristine external directory and reach a working installation and runtime. Any failure in the installer, dependency setup, environment validation, tests, or CLI execution is a release-blocking documentation or architecture defect.

## Findings

- The README documents both `install.sh` and the manual `uv` / CrewAI / runtime-validation path, so this validation needs to cover both.
- `install.sh`, `Makefile`, `scripts/integrate_crewai.sh`, `scripts/validate_runtime_env.py`, and `src/orchestrator/antigravity-cli.py` are the primary source-of-truth files for the documented flow.
- The installer is interactive, so automated execution must derive a deterministic selection from the copied `.env` without replacing the installer flow.
- The clean-room loop must preserve exact per-command logs so each failure can be traced back to the right source file.

## Proposed Solutions

### Option 1: Full clean-room loop with source patching

**Approach:** Recreate `/Users/Shared/antigravity/testing_folder`, execute the README command set in order, patch source on failure, and repeat until success.

**Pros:**
- Validates the real user path end-to-end
- Surfaces documentation drift and runtime defects together
- Produces evidence for every fix

**Cons:**
- Potentially time-consuming if multiple defects exist
- Live provider probing adds external variability

**Effort:** High

**Risk:** Medium

---

### Option 2: Static review only

**Approach:** Inspect README and scripts without running the full clean-room flow.

**Pros:**
- Faster
- Lower runtime cost

**Cons:**
- Does not satisfy the task
- Misses real installation/runtime breakages

**Effort:** Low

**Risk:** High

## Recommended Action

Execute Option 1. Use the plan file from this run as the controlling document, log every pass under `.agent/tmp/readme-clean-room-loop/pass-XX/`, apply source-only fixes, and update the plan/todo as work progresses until the README flow passes in the clean-room repo.

## Technical Details

**Affected files:**
- `README.md`
- `install.sh`
- `Makefile`
- `scripts/integrate_crewai.sh`
- `scripts/validate_runtime_env.py`
- `src/orchestrator/antigravity-cli.py`
- Additional runtime/test files implicated by failures discovered during execution

**Related components:**
- Runtime env resolution
- Provider probing
- CrewAI dependency/bootstrap path
- CLI workspace handling

**Database changes (if any):**
- No

## Resources

- **Plan:** `docs/plans/2026-03-08-fix-readme-clean-room-execution-fidelity-plan.md`
- **Target clean-room repo:** `/Users/Shared/antigravity/testing_folder`
- **Source repo:** `/Users/Shared/antigravity/3-tier-multi-agent-architecture-work`

## Acceptance Criteria

- [x] The clean-room README flow passes end-to-end from `/Users/Shared/antigravity/testing_folder`
- [x] All source fixes are applied only in the source repository
- [x] The plan file is updated with completed checkboxes
- [x] Final evidence paths and passing logs are preserved

## Work Log

### 2026-03-08 - Todo creation

**By:** Codex

**Actions:**
- Created the run-specific execution todo
- Linked the exact plan file produced in this SLFG run
- Set the work as `ready` with no dependencies

**Learnings:**
- The task is a true clean-room validation loop, not a documentation edit in isolation
- The installer interaction path needs deterministic automation tied to the copied `.env`

### 2026-03-08 - Final passing clean-room pass

**By:** Codex

**Actions:**
- Ran repeated clean-room retries until the strict README flow passed from a fresh copied repo with no inherited virtualenv.
- Validated `install.sh`, repo-local venv activation, manual `uv sync`, `scripts/integrate_crewai.sh`, live `validate_runtime_env.py`, maintenance `ls` checks, `make test-pytest`, and the standalone CLI command.
- Patched the source repo to remove installer false alarms, runtime alias warnings, brittle CrewAI memory behavior, missing-duration continuous-learning crashes, README command drift, and the placeholder-prompt task-graph retry loop.
- Preserved the final evidence under `.agent/tmp/readme-clean-room-loop/pass-13/`.

**Learnings:**
- Copying the source `.venv` invalidates the clone simulation because activation scripts retain absolute source paths; the clean-room copy must remove inherited virtualenvs before executing README commands.
- Placeholder or clarifying prompts should bypass task-graph execution entirely once the research phase explicitly confirms missing required configuration.

## Notes

- Use headless defaults where browser-related workflow stages appear later in the SLFG pipeline.
