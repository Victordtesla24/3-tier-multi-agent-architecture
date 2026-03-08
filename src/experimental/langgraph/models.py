from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- Rule Definition Models ---

class AgentRuleMetadata(BaseModel):
    """Represents the YAML frontmatter of an .agent/rules/*.md file"""
    trigger: str = Field(..., description="When the agent is triggered (e.g., manual, always_on)")
    priority: int = Field(..., description="Execution priority (lower is earlier)")
    model: Optional[str] = Field(default="Gemini 3 Pro Preview", description="The LLM model used")
    role: str = Field(..., description="The highly specific expert role/persona this agent embodies.")
    goal: str = Field(..., description="The singular, deterministic goal this agent strives to achieve.")
    backstory: str = Field(..., description="The behavioral backstory informing the agent's logic and rigor.")
    
class AgentRule(BaseModel):
    """Represents a fully parsed agent rule file"""
    filename: str
    metadata: AgentRuleMetadata
    directives: List[str] = Field(default_factory=list, description="Strict operational constraints")
    
# --- Execution State Models ---

class OrchestrationPlan(BaseModel):
    """L1 Orchestration Plan mapping tasks to L2 agents"""
    summary: str = Field(description="High level summary of the operation")
    tasks: List[Dict[str, Any]] = Field(description="Sub-agent exact task delegations")
    
class L2ValidationResult(BaseModel):
    """The result of an L2 Agent validating an L3 Worker's artifact"""
    is_valid: bool = Field(description="Did the L3 artifact pass all zero-tolerance restrictions?")
    feedback: Optional[str] = Field(description="Feedback requiring L3 regeneration if invalid")
    compiled_artifact: Optional[str] = Field(description="The finalized genuine code/document")

# --- Overall Pipeline State ---

class ArchitectState(BaseModel):
    """The global graph state for the LangGraph execution"""
    raw_prompt: str
    reconstructed_prompt: Optional[str] = None
    research_context: Optional[str] = None
    l1_plan: Optional[OrchestrationPlan] = None
    l2_results: Dict[str, L2ValidationResult] = Field(default_factory=dict)
    final_status: str = "INIT"
