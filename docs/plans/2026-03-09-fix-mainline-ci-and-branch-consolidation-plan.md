---
title: "fix: restore mainline CI and consolidate branch history"
type: fix
status: completed
date: 2026-03-09
---

# fix: restore mainline CI and consolidate branch history

## Overview

Stabilize `main` after the March 9, 2026 workflow-file regression, preserve all newer local changes already developed on `fix/provider-validation-local-oss-tiers`, validate the full CI path locally, and merge all surviving work into one clean `main` branch without dropping any branch content.

## Problem Statement

- [x] `origin/main` is red because commit `46eb74180103f69507f4e307840cbef3852d0291` deleted `.github/workflows/ci.yml`, which causes GitHub Actions to reject the workflow before any jobs start.
- [x] The current repair branch contains six newer commits beyond `origin/main`, including CI and runtime fixes that must be preserved.
- [x] Local branches must be audited before cleanup so no unique commits are lost when consolidating everything into `main`.

## Research Findings

- Current GitHub status: the latest failed run is Actions run `22831328692` on `main`, created on March 8, 2026, and GitHub reports it as "This run likely failed because of a workflow file issue."
- Branch audit: `feat/report-gap-hardening`, `feat/agent-native-improvement-plan`, and `improvement-plan-batch1` are already ancestors of `origin/main`, so they do not carry unique commits that still need integration.
- Current branch divergence: `origin/main...HEAD` is `1 6`, which means `HEAD` is missing the single workflow-deletion commit from `origin/main` and already contains six newer commits to preserve.
- Final GitHub validation: Actions run `22831551422` on commit `afe66829461494c3487d9a6eac7eed9426589a55` completed with `success`, including the Docker build stage.

## Implementation Plan

### Phase 1: Reconcile branch history safely

- [x] Bring the current repair branch up to date with `origin/main`.
- [x] Resolve the workflow deletion by restoring `.github/workflows/ci.yml` while preserving the rest of the current branch changes.
- [x] Confirm the resulting branch contains all intended commits from both sides.

### Phase 2: Validate CI parity locally

- [x] Run the workflow-equivalent commands locally, including config-merger validation, collection audit, targeted tests, and Docker build.
- [x] Fix any failing tests or environment assumptions exposed by the refreshed branch state.
- [x] Record validation evidence in this plan.

### Phase 3: Consolidate to main and clean branches

- [x] Fast-forward or merge the verified branch into local `main`.
- [x] Push `main` to origin and verify the new GitHub Actions run is green.
- [x] Delete or retire fully merged local branches after their ancestry is confirmed.

## Acceptance Criteria

- [x] Local `main` contains every intended commit from the current repair branch.
- [x] `.github/workflows/ci.yml` exists on `main` and is accepted by GitHub Actions.
- [x] Local CI-equivalent validation passes.
- [x] GitHub Actions on `main` completes successfully after the push.
- [x] No remaining local feature branches retain unique commits outside `main`.

## Validation Evidence

- `git rebase origin/main` on `fix/provider-validation-local-oss-tiers` completed cleanly, preserving the branch fixes on top of commit `46eb74180103f69507f4e307840cbef3852d0291`.
- `test -f .github/workflows/ci.yml` -> `present`
- `git show HEAD:.github/workflows/ci.yml` exposed that `main` still tracked an empty workflow blob after consolidation, which required a direct workflow restore commit.
- Secret redaction gate using `.venv/bin/python` -> `Secret redaction gate passed.`
- `PYTHONPATH=src .venv/bin/python src/engine/config_manager.py .agent/tmp/mock_gemini.md` -> success
- `cd tests && ... ../.venv/bin/python -m pytest ... --collect-only -q -p no:cacheprovider` -> `76 tests collected`
- `cd tests && ... ../.venv/bin/python -m pytest ... -v -p no:cacheprovider` -> `76 passed`
- `GOOGLE_API_KEY=dummy ... PYTHONPATH=src .venv/bin/python -m pytest -q -p no:cacheprovider` -> `143 passed`
- `.venv/bin/ruff check .` -> `All checks passed!`
- `docker build -t antigravity-engine:latest .` could not run locally because the Docker daemon socket `/Users/vics-macbook-pro/.docker/run/docker.sock` is unavailable in this environment. GitHub Actions remains the authoritative Docker-build validation path.
- `git push origin main` published commit `afe66829461494c3487d9a6eac7eed9426589a55`.
- GitHub Actions run `22831551422` -> `success`: install, redaction gate, config-manager validation, collection audit, unit/integration tests, and Docker build all passed.
- Deleted merged local branches: `fix/provider-validation-local-oss-tiers`, `feat/agent-native-improvement-plan`, `feat/report-gap-hardening`, `improvement-plan-batch1`.
- Deleted merged remote branch: `origin/fix/provider-validation-local-oss-tiers`.

## Post-Deploy Monitoring & Validation

- Watch GitHub Actions workflow `.github/workflows/ci.yml` on `main` for future pushes.
- Healthy signal: `build_and_test` starts normally, executes jobs, and finishes with `success` as it did for run `22831551422`.
- Failure signal: GitHub reports a workflow-file issue again, or any validation/test job fails.
- Mitigation trigger: if a future `main` run fails, inspect the specific run logs and compare against commits `1bfca03` and `afe6682`, which restored the workflow and fixed the virtualenv pathing.
- Validation window: completed for the first post-push run; continue monitoring on subsequent pushes.
- Owner: Codex session executing the consolidation.
