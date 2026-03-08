# Supported LLMs & Model Matrix

The Antigravity 3-Tier Architecture uses a dynamic fallback routing system. This ensures that if a frontier model experiences an outage or rate limit, the architecture cascades to a compatible fallback without process interruption.

Tier selection precedence is:
1. `ORCHESTRATION_MODEL`, `L1_MODEL`, `L2_MODEL`, `L3_MODEL`
2. `PRIMARY_LLM` as orchestration fallback / legacy compatibility
3. Catalog defaults

## Official Runtime Matrix

| Architecture Tier | Primary Model | Fallback Model | Required ENV Keys |
| :--- | :--- | :--- | :--- |
| **Orchestration (Manager)** | `openai/gpt-5.4` | `openai/gpt-5.2-codex` | `OPENAI_API_KEY` |
| **Level 1 (Analytical)** | `gemini/gemini-3.1-pro-preview` | `ollama/qwen3:14b` | `GOOGLE_API_KEY`, `OLLAMA_BASE_URL` |
| **Level 2 (Coordinator/QA)** | `ollama/qwen3:8b` | `ollama/qwen3:14b` | `OLLAMA_BASE_URL` |
| **Level 3 (Leaf Worker)** | `ollama/qwen2.5-coder:7b` | `ollama/qwen2.5-coder:14b` | `OLLAMA_BASE_URL` |

## Installer Catalog

The installer exposes the latest verified primary model catalog across:

| Provider | `PRIMARY_LLM` Value | Runtime Model | ENV |
| :--- | :--- | :--- | :--- |
| OpenAI GPT-5.4 | `openai/gpt-5.4` | `openai/gpt-5.4` | `OPENAI_API_KEY` |
| OpenAI GPT-5.2 Codex | `openai/gpt-5.2-codex` | `openai/gpt-5.2-codex` | `OPENAI_API_KEY` |
| Google Gemini 3.1 Pro Preview | `gemini/gemini-3.1-pro-preview` | `gemini/gemini-3.1-pro-preview` | `GOOGLE_API_KEY` |
| DeepSeek Chat | `deepseek/deepseek-chat` | `deepseek/deepseek-chat` | `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL` |
| Ollama Qwen 3 14B | `ollama/qwen3:14b` | `ollama/qwen3:14b` | `OLLAMA_BASE_URL` |
| Ollama Qwen 3 8B | `ollama/qwen3:8b` | `ollama/qwen3:8b` | `OLLAMA_BASE_URL` |
| Ollama Qwen 2.5 Coder 14B | `ollama/qwen2.5-coder:14b` | `ollama/qwen2.5-coder:14b` | `OLLAMA_BASE_URL` |
| Ollama Qwen 2.5 Coder 7B | `ollama/qwen2.5-coder:7b` | `ollama/qwen2.5-coder:7b` | `OLLAMA_BASE_URL` |

## Runtime Normalization Rules

1. OpenAI GPT-5 selections preserve requested `thinking=xHigh` in metadata, but the runtime normalizes to `reasoning_effort=high` because the installed CrewAI/LiteLLM surface exposes only `low|medium|high`.
2. OpenAI GPT-5 selections omit `temperature` at runtime because GPT-5 reasoning models reject it.
3. Gemini 3 selections apply `temperature=0.15` and rely on Gemini 3's documented default high thinking when `thinkingLevel` is not explicitly exposed by CrewAI.
4. DeepSeek selections use `DEEPSEEK_API_KEY` and default to `DEEPSEEK_BASE_URL=https://api.deepseek.com/v1` when no override is supplied.
5. Ollama selections run through the local runtime at `OLLAMA_BASE_URL` and do not require API keys.
6. `GEMINI_API_KEY` remains accepted as a legacy alias for `GOOGLE_API_KEY`.
7. `scripts/validate_runtime_env.py --probe-configured-providers` probes every configured provider surface in `.env`, while `--live` probes only the active primary tier selections.
