#!/bin/bash
# CrewAI Integration Script for 3-Tier Architecture

set -euo pipefail

echo "🌌 Antigravity 3-Tier Architecture - CrewAI Integration"
echo "======================================================="

# Step 1: Install dependencies (Using /tmp caches to bypass macOS Sandbox permission errors)
echo "📦 Installing dependencies..."
export UV_PROJECT_ENVIRONMENT=${UV_PROJECT_ENVIRONMENT:-/tmp/.venv-antigravity}
export UV_CACHE_DIR=${UV_CACHE_DIR:-/tmp/uv-cache}
env -u VIRTUAL_ENV uv sync --all-extras --python 3.12

# Step 2: Verify API keys in .env
echo "🔑 Verifying API keys..."
if [ ! -f ".env" ]; then
    echo "❌ ERROR: .env file not found! Please copy .env.template to .env and fill in your API keys."
    exit 1
fi

required_keys=("GOOGLE_API_KEY" "OPENAI_API_KEY" "MINIMAX_API_KEY" "DEEPSEEK_API_KEY" "MINIMAX_BASE_URL" "DEEPSEEK_BASE_URL")
for key in "${required_keys[@]}"; do
    if ! grep -q "^${key}=" .env; then
        echo "⚠️  WARNING: ${key} not found in .env"
    else
        value=$(grep "^${key}=" .env | cut -d'=' -f2)
        if [ "$value" = "your_google_api_key_here" ] || [ "$value" = "your_openai_api_key_here" ]; then
            echo "⚠️  WARNING: ${key} is still set to the template placeholder value"
        fi
    fi
done

echo "🧪 Validating toolchain compatibility..."
if ! "${UV_PROJECT_ENVIRONMENT}/bin/python" - <<'PY'
try:
    from crewai_tools import FileReadTool, FileWriterTool  # noqa: F401
    print("crewai_tools import check passed")
except Exception as exc:
    print(f"crewai_tools import check failed: {type(exc).__name__}: {exc}")
    raise SystemExit(1)
PY
then
    echo "⚠️  WARNING: crewai_tools import failed. Local workspace tool fallback will be used at runtime."
fi

# Step 3: Verify directory structure
echo "📁 Verifying integration directories..."
mkdir -p src/engine
mkdir -p scripts
mkdir -p .agent/rules .agent/workflows .agent/tmp .agent/memory

# Step 4: Verify .agent structure
echo "✅ Verifying .agent structure..."
if [ ! -d ".agent/rules" ]; then
    echo "⚠️  WARNING: .agent/rules directory not found"
fi

echo ""
echo "✅ CrewAI integration complete!"
echo ""
echo "Next steps:"
echo "1. Review src/engine/llm_config.py for provider policy + validation"
echo "2. Review src/engine/crew_orchestrator.py for telemetry and tool fallback logic"
echo "3. Review src/engine/state_machine.py for retry and reliability gates"
echo "4. Test with: make run-cli"
echo ""
echo "🚀 System ready for execution!"
