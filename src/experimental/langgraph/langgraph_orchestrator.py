import os
import logging
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from pydantic import BaseModel
from .models import ArchitectState, OrchestrationPlan, L2ValidationResult

# Try optional litellm import for fallback capability
try:
    from litellm import completion
except ImportError:
    completion = None

logger = logging.getLogger("LangGraphOrchestrator")

# --- LangGraph Node Functions ---

def prompt_reconstruction_node(state: ArchitectState) -> Dict:
    """Executes the Prompt Reconstruction Protocol."""
    logger.info("Executing Prompt Reconstruction...")
    # Mock LLM transformation
    constructed = f"<reconstructed>\n{state.raw_prompt}\n</reconstructed>"
    return {"reconstructed_prompt": constructed}

def internet_research_node(state: ArchitectState) -> Dict:
    """Executes the Internet Research Agent."""
    logger.info("Executing Internet Research...")
    # Mock LLM search
    return {"research_context": "Found 3 relevant architectural patterns."}

def l1_orchestration_node(state: ArchitectState) -> Dict:
    """Executes the L1 Orchestrator Agent to map tasks."""
    logger.info("Executing L1 Orchestration...")
    plan = OrchestrationPlan(
        summary="Executing mapped logic.",
        tasks=[{"id": 1, "action": "Generate Core Engine"}]
    )
    return {"l1_plan": plan}

def l2_sub_agent_node(state: ArchitectState) -> Dict:
    """Executes L2 Sub-Agents which delegates to L3 and validates."""
    logger.info("Executing L2 Sub-Agents & L3 Leaf Workers...")
    results = {}
    if state.l1_plan:
        for task in state.l1_plan.tasks:
            # Simulate L3 generation and L2 strict validation
            results[str(task["id"])] = L2ValidationResult(
                is_valid=True,
                feedback="Success",
                compiled_artifact="def execute(): pass"
            )
    return {"l2_results": results}

def verification_node(state: ArchitectState) -> Dict:
    """Final verification of constraints and logging."""
    logger.info("Verifying Final Artifacts...")
    all_valid = all(res.is_valid for res in state.l2_results.values())
    status = "SUCCESS" if all_valid else "FAILED_CONSTRAINTS"
    return {"final_status": status}


# --- Graph Construction ---

def build_architecture_graph() -> StateGraph:
    """Builds the 3-Tier Multi-Agent architecture using LangGraph."""
    
    workflow = StateGraph(ArchitectState)

    # Add Nodes
    workflow.add_node("prompt_reconstruction", prompt_reconstruction_node)
    workflow.add_node("internet_research", internet_research_node)
    workflow.add_node("l1_orchestrator", l1_orchestration_node)
    workflow.add_node("l2_sub_agents", l2_sub_agent_node)
    workflow.add_node("verification", verification_node)

    # Add Edges (Deterministic Flow)
    workflow.set_entry_point("prompt_reconstruction")
    workflow.add_edge("prompt_reconstruction", "internet_research")
    workflow.add_edge("internet_research", "l1_orchestrator")
    workflow.add_edge("l1_orchestrator", "l2_sub_agents")
    workflow.add_edge("l2_sub_agents", "verification")
    workflow.add_edge("verification", END)

    return workflow.compile()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    app = build_architecture_graph()
    
    # Example standalone execution test
    initial_state = ArchitectState(raw_prompt="Build a distributed Go microservice.")
    final_state = app.invoke(initial_state)
    logger.info(f"Pipeline Terminated with Status: {final_state['final_status']}")
