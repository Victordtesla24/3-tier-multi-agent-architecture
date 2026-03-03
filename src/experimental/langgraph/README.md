# LangGraph Orchestrator (Experimental)

> **⚠️ This module is experimental and NOT part of the canonical runtime.**

The LangGraph-based orchestrator was the initial prototype for the 3-tier architecture. It has been superseded by the **CrewAI-backed orchestrator** (`src/engine/crew_orchestrator.py`) which is the canonical production runtime.

## Status

- **Not used** by the CLI (`src/orchestrator/antigravity-cli.py`)
- **Not used** by Docker or CI
- **Retained** for reference and potential future experimentation

## Canonical Alternative

Use the CrewAI orchestrator via:

```bash
PYTHONPATH=src uv run python src/orchestrator/antigravity-cli.py \
  --workspace /tmp/antigravity_workspace \
  --prompt "Your objective here" \
  --verbose
```

Or via Docker:

```bash
docker compose up
```
