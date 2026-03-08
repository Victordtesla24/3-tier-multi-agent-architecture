#!/bin/bash
# Antigravity 3-Tier Multi-Agent Architecture — Automated Installer
# Supports: Dynamic multi-provider model selection, secure .env injection,
#           architecture file self-healing, and uv-based dependency installation.

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

NONINTERACTIVE="${ANTIGRAVITY_NONINTERACTIVE:-}"

declare -a MODEL_CATALOG=()
declare -a SELECTED_NOTES=()

_parse_model_field() {
    local entry="$1"
    local field="$2"
    echo "$entry" | cut -d'|' -f"$field" | xargs
}

_load_model_catalog() {
    MODEL_CATALOG=()
    while IFS= read -r line; do
        [ -n "$line" ] && MODEL_CATALOG+=("$line")
    done < <(
        PYTHONPATH=src python3 - <<'PY'
from engine.model_catalog import catalog_rows

for row in catalog_rows():
    print(
        "|".join(
            [
                str(row["display_label"]),
                str(row["logical_id"]),
                str(row["crewai_model"]),
                str(row["provider_group"]),
                str(row["api_key_env"]),
                str(row["base_url_env"]),
                str(row["default_base_url"]),
                str(row["requested_thinking"]),
                str(row["runtime_reasoning_effort"]),
                str(row["requested_temperature"]),
            ]
        )
    )
PY
    )

    if [ "${#MODEL_CATALOG[@]}" -eq 0 ]; then
        echo -e "${RED}❌  Failed to load the model catalog from src/engine/model_catalog.py.${NC}"
        exit 1
    fi
}

_load_default_tiers() {
    while IFS='|' read -r tier logical_id label; do
        case "$tier" in
            level1)
                DEFAULT_LEVEL1_MODEL="$logical_id"
                DEFAULT_LEVEL1_LABEL="$label"
                ;;
            level2)
                DEFAULT_LEVEL2_MODEL="$logical_id"
                DEFAULT_LEVEL2_LABEL="$label"
                ;;
            level3)
                DEFAULT_LEVEL3_MODEL="$logical_id"
                DEFAULT_LEVEL3_LABEL="$label"
                ;;
        esac
    done < <(
        PYTHONPATH=src python3 - <<'PY'
from engine.model_catalog import (
    DEFAULT_LEVEL1_MODEL,
    DEFAULT_LEVEL2_MODEL,
    DEFAULT_LEVEL3_MODEL,
    get_model_entry,
)

print(f"level1|{DEFAULT_LEVEL1_MODEL}|{get_model_entry(DEFAULT_LEVEL1_MODEL).display_label}")
print(f"level2|{DEFAULT_LEVEL2_MODEL}|{get_model_entry(DEFAULT_LEVEL2_MODEL).display_label}")
print(f"level3|{DEFAULT_LEVEL3_MODEL}|{get_model_entry(DEFAULT_LEVEL3_MODEL).display_label}")
PY
    )
}

_load_selected_notes() {
    local logical_id="$1"
    SELECTED_NOTES=()
    while IFS= read -r line; do
        [ -n "$line" ] && SELECTED_NOTES+=("$line")
    done < <(
        PYTHONPATH=src python3 - "$logical_id" <<'PY'
import sys
from engine.model_catalog import default_runtime_notes

for note in default_runtime_notes(sys.argv[1]):
    print(note)
PY
    )
}

_find_selection_by_model_id() {
    local model_id="$1"
    local i
    for i in "${!MODEL_CATALOG[@]}"; do
        if [ "$(_parse_model_field "${MODEL_CATALOG[$i]}" 2)" = "$model_id" ]; then
            echo $((i + 1))
            return 0
        fi
    done
    return 1
}

_print_catalog_menu() {
    local current_group=""
    local i entry group label
    echo -e "  ${BOLD}Select your Primary Orchestration LLM:${NC}"
    for i in "${!MODEL_CATALOG[@]}"; do
        entry="${MODEL_CATALOG[$i]}"
        group="$(_parse_model_field "$entry" 4)"
        label="$(_parse_model_field "$entry" 1)"
        if [ "$group" != "$current_group" ]; then
            [ -n "$current_group" ] && echo ""
            echo -e "  ${CYAN}── ${group} ───────────────────────────────────────────────${NC}"
            current_group="$group"
        fi
        echo -e "    ${BOLD}[$((i + 1))]${NC} ${label}"
    done
    echo ""
    echo -e "  ${CYAN}──────────────────────────────────────────────────────────${NC}"
}

_set_env_var() {
    local key="$1"
    local value="$2"
    local file=".env"
    sed -i.bak "/^${key}[[:space:]]*=/d" "$file" && rm -f "${file}.bak"
    if [ -s "$file" ]; then
        python3 - "$file" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
data = path.read_bytes()
if data and not data.endswith(b"\n"):
    path.write_bytes(data + b"\n")
PY
    fi
    printf '%s="%s"\n' "$key" "$value" >> "$file"
}

_get_env_var() {
    local key="$1"
    python3 - "$key" <<'PY'
import sys
from pathlib import Path

path = Path(".env")
if not path.exists():
    sys.exit(0)

for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    current_key, value = line.split("=", maxsplit=1)
    if current_key.strip() == sys.argv[1]:
        print(value.strip().strip('"').strip("'"))
        break
PY
}

_apply_active_matrix_defaults() {
    local selected_model_id="$1"
    while IFS='|' read -r key value; do
        [ -z "$key" ] && continue
        case "$key" in
            PRIMARY_LLM|ORCHESTRATION_MODEL|L1_MODEL|L2_MODEL|L3_MODEL|L2_AGENT_SWARMS|L3_AGENT_SWARMS)
                _set_env_var "$key" "$value"
                ;;
            *)
                if ! grep -q "^${key}=" ".env" 2>/dev/null; then
                    _set_env_var "$key" "$value"
                fi
                ;;
        esac
    done < <(
        PYTHONPATH=src python3 - "$selected_model_id" <<'PY'
import sys
from engine.model_catalog import active_matrix_env_defaults

for key, value in active_matrix_env_defaults(sys.argv[1]):
    print(f"{key}|{value}")
PY
    )
}

echo -e "${BLUE}${BOLD}========================================================${NC}"
echo -e "${BLUE}${BOLD}  🌌 Antigravity 3-Tier Multi-Agent — Installer v2.0   ${NC}"
echo -e "${BLUE}${BOLD}========================================================${NC}"
echo ""

echo -e "${YELLOW}${BOLD}[1/5] Detecting Antigravity IDE Environment...${NC}"
GEMINI_DIR="$HOME/.gemini"
if [ ! -d "$GEMINI_DIR" ]; then
    echo -e "${RED}❌  Error: Antigravity IDE not detected (missing ~/.gemini).${NC}"
    echo -e "    Please ensure the Antigravity IDE is installed and has been launched"
    echo -e "    at least once on this machine."
    exit 1
fi
echo -e "${GREEN}✅  Antigravity IDE configuration directory found: ${GEMINI_DIR}${NC}"
echo ""

echo -e "${YELLOW}${BOLD}[2/5] Verifying Architecture Integrity (Self-Healing Check)...${NC}"
mkdir -p .agent/rules .agent/workflows .agent/tmp .agent/memory docs/architecture

declare -a CORE_FILES=(
    ".agent/rules/system-verification-agent.md"
    ".agent/rules/internet-research-agent.md"
    ".agent/rules/l1-orchestration.md"
    ".agent/rules/l2-sub-agent.md"
    ".agent/rules/l3-leaf-worker.md"
    ".agent/rules/continuous-learning-agent.md"
    ".agent/workflows/3-tier-orchestration.md"
    "docs/architecture/multi-agent-3-level-architecture.md"
    "docs/architecture/prompt-reconstruction.md"
)

MISSING_FILES=0
for file in "${CORE_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}  ⚠️  Missing: $file${NC}"
        MISSING_FILES=$((MISSING_FILES + 1))
    fi
done

if [ "$MISSING_FILES" -gt 0 ]; then
    echo -e "${YELLOW}  🔄 Self-Healing: Restoring ${MISSING_FILES} missing file(s) from git...${NC}"
    git checkout HEAD -- .agent/ docs/ 2>/dev/null || {
        echo -e "${RED}❌  Critical: Cannot restore files. Ensure you are inside the cloned repo.${NC}"
        exit 1
    }
    echo -e "${GREEN}✅  Missing files restored successfully.${NC}"
else
    echo -e "${GREEN}✅  All architecture files verified.${NC}"
fi
echo ""

echo -e "${YELLOW}${BOLD}[3/5] Primary LLM Configuration${NC}"
echo ""

_load_model_catalog
_load_default_tiers
TOTAL_MODELS=${#MODEL_CATALOG[@]}

if [ -n "$NONINTERACTIVE" ]; then
    if [ -n "${ANTIGRAVITY_MODEL_ID:-}" ]; then
        SELECTION="$(_find_selection_by_model_id "${ANTIGRAVITY_MODEL_ID}")" || {
            echo -e "${RED}❌  Unknown ANTIGRAVITY_MODEL_ID='${ANTIGRAVITY_MODEL_ID}'.${NC}"
            exit 1
        }
        echo -e "${CYAN}  ℹ  Non-interactive mode: resolved ANTIGRAVITY_MODEL_ID=${ANTIGRAVITY_MODEL_ID}.${NC}"
    else
        SELECTION="${ANTIGRAVITY_MODEL_SELECTION:-1}"
        echo -e "${CYAN}  ℹ  Non-interactive mode: using pre-set selection ${SELECTION}.${NC}"
    fi
else
    _print_catalog_menu
    SELECTION=""
    while true; do
        printf "  Enter selection [1-%d]: " "$TOTAL_MODELS"
        read -r SELECTION 2>/dev/null || SELECTION="1"
        if [[ "$SELECTION" =~ ^[0-9]+$ ]] && [ "$SELECTION" -ge 1 ] && [ "$SELECTION" -le "$TOTAL_MODELS" ]; then
            break
        fi
        echo -e "  ${RED}Invalid selection. Please enter a number between 1 and ${TOTAL_MODELS}.${NC}"
    done
fi

if ! [[ "$SELECTION" =~ ^[0-9]+$ ]] || [ "$SELECTION" -lt 1 ] || [ "$SELECTION" -gt "$TOTAL_MODELS" ]; then
    echo -e "${RED}❌  Invalid model selection '${SELECTION}'.${NC}"
    exit 1
fi

SELECTED_ENTRY="${MODEL_CATALOG[$((SELECTION - 1))]}"
SELECTED_LABEL="$(_parse_model_field "$SELECTED_ENTRY" 1)"
SELECTED_MODEL="$(_parse_model_field "$SELECTED_ENTRY" 2)"
SELECTED_RUNTIME_MODEL="$(_parse_model_field "$SELECTED_ENTRY" 3)"
SELECTED_PROVIDER_GROUP="$(_parse_model_field "$SELECTED_ENTRY" 4)"
SELECTED_KEY_VAR="$(_parse_model_field "$SELECTED_ENTRY" 5)"
SELECTED_BASE_URL_VAR="$(_parse_model_field "$SELECTED_ENTRY" 6)"
SELECTED_DEFAULT_BASE_URL="$(_parse_model_field "$SELECTED_ENTRY" 7)"
SELECTED_REQUESTED_THINKING="$(_parse_model_field "$SELECTED_ENTRY" 8)"
SELECTED_RUNTIME_REASONING="$(_parse_model_field "$SELECTED_ENTRY" 9)"
SELECTED_REQUESTED_TEMPERATURE="$(_parse_model_field "$SELECTED_ENTRY" 10)"
_load_selected_notes "$SELECTED_MODEL"

echo ""
echo -e "  ${GREEN}✅  Selected: ${BOLD}${SELECTED_LABEL}${NC}"
echo -e "      Logical ID     : ${CYAN}${SELECTED_MODEL}${NC}"
echo -e "      Runtime Model  : ${CYAN}${SELECTED_RUNTIME_MODEL}${NC}"
echo -e "      Provider Group : ${CYAN}${SELECTED_PROVIDER_GROUP}${NC}"
[ -n "$SELECTED_KEY_VAR" ] && echo -e "      Key Var        : ${CYAN}${SELECTED_KEY_VAR}${NC}"
[ -z "$SELECTED_KEY_VAR" ] && echo -e "      Key Var        : ${CYAN}not required${NC}"
[ -n "$SELECTED_BASE_URL_VAR" ] && echo -e "      Base URL Var   : ${CYAN}${SELECTED_BASE_URL_VAR}${NC}"
echo ""

CAPTURED_API_KEY=""
if [ -n "$SELECTED_KEY_VAR" ]; then
    if [ -n "$NONINTERACTIVE" ]; then
        CAPTURED_API_KEY="${ANTIGRAVITY_API_KEY:-}"
        if [ -z "$CAPTURED_API_KEY" ]; then
            echo -e "${RED}❌  Non-interactive mode requires ANTIGRAVITY_API_KEY to be set.${NC}"
            exit 1
        fi
        echo -e "${CYAN}  ℹ  Non-interactive mode: API key read from ANTIGRAVITY_API_KEY env var.${NC}"
    else
        echo -e "  ${BOLD}Enter your ${SELECTED_KEY_VAR}:${NC}"
        printf "  > "
        read -rs CAPTURED_API_KEY 2>/dev/null || CAPTURED_API_KEY=""
        echo ""

        if [ -z "$CAPTURED_API_KEY" ]; then
            echo -e "  ${RED}❌  API key cannot be empty. Installation aborted.${NC}"
            exit 1
        fi
    fi

    echo -e "  ${GREEN}✅  API key captured (${#CAPTURED_API_KEY} characters).${NC}"
else
    echo -e "  ${GREEN}✅  No API key required for the selected provider.${NC}"
fi
echo ""

echo -e "${YELLOW}${BOLD}[4/5] Injecting Configuration into .env...${NC}"

if [ ! -f ".env" ]; then
    if [ -f ".env.template" ]; then
        cp ".env.template" ".env"
        echo -e "  ${CYAN}ℹ  Created .env from .env.template${NC}"
    else
        touch ".env"
        echo -e "  ${CYAN}ℹ  Created blank .env${NC}"
    fi
fi

_set_env_var "PRIMARY_LLM" "$SELECTED_MODEL"
_set_env_var "ORCHESTRATION_MODEL" "$SELECTED_MODEL"
if [ -n "$SELECTED_KEY_VAR" ]; then
    _set_env_var "$SELECTED_KEY_VAR" "$CAPTURED_API_KEY"
fi
if [ -n "$SELECTED_BASE_URL_VAR" ] && [ -n "$SELECTED_DEFAULT_BASE_URL" ]; then
    _set_env_var "$SELECTED_BASE_URL_VAR" "$SELECTED_DEFAULT_BASE_URL"
fi
_apply_active_matrix_defaults "$SELECTED_MODEL"

echo -e "  ${GREEN}✅  PRIMARY_LLM=${SELECTED_MODEL}${NC}"
echo -e "  ${GREEN}✅  ORCHESTRATION_MODEL=${SELECTED_MODEL}${NC}"
if [ -n "$SELECTED_KEY_VAR" ]; then
    echo -e "  ${GREEN}✅  ${SELECTED_KEY_VAR} written to .env${NC}"
fi
if [ -n "$SELECTED_BASE_URL_VAR" ] && [ -n "$SELECTED_DEFAULT_BASE_URL" ]; then
    echo -e "  ${GREEN}✅  ${SELECTED_BASE_URL_VAR}=${SELECTED_DEFAULT_BASE_URL}${NC}"
fi
echo ""

WRITTEN_MODEL=$(grep -E "^PRIMARY_LLM=" .env | head -1 | cut -d'"' -f2)
if [ "$WRITTEN_MODEL" != "$SELECTED_MODEL" ]; then
    echo -e "${RED}❌  Verification failed: PRIMARY_LLM in .env ('${WRITTEN_MODEL}') does not match expected '${SELECTED_MODEL}'.${NC}"
    exit 1
fi
WRITTEN_ORCHESTRATION_MODEL=$(grep -E "^ORCHESTRATION_MODEL=" .env | head -1 | cut -d'"' -f2)
if [ "$WRITTEN_ORCHESTRATION_MODEL" != "$SELECTED_MODEL" ]; then
    echo -e "${RED}❌  Verification failed: ORCHESTRATION_MODEL in .env ('${WRITTEN_ORCHESTRATION_MODEL}') does not match expected '${SELECTED_MODEL}'.${NC}"
    exit 1
fi
if [ -n "$SELECTED_KEY_VAR" ]; then
    if ! grep -q "^${SELECTED_KEY_VAR}=" .env 2>/dev/null; then
        echo -e "${RED}❌  Verification failed: ${SELECTED_KEY_VAR} was not written to .env.${NC}"
        exit 1
    fi
fi
if [ -n "$SELECTED_BASE_URL_VAR" ] && [ -n "$SELECTED_DEFAULT_BASE_URL" ]; then
    WRITTEN_BASE_URL=$(grep -E "^${SELECTED_BASE_URL_VAR}=" .env | head -1 | cut -d'"' -f2)
    if [ "$WRITTEN_BASE_URL" != "$SELECTED_DEFAULT_BASE_URL" ]; then
        echo -e "${RED}❌  Verification failed: ${SELECTED_BASE_URL_VAR} in .env ('${WRITTEN_BASE_URL}') does not match expected '${SELECTED_DEFAULT_BASE_URL}'.${NC}"
        exit 1
    fi
fi
echo -e "  ${GREEN}✅  .env verification passed (PRIMARY_LLM=${WRITTEN_MODEL}).${NC}"
echo ""

echo -e "${YELLOW}${BOLD}[5/5] Installing Dependencies & Registering with Antigravity Engine...${NC}"

if [ -z "$NONINTERACTIVE" ]; then
    printf "  ⚠️  This will modify your system configuration at %s. Proceed? [y/N] " "$GEMINI_DIR"
    read -r response 2>/dev/null || response="n"
    if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${RED}  Installation aborted by user.${NC}"
        exit 0
    fi
fi

GEMINI_CONF="$GEMINI_DIR/GEMINI.md"
if [ ! -f "$GEMINI_CONF" ]; then
    touch "$GEMINI_CONF"
else
    BACKUP_PATH="${GEMINI_CONF}.backup.$(date +%s)"
    cp "$GEMINI_CONF" "$BACKUP_PATH"
    echo -e "  ${GREEN}✅  Config backup: ${BACKUP_PATH}${NC}"
fi

if ! command -v uv >/dev/null 2>&1; then
    echo -e "  ${CYAN}ℹ  Installing uv package manager...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh -q || {
        echo -e "  ${RED}⚠️  uv installation failed. Continuing with caution.${NC}"
    }
fi
export PATH="$HOME/.cargo/bin:$PATH"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$(pwd)/.venv}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"

echo -e "  ${CYAN}ℹ  Syncing Python dependencies (uv sync)...${NC}"
env -u VIRTUAL_ENV uv sync --all-extras --python 3.12 -q || {
    echo -e "  ${RED}❌  uv sync failed. Installation cannot continue.${NC}"
    exit 1
}

VENV_PYTHON="${UV_PROJECT_ENVIRONMENT}/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo -e "  ${RED}❌  Expected interpreter not found at ${VENV_PYTHON}.${NC}"
    echo -e "     Verify uv created the project virtualenv successfully."
    exit 1
fi

"$VENV_PYTHON" src/engine/config_manager.py "$GEMINI_CONF" "$SELECTED_LABEL"

echo -e "  ${GREEN}✅  Dependencies installed and engine registered.${NC}"
echo ""

echo -e "${GREEN}${BOLD}======================================================================${NC}"
echo -e "${GREEN}${BOLD}🚀 INSTALLATION COMPLETE — Antigravity 3-Tier Architecture is LIVE${NC}"
echo -e "${GREEN}${BOLD}======================================================================${NC}"
echo ""
EFFECTIVE_ORCHESTRATION_MODEL="$(_get_env_var "ORCHESTRATION_MODEL")"
EFFECTIVE_L1_MODEL="$(_get_env_var "L1_MODEL")"
EFFECTIVE_L2_MODEL="$(_get_env_var "L2_MODEL")"
EFFECTIVE_L3_MODEL="$(_get_env_var "L3_MODEL")"
EFFECTIVE_L2_SWARMS="$(_get_env_var "L2_AGENT_SWARMS")"
EFFECTIVE_L3_SWARMS="$(_get_env_var "L3_AGENT_SWARMS")"
echo -e "  ${BOLD}Configuration Summary:${NC}"
echo -e "    Orchestration Primary : ${CYAN}${SELECTED_LABEL}${NC}"
echo -e "    Primary Logical ID    : ${CYAN}${SELECTED_MODEL}${NC}"
echo -e "    Runtime Model         : ${CYAN}${SELECTED_RUNTIME_MODEL}${NC}"
echo -e "    Orchestration Env     : ${CYAN}${EFFECTIVE_ORCHESTRATION_MODEL}${NC}"
echo -e "    Level1 Effective      : ${CYAN}${EFFECTIVE_L1_MODEL:-${DEFAULT_LEVEL1_MODEL}}${NC}"
echo -e "    Level2 Effective      : ${CYAN}${EFFECTIVE_L2_MODEL:-${DEFAULT_LEVEL2_MODEL}}${NC}"
echo -e "    Level3 Effective      : ${CYAN}${EFFECTIVE_L3_MODEL:-${DEFAULT_LEVEL3_MODEL}}${NC}"
echo -e "    L2 Agent Swarms       : ${CYAN}${EFFECTIVE_L2_SWARMS:-2}${NC}"
echo -e "    L3 Agent Swarms       : ${CYAN}${EFFECTIVE_L3_SWARMS:-3}${NC}"
echo -e "    API Key Var           : ${CYAN}${SELECTED_KEY_VAR}${NC}"
echo -e "    .env file             : ${CYAN}$(pwd)/.env${NC}"
echo -e "    Python env            : ${CYAN}${UV_PROJECT_ENVIRONMENT}${NC}"
if [ "${#SELECTED_NOTES[@]}" -gt 0 ]; then
    echo ""
    echo -e "  ${BOLD}Runtime Normalization:${NC}"
    for note in "${SELECTED_NOTES[@]}"; do
        echo -e "    - ${note}"
    done
fi
echo ""
echo -e "  ${BOLD}Next Steps:${NC}"
echo -e "    1. Activate the venv   : ${CYAN}source ${UV_PROJECT_ENVIRONMENT}/bin/activate${NC}"
echo -e "    2. Run the test suite  : ${CYAN}make test-pytest${NC}"
echo -e "    3. Run the CLI         : ${CYAN}make run-cli${NC}"
echo -e "    4. Open Antigravity IDE and start a new chat."
echo -e "       You should see: ${BLUE}3-tier-multi-agent-architecture Status: ON 🟢${NC}"
echo ""
echo -e "${GREEN}${BOLD}======================================================================${NC}"
