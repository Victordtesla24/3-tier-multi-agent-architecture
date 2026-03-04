"""Antigravity CLI — Production Entry Point for the 3-Tier Multi-Agent Architecture.

Usage:
    PYTHONPATH=src python src/orchestrator/antigravity-cli.py \\
        --prompt "<your objective>" \\
        --workspace /path/to/workspace \\
        [--verbose]
"""
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# CrewAI storage redirect — MUST execute before any crewai import.
# CrewAI's db_storage_path() runs at class-definition time and calls
# appdirs.user_data_dir() which on macOS resolves to
# ~/Library/Application Support/. On restricted filesystems, mkdir there
# fails with PermissionError. We redirect all storage to a writable path.
# ---------------------------------------------------------------------------
_CREWAI_STORAGE = os.environ.get(
    "CREWAI_STORAGE_DIR", "/tmp/crewai_cli_storage"
)
os.makedirs(_CREWAI_STORAGE, exist_ok=True)
os.environ.setdefault("CREWAI_STORAGE_DIR", _CREWAI_STORAGE)
os.environ.setdefault("CREWAI_HOME", _CREWAI_STORAGE)

try:
    import appdirs as _appdirs

    _orig_user_data_dir = _appdirs.user_data_dir

    def _patched_user_data_dir(appname=None, appauthor=None, version=None, roaming=False):
        base = os.path.join(_CREWAI_STORAGE, "appdirs_data")
        if appname:
            base = os.path.join(base, appname)
        os.makedirs(base, exist_ok=True)
        return base

    _appdirs.user_data_dir = _patched_user_data_dir
except ImportError:
    pass

# Patch pathlib.Path.is_file to bypass macOS Sandbox PermissionError 
# triggered by Pydantic's BaseSettings looking for .env in restricted directories.
_orig_is_file = Path.is_file
def _patched_is_file(self):
    try:
        return _orig_is_file(self)
    except PermissionError:
        return False
Path.is_file = _patched_is_file
# ---------------------------------------------------------------------------

import argparse
import json
import logging

# Ensure src/ is on the module path regardless of invocation CWD
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.llm_config import EnvConfigError, load_workspace_env, validate_provider_runtime_env
from engine.logging_utils import install_log_redaction
from engine.semantic_healer import ArchitectureHealer
from engine.status_banner import emit_status_banner
from engine.state_machine import OrchestrationStateMachine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
install_log_redaction()
# Prevent noisy duplicate tracer-provider warnings from third-party libs.
logging.getLogger("opentelemetry.trace").setLevel(logging.ERROR)
logger = logging.getLogger("AntigravityCLI")

# Project root is always two levels up from this file (src/orchestrator/ → project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Antigravity 3-Tier Multi-Agent Architecture with CrewAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--prompt", required=True, help="User objective / prompt")
    parser.add_argument(
        "--workspace",
        default="/tmp/antigravity_workspace",
        help="Working directory for pipeline artefacts (default: /tmp/antigravity_workspace)",
    )
    parser.add_argument(
        "--strict-provider-validation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail fast if provider credentials/base URLs are missing or placeholder values.",
    )
    parser.add_argument(
        "--max-provider-4xx",
        type=int,
        default=50,
        help="Maximum tolerated provider HTTP 4xx events before pipeline abort.",
    )
    parser.add_argument(
        "--fail-on-research-empty",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Fail pipeline if research stage returns fewer than two citations for non-trivial prompts.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose CrewAI output")

    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    emit_status_banner()
    print("3-tier-multi-agent-architecture Status: ON 🟢")
    print("🌌 Antigravity 3-Tier Multi-Agent Architecture + CrewAI")
    print(f"📁 Workspace : {workspace}")
    print(f"📁 Project   : {PROJECT_ROOT}")
    print(f"🎯 Objective : {args.prompt}\n")

    logger.info(f"Initialising Antigravity Engine | workspace={workspace}")

    if args.strict_provider_validation:
        try:
            load_workspace_env(workspace, project_root=PROJECT_ROOT)
            validate_provider_runtime_env(strict=True)
        except EnvConfigError as exc:
            logger.error(f"Provider preflight failed: {exc}")
            print(f"\n❌ Execution failed: {exc}")
            return 1

    # Pre-execution: Semantic Auto-Healing — always uses PROJECT_ROOT so the
    # architecture docs and rule templates are reliably available.
    logger.info("Engaging Semantic Healer pre-flight checks…")
    healer = ArchitectureHealer(str(PROJECT_ROOT))
    rules_to_validate = [
        ".agent/rules/l1-orchestration.md",
        ".agent/rules/l2-sub-agent.md",
        ".agent/rules/l3-leaf-worker.md",
        ".agent/rules/system-verification-agent.md",
    ]
    for rule in rules_to_validate:
        healer.validate_and_heal(rule)

    # Initialise the programmatic state machine back-end
    engine = OrchestrationStateMachine(
        workspace_dir=str(workspace),
        strict_provider_validation=args.strict_provider_validation,
        max_provider_4xx=args.max_provider_4xx,
        fail_on_research_empty=args.fail_on_research_empty,
    )

    logger.info("Starting execution pipeline…")
    try:
        success = engine.execute_pipeline(raw_prompt=args.prompt)

        output_file = workspace / "execution_result.json"
        output_file.write_text(
            json.dumps(
                {
                    "success": success,
                    "workspace": str(workspace),
                    "prompt": args.prompt,
                    "strict_provider_validation": args.strict_provider_validation,
                    "max_provider_4xx": args.max_provider_4xx,
                    "fail_on_research_empty": args.fail_on_research_empty,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        if success:
            print(f"\n✅ Execution complete! Results saved to {output_file}")
        else:
            print(f"\n⚠️  Execution completed with verification failures. See {output_file}")

        logger.info("Pipeline execution finished.")
        return 0 if success else 1

    except Exception as exc:
        logger.error(f"Critical pipeline failure: {exc}", exc_info=True)
        print(f"\n❌ Execution failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
