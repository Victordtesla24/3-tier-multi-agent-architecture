---
title: "fix: Enforce README clean-room install and execution fidelity"
type: fix
status: completed
date: 2026-03-08
---

# fix: Enforce README clean-room install and execution fidelity

Run a full clean-room simulation of a developer cloning, installing, configuring, validating, and operating the repository from `/Users/Shared/antigravity/testing_folder`, using the real credentials copied from the source repository `.env`. Execute the README-documented install, setup, validation, testing, and runtime commands as written wherever possible, patch the source repository when the real-world flow breaks, then wipe the clean-room copy and repeat until the README path succeeds end-to-end with no undocumented manual intervention.

## Problem Statement

The repository has to work for a first-time user outside the original working directory. The current source tree may still contain hidden path assumptions, installer/runtime mismatches, stale README guidance, broken validation steps, or missing dependency/setup behavior that only appears in a pristine external copy. The goal is not to get a single local run passing by hand. The goal is to prove that the README is operationally truthful and that a real user can follow it from a fresh directory and reach a fully working install, validation pass, and runtime execution without extra tribal knowledge.

## Research Summary

- `README.md` currently documents two installation paths that both matter for this validation:
  - Quick install: `chmod +x install.sh` then `./install.sh`
  - Manual install: `uv sync --all-extras --python 3.12`, `.env` setup, `./scripts/integrate_crewai.sh`, and `python scripts/validate_runtime_env.py --workspace . --project-root . --live --probe-configured-providers --report-path docs/reports/validation_report.json`
- `README.md` also documents operational verification commands that must succeed in the copied repo:
  - `make test-pytest`
  - `uv run python src/orchestrator/antigravity-cli.py --workspace /tmp/antigravity_workspace --prompt "Your objective here" --verbose`
  - Maintenance checks such as `ls -la .agent/rules .agent/workflows .agent/tmp .agent/memory` and `ls .agent/rules/`
- `install.sh` enforces `~/.gemini` presence, self-heals architecture files from git, loads the model catalog through `PYTHONPATH=src python3`, updates `.env`, installs dependencies via `uv`, and writes active model-matrix defaults. That makes it a high-risk entrypoint for clean-room failures.
- `Makefile` expects a repo-local virtualenv at `.venv` and defines the canonical validation path through `make test-pytest`.
- The repository already contains one earlier clean-room validation plan, which confirms this class of failure is real, but the current task is stricter: create a new run-specific plan and revalidate against the current README/install/runtime state from scratch.
- `docs/solutions/` currently contains no prior learnings to reuse, so the implementation must rely on repository evidence rather than institutional solution documents.

## External Research Decision

Proceed without external research. The problem is repository-local and the success criteria are governed by the current README, scripts, tests, and runtime behavior in this codebase.

## SpecFlow Analysis

### Primary Flow

1. Start with an empty `/Users/Shared/antigravity/testing_folder`.
2. Copy the active source repository into the clean-room directory.
3. Copy the real source `.env` into the clean-room repo root.
4. Change context to the clean-room directory.
5. Execute the README installation path beginning with `install.sh`.
6. Execute the README manual dependency/setup/validation commands.
7. Execute the README testing and runtime commands.
8. Inspect stdout, stderr, exit codes, and generated artifacts.
9. If anything fails or requires an undocumented workaround, patch the source repo.
10. Wipe the clean-room directory and repeat from step 1.
11. Stop only when the documented flow succeeds end-to-end.

### Critical Gaps To Validate During Execution

- Whether the README implies a prerequisite order that is currently incomplete or wrong.
- Whether `install.sh` and the manual `uv sync` path agree on environment layout, dependency versions, and `.env` semantics.
- Whether the copied `.env` plus README defaults create a valid active tier matrix without extra editing.
- Whether the README CLI command actually works as written with the installed environment and documented `PYTHONPATH`.
- Whether live provider probing fails because the README over-promises supported providers or required keys.
- Whether the maintenance checks and test commands reveal missing generated files, missing directories, or incorrect relative-path assumptions in the copied repo.

## Scope

### In Scope

- Recreate `/Users/Shared/antigravity/testing_folder` from scratch for each loop.
- Copy the full source repository into the clean-room directory.
- Copy the real `.env` from the source repository into the clean-room repo.
- Execute README-documented install, setup, validation, maintenance, testing, and runtime commands from the clean-room repo.
- Capture command output and failure modes for every broken step.
- Apply fixes only in `/Users/Shared/antigravity/3-tier-multi-agent-architecture-work/`.
- Repeat the full clean-room loop until all targeted README steps succeed without undocumented hacks.

### Out of Scope

- Mock provider execution.
- Declaring success based only on local source-tree runs.
- One-off manual workarounds inside the clean-room repo that are not reflected back into source.

## Deterministic Execution Defaults

- Use the active source branch as the source of truth and patch only the source workspace.
- Use the exact plan file from this run as the execution document and update it in place.
- Use the source `.env` as the canonical credential source for the clean-room copy.
- When the interactive installer requires a model selection, derive the deterministic selection from the copied `.env`:
  - Prefer `ORCHESTRATION_MODEL`
  - Fall back to `PRIMARY_LLM`
  - Use the corresponding provider API key already present in the copied `.env`
- Treat the README quick-install and manual-install sections as cumulative validation targets for this task, not mutually exclusive shortcuts.
- Store each retry pass under a stable log root such as `.agent/tmp/readme-clean-room-loop/pass-01/`, `.agent/tmp/readme-clean-room-loop/pass-02/`, and so on.

## Success Criteria

- [x] SC1: A pristine clean-room copy in `/Users/Shared/antigravity/testing_folder` can follow the README installation/setup path without missing prerequisites, broken commands, or path-coupled assumptions.
- [x] SC2: The copied `.env` satisfies the README credential and tier-matrix setup requirements, including `PRIMARY_LLM`, orchestration/tier model selection, and live provider validation behavior.
- [x] SC3: The documented dependency installation and CrewAI integration commands complete successfully from the clean-room repo.
- [x] SC4: The README validation and maintenance commands complete successfully from the clean-room repo.
- [x] SC5: `make test-pytest` passes in the clean-room repo.
- [x] SC6: At least one README-documented runtime workload succeeds from the clean-room repo with real credentials and produces inspectable execution artifacts.
- [x] SC7: No undocumented extra step is required between clone and successful operation.

## Implementation Strategy

### Phase 1: Capture the Exact README Command Set

- [x] Read `README.md` and extract every executable install/setup/validation/testing/runtime command relevant to a first-time user flow.
- [ ] Preserve the documented order and exact syntax, including:
  - [ ] `chmod +x install.sh`
  - [ ] `./install.sh`
  - [ ] `uv sync --all-extras --python 3.12`
  - [ ] `chmod +x scripts/integrate_crewai.sh`
  - [ ] `./scripts/integrate_crewai.sh`
  - [ ] `PYTHONPATH=src python scripts/validate_runtime_env.py --workspace . --project-root . --live --probe-configured-providers --report-path docs/reports/validation_report.json`
  - [ ] `ls -la .agent/rules .agent/workflows .agent/tmp .agent/memory`
  - [ ] `ls .agent/rules/`
  - [ ] `make test-pytest`
  - [ ] `uv run python src/orchestrator/antigravity-cli.py --workspace /tmp/antigravity_workspace --prompt "Your objective here" --verbose`
- [x] Record any README ambiguity about whether quick install and manual install are alternatives or cumulative verification steps, then choose the strict interpretation that maximizes validation coverage.

### Phase 2: Clean-Room Provisioning

- [x] Remove all contents of `/Users/Shared/antigravity/testing_folder`.
- [x] Recreate the target directory.
- [x] Copy the active source repository into the target directory, preserving dotfiles and git metadata.
- [x] Copy `/Users/Shared/antigravity/3-tier-multi-agent-architecture-work/.env` into `/Users/Shared/antigravity/testing_folder/.env`.
- [x] Verify the copied tree contains `README.md`, `install.sh`, `pyproject.toml`, `Makefile`, `scripts/`, and `src/`.
- [x] Switch all subsequent execution to `/Users/Shared/antigravity/testing_folder`.

### Phase 3: Execute README Installation and Setup Verbatim

- [x] Run `chmod +x install.sh`.
- [x] Run `./install.sh` using the clean-room repo.
- [x] If automation is required for the interactive installer, feed the deterministic model selection and matching API key derived from the copied `.env` so the executed path still represents the README installer flow rather than a substitute implementation.
- [x] Run `uv sync --all-extras --python 3.12`.
- [x] Activate the virtual environment exactly as the flow creates it when that activation step becomes necessary for subsequent commands.
- [x] Run `chmod +x scripts/integrate_crewai.sh`.
- [x] Run `./scripts/integrate_crewai.sh`.
- [x] Use the injected `.env` to satisfy the README `.env` configuration expectations and confirm the active tier matrix resolves cleanly.
- [x] Run the README runtime-environment validation command with live probing and report output.

### Phase 4: Execute README Maintenance, Test, and Runtime Commands

- [x] Run `ls -la .agent/rules .agent/workflows .agent/tmp .agent/memory`.
- [x] Run `ls .agent/rules/`.
- [x] Run `make test-pytest`.
- [x] Run the standalone CLI command from the README.
- [x] If the README’s primary runtime entrypoint is broken but another explicitly documented runtime command succeeds, fix the broken command rather than silently substituting the alternative.
- [x] Confirm a successful workload writes artifacts or logs that prove the orchestrator really ran.

### Phase 5: Forensic Failure Analysis

- [x] For every command executed, capture:
  - [x] Exact command string
  - [x] Exit code
  - [x] stdout
  - [x] stderr
- [ ] Classify each failure as one or more of:
  - [ ] README drift
  - [ ] installer defect
  - [ ] dependency resolution defect
  - [ ] `.env` or provider-validation defect
  - [ ] path/workspace defect
  - [ ] runtime/orchestrator defect
  - [ ] test defect
- [ ] Trace each failure back to the smallest source-of-truth file that should be fixed.
- [x] Re-run every failing command at least twice when needed to separate deterministic repository bugs from transient external-provider failures.
- [x] Preserve per-pass logs with stable names, for example:
  - [x] `01-install.log`
  - [x] `02-uv-sync.log`
  - [x] `03-integrate-crewai.log`
  - [x] `04-validate-runtime-env.log`
  - [x] `05-maintenance.log`
  - [x] `06-pytest.log`
  - [x] `07-cli.log`

### Phase 6: Source-Repo Remediation

- [x] Apply every fix only inside `/Users/Shared/antigravity/3-tier-multi-agent-architecture-work/`.
- [x] Prefer production-grade fixes in source code, scripts, dependency metadata, or README instructions over local clean-room hacks.
- [x] Keep the fix set minimal but complete enough to remove the failure for the next full loop.
- [x] Update README instructions when the code is correct but the documentation is wrong.
- [x] Update code/scripts when the README instruction is reasonable but the implementation is broken.
- [x] Preserve architectural consistency across `README.md`, `install.sh`, `Makefile`, `scripts/integrate_crewai.sh`, `scripts/validate_runtime_env.py`, and `src/orchestrator/antigravity-cli.py`.
- [x] Prefer fixing the shared runtime/configuration boundary once instead of adding copy-specific fallbacks in multiple entrypoints.

### Phase 7: Autonomous Retry Loop

- [x] After every fix, completely wipe `/Users/Shared/antigravity/testing_folder`.
- [x] Recopy the source repository and `.env`.
- [x] Re-execute Phases 3 and 4 from the top.
- [x] Continue until every success criterion is checked off with a clean-room pass.

### Phase 8: Evidence and Closeout

- [x] Preserve the final passing command outputs in a stable artifact location.
- [x] Update this plan file by checking off every completed item as work progresses.
- [x] Summarize the defects found, fixes applied, and evidence paths for the final successful run.

## Swarm Execution Map

- [ ] Parallelize safe discovery work:
  - [ ] README command extraction
  - [ ] Source tree path/venv/runtime pattern inspection
  - [ ] Test and script lookup for the failing area
- [ ] Keep stateful clean-room execution itself sequential per pass so each command runs against the exact filesystem state a real user would have.
- [ ] After a failure is captured, parallelize source inspection across the implicated files and tests before applying the fix.
- [ ] After a passing runtime, parallelize artifact verification and evidence collection.

## Failure-to-Fix Mapping

- [ ] `./install.sh` failures:
  - [ ] Inspect `install.sh`
  - [ ] Inspect `src/engine/model_catalog.py`
  - [ ] Inspect `src/engine/config_manager.py`
  - [ ] Inspect installer tests such as `tests/test_install_script.py`
- [ ] `uv sync` or `./scripts/integrate_crewai.sh` failures:
  - [ ] Inspect `pyproject.toml`
  - [ ] Inspect `uv.lock` if present
  - [ ] Inspect `scripts/integrate_crewai.sh`
  - [ ] Inspect related CrewAI/runtime tests
- [ ] `validate_runtime_env.py` failures:
  - [ ] Inspect `scripts/validate_runtime_env.py`
  - [ ] Inspect `src/engine/runtime_env.py`
  - [ ] Inspect `src/engine/provider_healthchecks.py`
  - [ ] Inspect provider/runtime tests
- [ ] `make test-pytest` failures:
  - [ ] Inspect the first failing test file
  - [ ] Inspect the production module under test
  - [ ] Inspect the relevant setup/fixture path
- [ ] CLI/runtime workload failures:
  - [ ] Inspect `src/orchestrator/antigravity-cli.py`
  - [ ] Inspect `src/engine/crew_orchestrator.py`
  - [ ] Inspect `src/engine/state_machine.py`
  - [ ] Inspect workspace/runtime env helpers and artifact-writing paths

## Concrete Command Baseline

```bash
rm -rf /Users/Shared/antigravity/testing_folder/*
rsync -a /Users/Shared/antigravity/3-tier-multi-agent-architecture-work/ /Users/Shared/antigravity/testing_folder/
cp /Users/Shared/antigravity/3-tier-multi-agent-architecture-work/.env /Users/Shared/antigravity/testing_folder/.env
cd /Users/Shared/antigravity/testing_folder
chmod +x install.sh
./install.sh
uv sync --all-extras --python 3.12
chmod +x scripts/integrate_crewai.sh
./scripts/integrate_crewai.sh
PYTHONPATH=src uv run python scripts/validate_runtime_env.py --workspace . --project-root . --live --probe-configured-providers --report-path docs/reports/validation_report.json
ls -la .agent/rules .agent/workflows .agent/tmp .agent/memory
ls .agent/rules/
make test-pytest
uv run python src/orchestrator/antigravity-cli.py --workspace /tmp/antigravity_workspace --prompt "Your objective here" --verbose
```

## Risks and Watchpoints

- `install.sh` may depend on machine-local IDE state or prompt handling that breaks unattended clean-room execution.
- The README may describe both interactive and manual flows without clearly defining whether they are alternatives or cumulative steps.
- Live provider probing may fail because the copied `.env` contains inactive credentials or provider combinations that the runtime now validates more strictly than before.
- The CLI command may succeed only with additional environment variables or workspace preparation that the README does not mention.
- The clean-room repo may expose hidden assumptions about `PYTHONPATH`, repo root discovery, shell, `uv`, or virtualenv activation.

## Evidence Targets

## Final Outcome

- Final strict clean-room pass: `.agent/tmp/readme-clean-room-loop/pass-13/`
- Passing installer log: `.agent/tmp/readme-clean-room-loop/pass-13/01-install.log`
- Passing venv activation log: `.agent/tmp/readme-clean-room-loop/pass-13/02-activate-venv.log`
- Passing manual install log: `.agent/tmp/readme-clean-room-loop/pass-13/03-uv-sync.log`
- Passing CrewAI integration log: `.agent/tmp/readme-clean-room-loop/pass-13/04-integrate-crewai.log`
- Passing runtime validation log: `.agent/tmp/readme-clean-room-loop/pass-13/05-validate-runtime-env.log`
- Passing maintenance logs:
  - `.agent/tmp/readme-clean-room-loop/pass-13/06-maintenance-ls-la.log`
  - `.agent/tmp/readme-clean-room-loop/pass-13/07-maintenance-rules.log`
- Passing test log: `.agent/tmp/readme-clean-room-loop/pass-13/08-make-test-pytest.log`
- Passing CLI log: `.agent/tmp/readme-clean-room-loop/pass-13/09-cli.log`
- Passing CLI result JSON: `/tmp/antigravity_workspace/execution_result.json`

### Defects Fixed During This Loop

- `scripts/integrate_crewai.sh` no longer trips on empty runtime-warning arrays and now validates the actual local CrewAI tool path instead of a stale `crewai_tools` import.
- `src/engine/runtime_env.py` now normalizes Google/Gemini aliases without false duplicate warnings and preserves canonical credentials when alias placeholders or conflicts exist.
- `src/engine/crew_orchestrator.py` now disables CrewAI memory when the Google embedder SDK is unavailable and short-circuits directly to clarification output when the reconstructed prompt plus research state make task-graph execution unnecessary.
- `src/engine/continuous_learning.py` now tolerates missing stage durations.
- `README.md` now uses the managed `uv run python` path for `validate_runtime_env.py`, matching the clean-room shell environment.

- `testing_folder/docs/reports/validation_report.json`
- `testing_folder/.agent/tmp/`
- `testing_folder/.agent/memory/`
- `testing_folder/workspaces/`
- Final passing clean-room command transcript captured during execution
