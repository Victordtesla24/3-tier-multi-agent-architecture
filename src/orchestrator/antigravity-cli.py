"""Antigravity CLI — Production Entry Point for the 3-Tier Multi-Agent Architecture.

Usage:
    PYTHONPATH=src python src/orchestrator/antigravity-cli.py \\
        --prompt "<your objective>" \\
        --workspace /path/to/workspace \\
        [--verbose]
"""
import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure src/ is on the module path regardless of invocation CWD
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.semantic_healer import ArchitectureHealer
from engine.state_machine import OrchestrationStateMachine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
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
    parser.add_argument("--verbose", action="store_true", help="Enable verbose CrewAI output")

    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initialising Antigravity Engine | workspace={workspace}")

    print("🌌 Antigravity 3-Tier Multi-Agent Architecture + CrewAI")
    print(f"📁 Workspace : {workspace}")
    print(f"📁 Project   : {PROJECT_ROOT}")
    print(f"🎯 Objective : {args.prompt}\n")

    # Pre-execution: Semantic Auto-Healing — always uses PROJECT_ROOT so the
    # architecture docs and rule templates are reliably available.
    logger.info("Engaging Semantic Healer pre-flight checks…")
    healer = ArchitectureHealer(str(PROJECT_ROOT))
    rules_to_validate = [
        ".agent/rules/l1-orchestration.md",
        ".agent/rules/l2-implementation.md",
        ".agent/rules/l3-leaf-worker.md",
        ".agent/rules/system-verification-agent.md",
    ]
    for rule in rules_to_validate:
        healer.validate_and_heal(rule)

    # Initialise the programmatic state machine back-end
    engine = OrchestrationStateMachine(workspace_dir=str(workspace))

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
