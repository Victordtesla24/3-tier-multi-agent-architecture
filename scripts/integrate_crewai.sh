#!/bin/bash
# CrewAI Integration Script for 3-Tier Architecture

set -e

echo "🌌 Antigravity 3-Tier Architecture - CrewAI Integration"
echo "======================================================="

# Step 1: Clone CrewAI (temporary for reference)
echo "📥 Cloning CrewAI repository..."
if [ -d "/tmp/crewai_reference" ]; then
    sudo rm -rf /tmp/crewai_reference
fi
git clone https://github.com/crewAIInc/crewAI.git /tmp/crewai_reference

# Step 2: Install dependencies
echo "📦 Installing dependencies..."
uv sync
uv add 'crewai[openai]>=0.80.0'
uv add 'crewai[litellm]>=0.80.0'

# Step 3: Verify API keys in .env
echo "🔑 Verifying API keys..."
if [ ! -f ".env" ]; then
    echo "❌ ERROR: .env file not found!"
    exit 1
fi

required_keys=("GOOGLE_API_KEY" "OPENAI_API_KEY")
for key in "${required_keys[@]}"; do
    if ! grep -q "^${key}=" .env; then
        echo "⚠️  WARNING: ${key} not found in .env"
    fi
done

# Step 4: Create new directories
echo "📁 Creating integration directories..."
mkdir -p src/engine
mkdir -p scripts

# Step 5: Verify existing .agent structure
echo "✅ Verifying .agent structure..."
if [ ! -d ".agent/rules" ]; then
    echo "⚠️  WARNING: .agent/rules directory not found"
fi

# Step 6: Remove temporary CrewAI clone
echo "🧹 Cleaning up temporary files..."
sudo rm -rf /tmp/crewai_reference

echo ""
echo "✅ CrewAI integration complete!"
echo ""
echo "Next steps:"
echo "1. Review src/engine/llm_providers.py for LLM configuration"
echo "2. Review src/engine/crew_agents.py for agent definitions"
echo "3. Review src/engine/antigravity_flow.py for flow logic"
echo "4. Test with: uv run python src/orchestrator/antigravity-cli.py --prompt 'test objective'"
echo ""
echo "🚀 System ready for execution!"
