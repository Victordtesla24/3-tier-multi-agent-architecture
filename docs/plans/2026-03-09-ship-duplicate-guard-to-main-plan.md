---
title: "fix: ship duplicate guard and repo cleanup to main"
type: fix
status: completed
date: 2026-03-09
---

# fix: ship duplicate guard and repo cleanup to main

Publish the duplicate-content enforcement, symlink prohibition, and repository cleanup changes directly to `main`, then verify GitHub Actions passes and the repository tree is clean afterward.

## Scope

- [x] Include the duplicate guard implementation and its tests.
- [x] Include the tracked symlink deletion and duplicate config cleanup.
- [x] Include the related documentation updates needed for a clean tree.
- [x] Exclude ignored local environment files and runtime artifacts.

## Execution Plan

### Phase 1: Validate locally

- [x] Review the exact staged candidate changes before commit.
- [x] Run the duplicate-content audit locally.
- [x] Run the targeted pytest coverage for duplicate-guard and orchestration parity paths.
- [x] Run repo linting or equivalent fast quality checks where available.

### Phase 2: Ship to main

- [x] Confirm local `main` is the active branch and aligned with `origin/main` before commit.
- [ ] Stage only the intended repository changes for this ship operation.
- [ ] Create a conventional commit on `main`.
- [ ] Push the commit to `origin/main`.

### Phase 3: Verify GitHub readiness

- [ ] Watch the GitHub Actions run triggered by the push.
- [ ] Confirm the workflow completes without errors.
- [ ] Confirm `git status --short` is clean after the push.
- [ ] Confirm local `main` matches `origin/main`.

## Acceptance Criteria

- [ ] `main` on GitHub contains the duplicate guard, tests, and cleanup changes.
- [x] No tracked symlink remains in managed repository content.
- [ ] The local repository worktree is clean after the push.
- [ ] The post-push GitHub Actions run completes successfully.
- [ ] The repository is ready for normal use without duplicate-file drift.

## Post-Deploy Monitoring & Validation

- Watch the `Antigravity Architecture CI` workflow on `main` for the post-push run.
- Healthy signal: secret redaction, duplicate audit, test collection, pytest, and Docker build all complete with `success`.
- Failure signal: any workflow step fails, or a new symlink / duplicate-content violation appears in CI.
- Mitigation trigger: if the workflow fails, inspect the failing job logs immediately and fix `main` before any further feature work.
- Validation window: immediate, until the first post-push `main` run completes.
- Owner: Codex session executing the ship operation.

## Validation Evidence

- `git rev-list --left-right --count origin/main...HEAD` -> `0 0`
- `gh auth status` -> authenticated as `Victordtesla24` with `repo` and `workflow` scopes
- `PYTHONPATH=src .venv/bin/python scripts/enforce_no_duplicates.py` -> `Duplicate content audit passed.`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_duplicate_guard.py tests/test_runtime_graph.py tests/test_capability_parity.py -q -p no:cacheprovider` -> `38 passed`
- `.venv/bin/ruff check .` -> `All checks passed!`
- Secret redaction gate over tracked files -> `Secret redaction gate passed.`
- `PYTHONPATH=src .venv/bin/python src/engine/config_manager.py .agent/tmp/mock_gemini.md` -> success
- CI collect-only subset -> `76 tests collected`
- CI pytest subset -> `76 passed`
- Added `.dockerignore` after a local Docker context audit showed the missing file forced a `1.4G` virtualenv into the build context.
- Local `docker build -t antigravity-engine:latest .` still fails during BuildKit image export with Docker Desktop EOF after dependency installation. Treat GitHub Actions as the authoritative Docker validation path for this ship.
