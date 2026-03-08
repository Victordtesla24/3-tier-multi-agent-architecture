---
title: fix: restore deepseek provider compatibility without breaking local oss defaults
type: fix
status: completed
date: 2026-03-08
---

# Restore DeepSeek Provider Compatibility

The current branch already replaced legacy paid proxy providers with OpenAI, Google, and local Ollama-backed open-source defaults for the lower tiers. The follow-up requirement is to keep DeepSeek as a supported provider as well, because the API is valid in this environment. The fix must preserve the 3-tier multi-agent architecture, keep the existing `.env` model-level variables intact, and avoid reintroducing provider-validation failures.

## Problem Statement

- [x] Keep OpenAI and Google support intact.
- [x] Restore DeepSeek as an explicitly supported provider.
- [x] Preserve local Ollama-backed defaults for the lower tiers so keyless operation still works when DeepSeek is not selected.
- [x] Keep `.env` tier variables and fallback variables unchanged.
- [x] Fix runtime/provider-validation breakage discovered during the DeepSeek restore.

## Proposed Solution

Restore DeepSeek to the provider catalog, runtime contract, environment validation, healthcheck inventory, installer surface, and documentation as an optional OpenAI-compatible provider. Keep the active default matrix on OpenAI, Google, and Ollama, and normalize any stale DeepSeek aliases to the working LiteLLM/CrewAI runtime identifier.

## Implementation Steps

### 1. Catalog and Runtime Contract

- [x] Reintroduce DeepSeek in `src/engine/model_catalog.py` with the correct OpenAI-compatible env contract.
- [x] Keep DeepSeek out of the default lower-tier runtime selections so the local OSS defaults remain intact.
- [x] Normalize stale runtime aliases in `src/engine/runtime_env.py` to the working DeepSeek model identifier.

### 2. Validation and Call Sites

- [x] Update `src/engine/llm_config.py` to treat DeepSeek like the other OpenAI-compatible non-reasoning-effort providers.
- [x] Update direct LiteLLM call sites to avoid unsupported request parameters for DeepSeek.
- [x] Update `src/engine/provider_healthchecks.py` to probe DeepSeek correctly with `DEEPSEEK_API_KEY` and `DEEPSEEK_BASE_URL`.

### 3. Docs and Install Surface

- [x] Update `.env.template`, `README.md`, `SUPPORTED_LLMS.md`, `docker-compose.yml`, and installer helpers to document DeepSeek as optional support.
- [x] Keep the tiered environment naming and install flow intact.

### 4. Test Alignment

- [x] Add or update tests for DeepSeek provider env resolution, installer handling, and provider healthchecks.
- [x] Re-run focused coverage for the provider/runtime stack.

## Acceptance Criteria

- [x] DeepSeek is supported again without becoming the default provider for lower tiers.
- [x] `validate_provider_runtime_env(strict=True)` accepts DeepSeek when the required DeepSeek env vars are present.
- [x] Configured-provider probing can probe DeepSeek via its OpenAI-compatible endpoint.
- [x] Legacy `deepseek/deepseek-v3.2` references normalize to a working runtime model.
- [x] Existing OpenAI, Google, and Ollama flows remain intact.

## Completion Notes

- [x] DeepSeek was restored as an optional provider across the catalog, runtime-env normalization, healthchecks, docs, and installer surface.
- [x] The non-working runtime alias `deepseek/deepseek-v3.2` was normalized to `deepseek/deepseek-chat`, which is the working model identifier for this runtime path.
- [x] Focused provider/runtime tests were updated to cover the DeepSeek path.
- [x] Focused tests passed: `51 passed`.
- [x] Direct runtime validation passed through `build_llm(model_spec_from_catalog("deepseek/deepseek-chat"))`.
- [x] Direct configured-provider probe for DeepSeek returned `success=True` and `http_status=200`.
- [x] Review found no new DeepSeek-specific defects on the current branch.
- [x] Browser testing was skipped cleanly because the tracked branch diff contains no route-mapped UI files.
- [x] Feature video was skipped cleanly because no UI flow changed and there is no PR for the current branch to annotate.

## Sources

- `src/engine/model_catalog.py`
- `src/engine/llm_config.py`
- `src/engine/runtime_env.py`
- `src/engine/provider_healthchecks.py`
- `src/orchestrator/tier1_manager.py`
- `src/experimental/langgraph/langgraph_orchestrator.py`
- `.env.template`
- `README.md`
- `SUPPORTED_LLMS.md`
- `docker-compose.yml`
- `scripts/integrate_crewai.sh`
- `verify_interactive.py`
- `tests/test_crewai_integration.py`
- `tests/test_provider_healthchecks.py`
- `tests/test_install_script.py`
