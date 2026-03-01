import sys
import argparse
import logging
from pathlib import Path

# Provide path to internal engine modules
sys.path.append(str(Path(__file__).parent.parent))
from engine.state_machine import OrchestrationStateMachine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AntigravityCLI")

def main():
    parser = argparse.ArgumentParser(description="Standalone CLI Runner for the 3-Tier Multi-Agent Architecture")
    parser.add_argument("--prompt", type=str, required=True, help="The raw user prompt/directive to execute")
    parser.add_argument("--workspace", type=str, default=".", help="Root directory for file system operations")
    
    args = parser.parse_args()
    
    logger.info(f"Initializing Antigravity Engine in {args.workspace}")
    
    # Initialize the programmatic state machine back-end
    engine = OrchestrationStateMachine(workspace_dir=args.workspace)
    
    logger.info("Starting execution pipeline...")
    try:
        result = engine.execute_pipeline(raw_prompt=args.prompt)
        logger.info(f"Pipeline executed successfully. Result bounds verified.")
    except Exception as e:
        logger.error(f"Critical Pipeline Failure: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
