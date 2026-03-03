# Supported LLMs & Model Matrix

The Antigravity 3-Tier Architecture uses a dynamic fallback routing system. This ensures that if a frontier model experiences an outage or a rate limit, the architecture instantaneously cascades down to a highly capable fallback without process interruption.

## Official 3-Tier Matrix

| Architecture Tier | Primary Model | Fallback Model | Required ENV Keys |
| :--- | :--- | :--- | :--- |
| **Orchestration (Manager)** | `gemini/gemini-3.1-pro-preview` | `openai/gpt-5.2-codex` | `GOOGLE_API_KEY`, `OPENAI_API_KEY` |
| **Level 1 (Analytical)** | `openai/gpt-5.2-codex` | `openai/minimax-m2.5` | `OPENAI_API_KEY`, `MINIMAX_API_KEY`, `MINIMAX_BASE_URL` |
| **Level 2 & 3 (Worker/QA)** | `openai/minimax-m2.5` | `openai/deepseek-v3.2` | `MINIMAX_API_KEY`, `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL` |

### Custom Providers via OpenAI Compatibility

Because the architecture utilizes the `litellm` and `crewai[openai]` backbones, any model exposing an OpenAI-compatible `/v1/chat/completions` endpoint can be injected.

For example, to use a local model via **Ollama**, configure `.env`:
```env
LOCAL_LLM_API_KEY="ollama"
LOCAL_LLM_BASE_URL="http://localhost:11434/v1"
```

And update the `ModelMatrix` in `src/engine/llm_config.py`.

### Mandatory vs Optional Models

1. **Gemini 3.1 Pro Preview**: `MANDATORY`. Driven by `GOOGLE_API_KEY`. It governs the critical reasoning phase of the orchestrator.
2. **GPT-5.2-Codex**: `MANDATORY`. Driven by `OPENAI_API_KEY`.
3. **MiniMax and DeepSeek**: `OPTIONAL` but highly recommended for Level 2/3 speed and redundancy. If omitted, configuring the primary `OPENAI_API_KEY` to cover workers will suffice until limit exhaustion.
