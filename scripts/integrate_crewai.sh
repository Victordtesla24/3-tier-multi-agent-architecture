#!/bin/bash
# CrewAI Integration Script for 3-Tier Architecture

set -e

PYTHON_VERSION="3.12"

echo "🌌 Antigravity 3-Tier Architecture - CrewAI Integration"
echo "======================================================="

# Step 1: Configure UV environment
export UV_PROJECT_ENVIRONMENT=/tmp/.venv-antigravity
export UV_CACHE_DIR=/tmp/uv-cache

# Step 2: Ensure correct Python version
echo "🐍 Ensuring Python ${PYTHON_VERSION}..."
uv python install "${PYTHON_VERSION}" 2>/dev/null || true

# Step 3: Install dependencies with pinned Python
echo "📦 Installing dependencies..."
uv sync --python "${PYTHON_VERSION}" --all-extras

# Step 4: Verify API keys in .env
echo "🔑 Verifying API keys..."
if [ ! -f ".env" ]; then
    echo "⚠️  WARNING: .env file not found. Copy from template:"
    echo "   cp .env.template .env"
    echo "   Then fill in your API keys."
fi

if [ -f ".env" ]; then
    required_keys=("GOOGLE_API_KEY" "OPENAI_API_KEY")
    for key in "${required_keys[@]}"; do
        if ! grep -q "^${key}=" .env; then
            echo "⚠️  WARNING: ${key} not found in .env"
        fi
    done
fi

# Step 4: Verify directory structure
echo "📁 Verifying project structure..."
for dir in src/engine src/orchestrator scripts tests benchmarks; do
    if [ -d "$dir" ]; then
        echo "  ✅ $dir"
    else
        echo "  ❌ MISSING: $dir"
    fi
done

# Step 5: Verify .agent structure
echo "✅ Verifying .agent structure..."
for dir in .agent/rules .agent/workflows; do
    if [ -d "$dir" ]; then
        echo "  ✅ $dir"
    else
        echo "  ⚠️  $dir not found (optional)"
    fi
done

echo ""
echo "✅ CrewAI integration complete!"
echo ""
echo "Next steps:"
echo "1. Review src/engine/llm_providers.py for LLM configuration"
echo "2. Review src/engine/crew_agents.py for agent definitions"
echo "3. Review src/engine/crew_orchestrator.py for orchestration logic"
echo "4. Test with: make test-pytest"
echo "5. Run CLI: PYTHONPATH=src uv run python src/orchestrator/antigravity-cli.py --prompt 'test objective'"
echo ""
echo "🚀 System ready for execution!"
