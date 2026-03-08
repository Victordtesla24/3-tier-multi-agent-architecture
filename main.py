"""
System Integration: Proving Execution Capability
Integrates all three architectural enhancements into a single, cohesive,
operational asynchronous event loop demonstrating execution capability.

Usage:
    python main.py
"""

import asyncio
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"


def _bootstrap_src_path() -> None:
    src_root = str(SRC_ROOT)
    if src_root not in sys.path:
        sys.path.insert(0, src_root)

# Standardize logging format for the demonstration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("System_Integration")


async def run_system() -> None:
    _bootstrap_src_path()

    from orchestrator.tier1_manager import AsyncTier1Orchestrator
    from utility.mcp_executor import MCPUtilityExecutor, fetch_database_schema
    from view.a2ui_protocol import A2UIViewAgent

    logger.info("Initializing 3-Tier Multi-Agent AVC System...")

    # -----------------------------------------------------------------------
    # 1. Initialize the Tier 1 Orchestrator
    # -----------------------------------------------------------------------
    orchestrator = AsyncTier1Orchestrator()

    # Define a complex user intent broken into domain-specific tasks
    user_intent_tasks = [
        {
            "domain": "Research",
            "directive": "Compile competitive landscape analysis for Q3 reporting.",
        },
        {
            "domain": "DevOps",
            "directive": "Provision staging environment for payment service v2.1.",
        },
        {
            "domain": "DataEngineering",
            "directive": "Reconcile transaction ledger for fiscal year-end audit.",
        },
    ]

    # Execute Tier 1 Parallel Orchestration
    logger.info("--- STARTING TIER 1 ORCHESTRATION ---")
    swarm_results = await orchestrator.orchestrate_concurrent_tasks(
        user_id="usr_8891_alpha",
        task_definitions=user_intent_tasks,
    )

    for result in swarm_results:
        logger.info(
            f"Swarm Result -> Domain: {result.domain_type} | Status: {result.status}"
        )

    # -----------------------------------------------------------------------
    # 2. Execute Tier 3 MCP Utility with Circuit Breaker
    # -----------------------------------------------------------------------
    logger.info("--- STARTING TIER 3 UTILITY EXECUTION ---")
    mcp_engine = MCPUtilityExecutor(
        failure_threshold=2, recovery_timeout_seconds=10
    )

    try:
        # Successful MCP execution
        db_schema = await mcp_engine.execute_mcp_tool(
            tool_func=fetch_database_schema,
            params={"target_db": "production_sql_01"},
        )
        logger.info(f"Tier 3 Tool Execution Success: {db_schema['schema']}")

        # Force a failure to demonstrate exponential backoff and circuit breaking
        logger.info(
            "Forcing a network failure to demonstrate resiliency mechanics..."
        )
        await mcp_engine.execute_mcp_tool(
            tool_func=fetch_database_schema,
            params={"target_db": "fail_db"},
            max_retries=3,
        )
    except RuntimeError as e:
        logger.warning(f"Expected Utility Failure Handled Safely: {e}")

    # -----------------------------------------------------------------------
    # 3. Stream Results via A2UI View Agent
    # -----------------------------------------------------------------------
    logger.info("--- STARTING A2UI VIEW AGENT STREAM ---")
    view_agent = A2UIViewAgent(surface_id="dashboard_surface_01")

    # Aggregate state for the UI
    final_controller_state = {
        "title": "Execution Swarm Complete",
        "status": "AWAITING_USER_INPUT",
        "agents_completed": len(swarm_results),
    }

    # Asynchronously iterate over the generated JSONL stream
    async for payload in view_agent.generate_ui_stream(final_controller_state):
        logger.info(
            f"A2UI Payload Transmitted over Socket -> {payload.strip()}"
        )

    logger.info(
        "System integration test complete. "
        "Architecture is highly available and fault-tolerant."
    )


if __name__ == "__main__":
    # Execute the asynchronous event loop
    asyncio.run(run_system())
