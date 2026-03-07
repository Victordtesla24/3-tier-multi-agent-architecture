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
CREWAI_TOOLS_CHECK=$("${UV_PROJECT_ENVIRONMENT}/bin/python" - 2>&1 <<'PY'
try:
    from crewai_tools import FileReadTool, FileWriterTool  # noqa: F401
    print("ok")
except ImportError as exc:
    print(f"IMPORT_ERROR: {exc}")
except Exception as exc:
    print(f"ERROR: {type(exc).__name__}: {exc}")
PY
)

if echo "$CREWAI_TOOLS_CHECK" | grep -q "^ok"; then
    echo "✅ crewai_tools import check passed"
elif echo "$CREWAI_TOOLS_CHECK" | grep -q "^IMPORT_ERROR"; then
    echo "❌ ERROR: crewai_tools import failed — ${CREWAI_TOOLS_CHECK}"
    echo "   Remediation: Run 'uv add --upgrade crewai-tools' or check installed crewai version."
    echo "   The local workspace tool fallback will be used at runtime, but production tool availability is degraded."
else
    echo "⚠️  WARNING: crewai_tools check returned unexpected output: ${CREWAI_TOOLS_CHECK}"
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
