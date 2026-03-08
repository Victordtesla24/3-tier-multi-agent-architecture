#!/bin/bash
# CrewAI Integration Script for 3-Tier Architecture

set -euo pipefail

echo "🌌 Antigravity 3-Tier Architecture - CrewAI Integration"
echo "======================================================="

# Step 1: Install dependencies (Using /tmp caches to bypass macOS Sandbox permission errors)
echo "📦 Installing dependencies..."
export UV_PROJECT_ENVIRONMENT=${UV_PROJECT_ENVIRONMENT:-"$(pwd)/.venv"}
export UV_CACHE_DIR=${UV_CACHE_DIR:-/tmp/uv-cache}
env -u VIRTUAL_ENV uv sync --all-extras --python 3.12
PYTHON_BIN="${UV_PROJECT_ENVIRONMENT}/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "❌ ERROR: Expected interpreter not found at $PYTHON_BIN"
    echo "   Remediation: rerun 'uv sync --all-extras --python 3.12' and verify the project virtualenv exists."
    exit 1
fi

# Step 2: Verify API keys in .env
echo "🔑 Verifying API keys..."
if [ ! -f ".env" ]; then
    echo "❌ ERROR: .env file not found! Please copy .env.template to .env and fill in your API keys."
    exit 1
fi

PRIMARY_LLM=$(grep -E '^PRIMARY_LLM=' .env | head -1 | cut -d'=' -f2- | tr -d '"' | xargs)
if [ -z "$PRIMARY_LLM" ]; then
    PRIMARY_LLM="openai/gpt-5.4"
fi

declare -a REQUIRED_KEYS=()
declare -a RUNTIME_WARNINGS=()
while IFS= read -r key; do
    [ -n "$key" ] && REQUIRED_KEYS+=("$key")
done < <(
    PYTHONPATH=src "$PYTHON_BIN" - "$PRIMARY_LLM" <<'PY'
import sys
from engine.runtime_env import resolve_runtime_env

runtime_env = resolve_runtime_env(".", project_root=".", primary_model_id_override=sys.argv[1])
for key in runtime_env.active_provider_env_keys:
    print(key)
print("---WARNINGS---")
for warning in runtime_env.warnings:
    print(warning)
PY
)

if [ "${#REQUIRED_KEYS[@]}" -gt 0 ]; then
    LAST_INDEX=$((${#REQUIRED_KEYS[@]} - 1))
    if [ "${REQUIRED_KEYS[$LAST_INDEX]}" = "---WARNINGS---" ]; then
        unset 'REQUIRED_KEYS[$LAST_INDEX]'
    else
        for i in "${!REQUIRED_KEYS[@]}"; do
            if [ "${REQUIRED_KEYS[$i]}" = "---WARNINGS---" ]; then
                RUNTIME_WARNINGS=("${REQUIRED_KEYS[@]:$((i + 1))}")
                REQUIRED_KEYS=("${REQUIRED_KEYS[@]:0:$i}")
                break
            fi
        done
    fi
fi

for warning in "${RUNTIME_WARNINGS[@]}"; do
    echo "⚠️  WARNING: ${warning}"
done

for key in "${REQUIRED_KEYS[@]}"; do
    if ! grep -q "^${key}=" .env; then
        echo "⚠️  WARNING: ${key} not found in .env"
    else
        value=$(grep "^${key}=" .env | cut -d'=' -f2- | tr -d '"' | xargs)
        if [ "$value" = "your_google_api_key_here" ] \
            || [ "$value" = "your_deepseek_api_key_here" ] \
            || [ "$value" = "your_deepseek_base_url_here" ] \
            || [ "$value" = "your_openai_api_key_here" ] \
            || [ "$value" = "your_ollama_base_url_here" ]; then
            echo "⚠️  WARNING: ${key} is still set to the template placeholder value"
        fi
    fi
done

echo "🧪 Validating toolchain compatibility..."
CREWAI_TOOLS_CHECK=$("$PYTHON_BIN" - 2>&1 <<'PY'
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
