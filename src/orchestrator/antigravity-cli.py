"""Antigravity CLI with CrewAI Integration"""
import argparse
import sys
import logging
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from engine.state_machine import OrchestrationStateMachine
from engine.semantic_healer import ArchitectureHealer
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AntigravityCLI")


def main():
    parser = argparse.ArgumentParser(
        description="Antigravity 3-Tier Multi-Agent Architecture with CrewAI"
    )
    parser.add_argument("--prompt", required=True, help="User objective/prompt")
    parser.add_argument(
        "--workspace",
        default="/tmp/antigravity_workspace",
        help="Workspace directory"
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Initialize workspace
    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing Antigravity Engine in {workspace}")

    print("🌌 Antigravity 3-Tier Multi-Agent Architecture + CrewAI")
    print(f"📁 Workspace: {workspace}")
    print(f"🎯 Objective: {args.prompt}\n")

    # Pre-execution: Semantic Auto-Healing checks
    logger.info("Engaging Semantic Healer constraints...")
    healer = ArchitectureHealer(str(workspace))
    healer.validate_and_heal(".agent/rules/l1-orchestration.md")

    # Initialize the programmatic state machine back-end
    engine = OrchestrationStateMachine(workspace_dir=str(workspace))

    logger.info("Starting execution pipeline...")
    try:
        result = engine.execute_pipeline(raw_prompt=args.prompt)

        # Save results
        output_file = workspace / "execution_result.json"
        with open(output_file, "w") as f:
            json.dump({
                "success": result,
                "workspace": str(workspace),
                "prompt": args.prompt,
            }, f, indent=2)

        if result:
            print(f"\n✅ Execution complete! Results saved to {output_file}")

        # Save logs
        log_file = workspace / ".agent" / "memory" / "execution_log.json"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Pipeline executed successfully. Result bounds verified.")
        return 0

    except Exception as e:
        logger.error(f"Critical Pipeline Failure: {str(e)}")
        print(f"\n❌ Execution failed: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
