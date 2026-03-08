---
title: "fix: Validate clean install onboarding in out-of-tree workspace"
type: fix
status: completed
date: 2026-03-08
---

# fix: Validate clean install onboarding in out-of-tree workspace

Run a full first-time-user simulation from a pristine external directory at `/Users/Shared/antigravity/testing_folder`, using the latest local source tree and the real `.env` credentials from the source repository. The goal is to prove that the recent Tier 1 async orchestration, MCP utility execution, and model catalog changes work in a production-like install outside the native development directory.

## Problem Statement

The repository has recent runtime, installation, and model-selection changes, but they still need an end-to-end validation in a clean directory that behaves like a real new-user install. The validation must not rely on the original repo path, must consume authentic provider credentials from the copied `.env`, and must keep looping on source fixes until install, tests, and a real CLI workload all pass in `/Users/Shared/antigravity/testing_folder`.

## Research Summary

- `README.md` documents `install.sh` as the guided installation entrypoint and still documents `uv sync --all-extras --python 3.12` as the canonical dependency install command.
- `install.sh` supports non-interactive execution via `ANTIGRAVITY_NONINTERACTIVE=1` and `ANTIGRAVITY_MODEL_ID`, which allows autonomous first-run validation while still using the official installer path.
- `src/orchestrator/antigravity-cli.py` resolves workspaces independently from the project root and writes execution artefacts under the chosen workspace, which is required for out-of-tree execution.
- `src/engine/runtime_env.py` and related tests indicate workspace-local `.env` loading is intended to override or supplement project-root configuration, which is critical for the copied test directory.
- Existing tests cover install-script behavior, runtime env loading, CLI runtime behavior, and async runtime graph execution, but they do not replace a real clean-room install using the copied repo and real credentials.

## Scope

### In Scope

- Wipe and recreate `/Users/Shared/antigravity/testing_folder` as a pristine install target.
- Copy the full source repository into the target directory.
- Copy the real source `.env` into the target repo root.
- Run the official first-time-user installation path from the target directory.
- Activate the created virtual environment for all subsequent commands.
- Run the core test suite from the target directory.
- Execute a real CLI workload from the target directory with authentic credentials.
- Capture stdout, stderr, execution artefacts, and failure modes.
- Patch the source repository when failures are discovered.
- Repeat the full clean-room simulation until all success criteria pass.

### Out of Scope

- Mocked provider execution.
- Partial success claims.
- Fixes that only make the source-tree path work while leaving the copied repo broken.

## Success Criteria

- [x] SC1: The project installs successfully in `/Users/Shared/antigravity/testing_folder` with no missing dependencies, path-coupled imports, or hardcoded assumptions about the original repo location.
- [x] SC2: The copied workspace-local `.env` is consumed correctly and authentic provider credentials are loaded without interactive credential prompts.
- [x] SC3: A real CLI workload executes end-to-end, including async orchestration, Tier 3 utility flow, and A2UI/final-output artefact generation, without syntax errors, deadlocks, sandbox failures, or provider bootstrap regressions.
- [x] SC4: `make test-pytest` passes in the copied directory after installation.
- [x] SC5: Evidence files and command logs are available to show the clean-room run actually completed from the copied directory.

## Execution Plan

### Phase 1: Pristine Environment Preparation

- [x] Inspect `/Users/Shared/antigravity/testing_folder`.
- [x] Remove existing contents completely to guarantee a clean starting state.
- [x] Copy the full repository from `/Users/Shared/antigravity/3-tier-multi-agent-architecture-work` into `/Users/Shared/antigravity/testing_folder`.
- [x] Copy `/Users/Shared/antigravity/3-tier-multi-agent-architecture-work/.env` to `/Users/Shared/antigravity/testing_folder/.env`.
- [x] Verify the copied directory contains the expected install entrypoints and source tree.

### Phase 2: First-Time User Installation Simulation

- [x] Change working directory to `/Users/Shared/antigravity/testing_folder`.
- [x] Use the official installer path first: run `install.sh` in non-interactive mode if needed to avoid manual prompts while preserving the first-time-user flow.
- [x] Ensure dependency installation completes and a repo-local `.venv` is available in the copied repo.
- [x] Activate `.venv` from the copied repo for subsequent commands.
- [x] Record installer stdout/stderr and any created config or env mutations.
- [x] Run `python scripts/validate_runtime_env.py --workspace . --project-root .` from the copied repo before the full test run.

### Phase 3: Real Execution Validation

- [x] Run `make test-pytest` from the copied repo.
- [x] Run a real CLI workload from the copied repo with a dedicated workspace under the copied tree or an explicit external workspace.
- [x] Use a workload that exercises multi-step orchestration and produces inspectable artefacts.
- [x] Confirm execution writes `execution_result.json`, reconstructed prompt, research context, final output, and telemetry.
- [x] Confirm runtime logs indicate model selection, provider authentication, and non-blocking orchestration behavior rather than immediate local-path failures.

### Phase 4: Autonomous Failure Loop

- [x] If any install, import, test, or runtime failure occurs, diagnose the root cause from the copied repo output.
- [x] Apply the minimal production-grade fix to the source repository only.
- [x] Prefer fixes that preserve first-time-user expectations across `install.sh`, `scripts/integrate_crewai.sh`, and `Makefile` so they agree on the active virtualenv and copied-workspace behavior.
- [x] Recreate the clean target directory from scratch.
- [x] Recopy source and `.env`.
- [x] Rerun installation, tests, and CLI execution from the beginning.
- [x] Continue until every success criterion is checked off.

### Phase 5: Evidence and Closeout

- [x] Preserve the key command outputs needed to prove the final passing run.
- [x] Summarize the final command set, affected fixes, and artefact locations.
- [x] Record any residual risk if a non-blocking external dependency remains variable.

## Concrete Commands

```bash
rm -rf /Users/Shared/antigravity/testing_folder
mkdir -p /Users/Shared/antigravity/testing_folder
rsync -a --delete /Users/Shared/antigravity/3-tier-multi-agent-architecture-work/ /Users/Shared/antigravity/testing_folder/
cp /Users/Shared/antigravity/3-tier-multi-agent-architecture-work/.env /Users/Shared/antigravity/testing_folder/.env
cd /Users/Shared/antigravity/testing_folder
ANTIGRAVITY_NONINTERACTIVE=1 bash install.sh
source .venv/bin/activate
make test-pytest
PYTHONPATH=src python src/orchestrator/antigravity-cli.py --workspace /Users/Shared/antigravity/testing_folder/workspaces/e2e-clean-room --prompt "Research and synthesize the architectural benefits of the Agent-View-Controller paradigm versus standard MVC." --verbose
```

## Risks and Checks

- Installer logic may assume a pre-existing local IDE home directory or mutate `.env` in a way that breaks copied real credentials.
- Test commands may still assume `/tmp/.venv-antigravity` instead of the repo-local `.venv`, which would break clean-user onboarding despite local developer success.
- Runtime code may still reference the original repository root, especially in architecture healing, rule loading, or workspace env precedence.
- Authentic provider calls may fail because of missing required model-specific env keys, invalid base URLs, or stricter runtime validation introduced by the model catalog changes.
- `install.sh`, `scripts/integrate_crewai.sh`, and `Makefile` currently share a `/tmp/.venv-antigravity` convention that is likely incompatible with the requested `.venv` activation flow and may require source changes.

## Validation Artefacts

- `testing_folder/.venv`
- `testing_folder/workspaces/e2e-clean-room/execution_result.json`
- `testing_folder/workspaces/e2e-clean-room/.agent/tmp/final_output.md`
- `testing_folder/workspaces/e2e-clean-room/.agent/tmp/reconstructed_prompt.md`
- `testing_folder/workspaces/e2e-clean-room/.agent/tmp/research-context.md`
- `testing_folder/workspaces/e2e-clean-room/.agent/memory/execution_log.json`

## Final Validation Result

- Final clean-room pass completed after iterative source fixes and full reinstallation loops.
- The provided real credential set only yielded stable live execution with `deepseek/deepseek-v3.2`, so the installer was exercised non-interactively with that primary model selection for the passing run.
- The direct entrypoint used for the final end-to-end runtime proof was `python main.py`, which exercised Tier 1 async orchestration, Tier 3 MCP retries/circuit breaking, and A2UI payload emission from the copied repo.

## Evidence

- Installer log: `.agent/tmp/clean-room-logs/install-pass7.log`
- Runtime env live probe: `.agent/tmp/clean-room-logs/runtime-env-pass7.log`
- Pytest pass: `.agent/tmp/clean-room-logs/pytest-pass7.log`
- Final runtime pass: `.agent/tmp/clean-room-logs/main-pass7.log`
