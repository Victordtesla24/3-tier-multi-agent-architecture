---
status: complete
priority: p1
issue_id: "007"
tags: [providers, runtime, docker, docs]
dependencies: []
---

# Remove Legacy Provider Surfaces

Legacy MiniMax, GLM, Kimi, and DeepSeek references remained in executable and user-facing surfaces after the runtime matrix moved to OpenAI, Google, and Ollama-backed Qwen models.

## Problem Statement

Core runtime validation had been fixed, but adjacent operational surfaces still described or exported the retired paid proxy providers. That left the repo in an inconsistent state where the main validator passed while Docker startup wiring, benchmark bootstrap env, and top-level runtime documentation still implied obsolete provider requirements.

## Findings

- `docker-compose.yml` exported `MINIMAX_*` and `DEEPSEEK_*` instead of the active local-provider base URL.
- `benchmarks/run_benchmark.py` injected legacy proxy credentials into the benchmark runtime bootstrap.
- `README.md` and `src/engine/crew_orchestrator.py` still described the old provider topology.
- Containerized Ollama access needed a Docker-safe base URL instead of inheriting host-local `127.0.0.1`.

## Proposed Solutions

### Option 1: Patch Only Runtime Validation

**Approach:** Leave adjacent scripts and docs untouched because the main validator already passes.

**Pros:**
- Lowest effort
- No additional doc or tooling changes

**Cons:**
- Leaves Docker and benchmark paths inconsistent
- Keeps review findings open

**Effort:** <1 hour

**Risk:** Medium

---

### Option 2: Patch All Operational Surfaces

**Approach:** Align Docker env, benchmark bootstrap, runtime docs, and workflow artifacts with the new OpenAI/Google/Ollama matrix.

**Pros:**
- Removes contradictory provider guidance
- Makes the repo operational across more entry points

**Cons:**
- Touches multiple surfaces

**Effort:** 1-2 hours

**Risk:** Low

## Recommended Action

Implement Option 2 and close the finding only after the updated runtime surfaces are validated.

## Technical Details

**Affected files:**
- `docker-compose.yml`
- `benchmarks/run_benchmark.py`
- `README.md`
- `src/engine/crew_orchestrator.py`

## Resources

- Plan: `docs/plans/2026-03-08-fix-provider-validation-local-oss-tier-plan.md`
- Validation script: `scripts/validate_runtime_env.py`

## Acceptance Criteria

- [x] Docker wiring exports `OLLAMA_BASE_URL` instead of retired provider env vars
- [x] Benchmark bootstrap no longer relies on MiniMax or DeepSeek env vars
- [x] User-facing docs and runtime docstrings describe the OpenAI/Google/Ollama topology
- [x] Review finding is resolved and recorded

## Work Log

### 2026-03-08 - Review Synthesis

**By:** Codex

**Actions:**
- Identified stale provider surfaces during the `ce-review` phase
- Scoped executable and user-facing files that still referenced retired providers
- Prepared direct alignment changes so the issue could be resolved in the same workflow

**Learnings:**
- Core runtime validation can pass while adjacent operational surfaces remain inconsistent
- Containerized Ollama access requires a Docker-safe host mapping

### 2026-03-08 - Resolution

**By:** Codex

**Actions:**
- Replaced retired provider env exports in `docker-compose.yml` with Docker-safe Ollama wiring
- Updated `benchmarks/run_benchmark.py` to bootstrap the active OpenAI/Google/Ollama runtime contract
- Updated `README.md` and `src/engine/crew_orchestrator.py` to describe the current provider topology
- Verified the fixes with `python3 -m py_compile`, focused pytest coverage, `docker compose config`, and the benchmark harness

**Learnings:**
- Provider migrations need follow-through across benchmark and container entry points, not just the core validator
