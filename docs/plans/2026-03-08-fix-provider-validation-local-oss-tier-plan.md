---
title: fix: replace paid proxy providers with local open-source runtime defaults
type: fix
status: active
date: 2026-03-08
---

# Fix Provider Validation With Local OSS Tier Defaults

The current runtime matrix and configured-provider audit still treat MiniMax, GLM, Kimi, and DeepSeek as first-class providers. In practice this causes provider validation and configured-provider probes to fail for installations that only intend to use OpenAI and Google, or that want keyless local fallbacks for lower tiers. The orchestration architecture itself is sound; the failure is in the provider catalog, environment contract, and healthcheck assumptions.

## Problem Statement

- [x] Replace the non-OpenAI/non-Google provider catalog entries with local open-source providers that do not require API keys.
- [x] Preserve the 3-tier multi-agent architecture and keep the existing `.env` tier variables (`PRIMARY_LLM`, `ORCHESTRATION_MODEL`, `L1_MODEL`, `L2_MODEL`, `L3_MODEL`, and fallback variants) intact.
- [x] Ensure runtime validation only requires credentials for providers that truly need them.
- [x] Ensure configured-provider inventory and healthchecks no longer emit failures for removed paid proxy providers.
- [x] Keep installer, docs, and tests aligned with the new provider surface.
- [x] Fix any `slfg`-discovered workflow breakage encountered while doing this work.

## Proposed Solution

Introduce an `Ollama` local-provider group for the non-OpenAI/non-Google catalog entries and make API keys optional at the model-catalog/runtime-contract level. Use local open-source models for the analytical/coordination/leaf-worker tiers and keep OpenAI/Google as the cloud-backed orchestration and upper-tier options.

### Target Model Topology

- [x] Keep orchestration defaults on OpenAI/OpenAI fallback.
- [x] Keep Level 1 primary on Google Gemini.
- [x] Replace Level 1 fallback with a local Ollama reasoning-capable model.
- [x] Replace Level 2 primary/fallback with local Ollama coordinator-safe models.
- [x] Replace Level 3 primary/fallback with local Ollama coding/worker-safe models.

## Implementation Steps

### 1. Model Catalog and Runtime Contract

- [x] Update `src/engine/model_catalog.py` to remove MiniMax, GLM, Kimi, and DeepSeek entries.
- [x] Add local Ollama-based open-source model entries with `OLLAMA_BASE_URL` and no required API key.
- [x] Update default tier selections and env defaults for L1/L2/L3 fallbacks and primaries.
- [x] Update `PRIMARY_PROVIDER_GROUPS` and runtime notes accordingly.

### 2. Validation and Builder Logic

- [x] Update `src/engine/llm_config.py` to support model specs without API keys.
- [x] Update `src/engine/runtime_env.py` inventory discovery and active-provider key resolution for optional-key providers.
- [x] Update `src/engine/provider_healthchecks.py` to probe Ollama locally instead of paid proxy endpoints.
- [x] Make `scripts/validate_runtime_env.py` degrade cleanly when live LLM probing cannot import optional runtime dependencies.

### 3. Direct LiteLLM Call Sites

- [x] Update `src/orchestrator/tier1_manager.py` for optional-key local providers.
- [x] Update `src/experimental/langgraph/langgraph_orchestrator.py` for optional-key local providers.

### 4. Documentation and Install Surface

- [x] Update `.env.template` with the new tier defaults and local-provider env contract.
- [x] Update `README.md` and `SUPPORTED_LLMS.md` to remove paid proxy provider references and document the new local provider defaults.
- [x] Keep the tier env variable names and selection flow intact in `install.sh`.

### 5. Test Alignment

- [x] Update structural tests for the new catalog entries and active-provider keys.
- [x] Update provider-healthcheck tests to cover local Ollama inventory/probe behavior.
- [x] Update runtime validation/install-script tests to match the new defaults.

## Acceptance Criteria

- [x] `resolve_runtime_env()` no longer surfaces MiniMax, GLM, Kimi, or DeepSeek as active/configured providers by default.
- [x] `validate_provider_runtime_env(strict=True)` only requires OpenAI/Google keys plus `OLLAMA_BASE_URL` when local OSS tiers are selected.
- [x] Configured-provider probing no longer fails on removed paid proxy providers.
- [x] `.env.template`, `README.md`, `SUPPORTED_LLMS.md`, and installer output match the new provider topology.
- [x] Test suite coverage is updated for the new model/provider matrix.

## Completion Notes

- [x] `scripts/validate_runtime_env.py --probe-configured-providers` passed against the current workspace and regenerated `docs/reports/validation_report.json`.
- [x] `scripts/validate_runtime_env.py --live` passed for the active primary matrix: orchestration, level1, level2, and level3 all returned `OK`.
- [x] Local fallback models `ollama/qwen3:14b` and `ollama/qwen2.5-coder:14b` were pulled into Ollama and answered `OK` through the same `build_llm()` path used by the application runtime.
- [x] `ce-review` follow-up fixes aligned Docker, benchmark, and verification surfaces with the new provider topology.
- [x] `test-browser` and `feature-video` were skipped cleanly because this branch changed no route-mapped UI flows.

## Sources

- `src/engine/model_catalog.py`
- `src/engine/llm_config.py`
- `src/engine/runtime_env.py`
- `src/engine/provider_healthchecks.py`
- `scripts/validate_runtime_env.py`
- `src/orchestrator/tier1_manager.py`
- `src/experimental/langgraph/langgraph_orchestrator.py`
- `.env.template`
- `README.md`
- `SUPPORTED_LLMS.md`
- `tests/test_crewai_integration.py`
- `tests/test_provider_healthchecks.py`
- `tests/test_validate_runtime_env.py`
