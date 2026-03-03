# Quickstart Guide

Get up and running with the Antigravity 3-Tier Multi-Agent Architecture in under 5 minutes.

## 1. Local Initialization

```bash
git clone https://github.com/Victordtesla24/3-tier-multi-agent-architecture.git
cd 3-tier-multi-agent-architecture

# Install dependencies deterministically
uv sync --all-extras

# Setup Environment
cp .env.template .env
# Edit .env and supply your GOOGLE_API_KEY and OPENAI_API_KEY at a minimum.

# Provision directories and setup scripts
chmod +x scripts/integrate_crewai.sh
./scripts/integrate_crewai.sh
```


## 2. Running Your First Objective (Standalone)

You can launch the orchestrator directly from the terminal without integrating it into an IDE.

```bash
export PYTHONPATH=src
uv run python src/orchestrator/antigravity-cli.py \
  --workspace /tmp/ag_workspace \
  --prompt "Write a Python script that fetches the current Bitcoin price and saves it to a file." \
  --verbose
```


## 3. Reviewing the Output

The architecture enforces strict payload generation. Check the specified workspace directory (in this case `/tmp/ag_workspace/.agent/tmp/final_output.md`) to see the production-ready code with absolutely no placeholders.

You can also review the deterministic logs in `/tmp/ag_workspace/.agent/memory/execution_log.json`.
