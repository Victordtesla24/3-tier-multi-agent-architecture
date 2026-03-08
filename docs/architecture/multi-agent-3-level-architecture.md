# CrewAI Integration Architecture


> **Docs ↔ Code Contract**
> - [x] All referenced file paths (e.g. `src/engine/llm_config.py`, `src/engine/crew_agents.py`, `src/orchestrator/antigravity-cli.py`) physically exist in the repository.
> - [x] No raw script output or excessive code dumps are embedded directly inside this architectural spec.
> - [x] The `uv run python src/orchestrator/antigravity-cli.py` workflow is the canonical executable path.


The integration strategy leverages CrewAI's **Flows** (orchestration layer) and **Crews** (collaborative agent teams) while preserving your existing 3-tier hierarchy (L1 Orchestration, L2 Sub-Agents, L3 Leaf Workers).

# Core Integration Strategy

## Architectural Mapping

**Your Current Architecture → CrewAI Integration:**

- **Orchestration AI Model** → CrewAI Flow Manager + L1 Orchestration Crew
- **L1 Tier** → CrewAI Hierarchical Manager Agent with custom LLM
- **L2 Tier** → Specialized CrewAI Agents with task delegation
- **L3 Tier** → Leaf Worker Agents executing atomic tasks


# CrewAI Integration Into the Antigravity 3‑Tier Multi‑Agent Architecture

## Research scope and non‑negotiable integration constraints

This integration is designed to embed CrewAI’s **Agent / Task / Crew** execution model into the existing **3‑tier pipeline** (Prompt Reconstruction → Research → L1 Orchestration → L2 Execution → Verification), while preserving the 3‑tier directory layout as the system’s primary foundation and wiring CrewAI in as the orchestration runtime. CrewAI’s documented primitives map cleanly onto the 3‑tier boundaries: **Agents** are autonomous units that can collaborate, retain memory, and delegate where allowed, **Tasks** represent executable work units with explicit expected outputs and optional context dependencies, and a **Crew** is the orchestrated execution container that runs tasks through a defined process (sequential or hierarchical). 

Key CrewAI capabilities required by your brief and explicitly supported in official documentation are: (a) delegation support when `allow_delegation=True`, including documented delegation behaviour even in sequential workflows when multiple agents exist, (b) memory being enabled at Crew level via `memory=True` with built‑in short/long/entity memory, and (c) hierarchical process support with a manager model or manager agent coordinating delegation and validation.    

Your LLM requirements introduce a strict production constraint: each tier must use a **tier‑specific model pair** (primary → fallback) and enforce a **tier‑specific reasoning/thinking effort**. For OpenAI, `reasoning_effort` explicitly supports `low`, `medium`, `high`, and `xhigh` (among others) and is part of the official API parameter surface. For Gemini 3 models, Google documents that `thinkingLevel` controls reasoning behaviour, and that if a thinking level is not provided, Gemini 3 defaults to a dynamic `"high"` thinking level. 

## CrewAI to 3‑tier architectural mapping

CrewAI’s concepts map into the 3‑tier system with minimal impedance mismatch:

The **Orchestration Tier (Manager/Router)** corresponds to CrewAI’s **manager** role in hierarchical execution. CrewAI’s documentation describes a hierarchical process where a manager agent/model oversees task execution, including planning, delegation, and validation, and requires specifying a `manager_llm` or `manager_agent`. In this integration, the manager’s LLM is bound to the Orchestration Tier model pair:

- Primary: **OpenAI/GPT‑5.4** (requested xHigh thinking preserved in metadata and normalized to runtime high)
- Fallback: **OpenAI/GPT‑5.3‑Codex** (requested xHigh thinking preserved in metadata and normalized to runtime high)

The **Level 1 Tier (Senior/Analytical Agents)** maps to CrewAI Agents configured for planning, orchestration decomposition, and analysis. CrewAI Agents can be explicitly assigned an LLM (overriding Crew defaults), can use reasoning/planning features, and can delegate when allowed. This tier is bound to:

- Primary: **Google/Gemini‑3‑Pro‑Preview** (High thinking, `temperature=0.15`)
- Fallback: **Ollama/Qwen 3 14B** via local runtime (Medium reasoning intent, `temperature=0.15`)

The **Level 2 Tier (Coordinator / QA Agents)** maps to CrewAI Agents specialised for coordination, validation, and retry gating. This tier is bound to:

- Primary: **Ollama/Qwen 3 8B** via local runtime (`temperature=0.15`)
- Fallback: **Ollama/Qwen 3 14B** via local runtime (`temperature=0.15`)

The **Level 3 Tier (Execution / Leaf Workers)** maps to CrewAI Agents responsible for atomic task execution. By default it mirrors the Level 2 primary provider family while remaining independently configurable through `.env`:

- Primary: **Ollama/Qwen 2.5 Coder 7B** via local runtime (`temperature=0.15`)
- Fallback: **Ollama/Qwen 2.5 Coder 14B** via local runtime (`temperature=0.15`)

CrewAI’s built‑in memory system is enabled at the Crew level via `memory=True`, and storage location can be controlled via the `CREWAI_STORAGE_DIR` environment variable. This integration routes CrewAI memory storage into the existing `.agent/memory/` hierarchy to remain consistent with the 3‑tier architecture’s persistence model.

## Hierarchical model matrix implementation details

### OpenAI reasoning effort enforcement

OpenAI’s GPT‑5 family exposes reasoning controls, but the installed CrewAI/LiteLLM surface currently accepts `low`, `medium`, and `high`. This integration therefore preserves requested `thinking=xHigh` in metadata and normalizes runtime reasoning to `high`:

- Orchestration primary GPT‑5.4: `reasoning_effort="high"`
- Orchestration fallback GPT‑5.3‑Codex: `reasoning_effort="high"`
- Local Ollama tiers do not receive a provider-specific `reasoning_effort` parameter; model/runtime defaults handle reasoning behaviour while `temperature=0.15` remains applied.

GPT‑5 family models also reject `temperature`, so requested `temperature=0.15` is omitted at runtime for GPT‑5 selections.

### Gemini thinking effort enforcement

Google documents that Gemini 3 models default to dynamic high thinking if `thinkingLevel` is not specified. CrewAI’s Gemini integration is implemented via the Google GenAI SDK and supports standard Gemini model invocation with `GOOGLE_API_KEY` or `GEMINI_API_KEY`. Because CrewAI’s public LLM documentation does not explicitly document a pass‑through parameter for `thinkingLevel`, this implementation treats the configured analytical tier as **High thinking** by selecting the Gemini 3 Pro Preview model and relying on Google’s documented default dynamic `"high"` thinking behaviour for Gemini 3 when `thinkingLevel` is omitted. `temperature=0.15` is applied directly.

### Local runtime routing for Ollama

CrewAI’s LiteLLM integration supports Ollama models via a local `base_url`. This integration routes keyless open-source tiers through:

- Ollama requests: `base_url=$OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`)

The runtime now treats tier-specific env vars as authoritative: `ORCHESTRATION_MODEL`, `L1_MODEL`, `L2_MODEL`, and `L3_MODEL` override `PRIMARY_LLM`, while `L2_AGENT_SWARMS` and `L3_AGENT_SWARMS` control task-graph evaluation and execution concurrency. Legacy alias env names such as `GEMINI_API_KEY` remain accepted and are normalized in memory without rewriting the user’s `.env`.

The validation flow is intentionally split into two layers. `scripts/validate_runtime_env.py --live` proves the active primary tier selections can answer a minimal prompt through CrewAI/LiteLLM, while `--probe-configured-providers` separately probes every configured provider credential in `.env` with official REST calls so inactive or dead credentials are surfaced explicitly instead of being hidden by a healthy active matrix.


## Production configuration code implementing the model matrix and CrewAI merge

### llm_config.py

The integration hardcodes the tiered model matrix and configures normalized OpenAI reasoning effort together with OpenAI‑compatible proxy base URLs via environment variables. CrewAI’s LLM documentation explicitly supports OpenAI `base_url` override and Gemini API key configuration.

> **Source:** See [`src/engine/llm_config.py`](../../../src/engine/llm_config.py) for the production implementation.

### crew_orchestrator.py

This file defines a three‑tier CrewAI orchestrator that binds:
- Manager/router to the orchestration-tier fallback LLM wrapper
- Senior agents to the L1 fallback wrapper
- Worker agent to the L2 fallback wrapper

CrewAI’s hierarchical process and manager agent patterns are explicitly documented. CrewAI memory is enabled at Crew level and stored under `CREWAI_STORAGE_DIR`.

> **Source:** See [`src/engine/crew_orchestrator.py`](../../../src/engine/crew_orchestrator.py) for the production implementation.

## Workspace cleanup, validation gates, and operational notes

The final workspace is intentionally reduced to the **single source of truth**: `./3-tier-arch` is the retained foundation and `./crewai-source` is deleted after dependency‑based integration. This directly satisfies your “purge redundant files” requirement by ensuring no duplicated upstream framework files remain after integration.

CrewAI’s memory system persists under `.agent/memory/crewai_storage` and is enabled using `memory=True`, consistent with CrewAI documentation describing built‑in memory and storage configuration via `CREWAI_STORAGE_DIR`.

To ensure your **thinking/reasoning policy** is maintained across model providers, this integration uses strict runtime configuration surfaces that are officially documented: GPT‑5 requests preserve requested `thinking=xHigh` but normalize runtime `reasoning_effort` to `high`, GPT‑5 temperatures are omitted because the API rejects them, and Gemini 3’s high thinking behaviour is satisfied by selecting a Gemini 3.x model and relying on Google’s documented default `"high"` thinking level when `thinkingLevel` is not specified.
