"""3-Tier Agent Hierarchy using CrewAI Framework"""
from crewai import Agent, Task, Crew, Process
from engine.llm_providers import LLMProvider
from typing import List, Dict, Any
import json


class L3LeafWorkerAgent:
    """L3: Leaf Worker Agents - Atomic Task Execution"""

    @staticmethod
    def create_code_executor() -> Agent:
        """Code execution specialist - NO simulated code allowed"""
        return Agent(
            role="L3 Code Execution Specialist",
            goal="Execute genuine, production-ready code with zero placeholders",
            backstory="""You are a leaf worker specialized in executing code.
            CRITICAL DIRECTIVE: Never return TODO, placeholder, or simulated code.
            All code must be complete, functional, and ready for production deployment.
            Enforce strict code verification before returning results.""",
            llm=LLMProvider.get_l2_llm(),
            verbose=True,
            allow_delegation=False  # Leaf workers never delegate
        )

    @staticmethod
    def create_file_operator() -> Agent:
        """File operations specialist"""
        return Agent(
            role="L3 File Operations Specialist",
            goal="Perform precise file create/read/update/delete operations",
            backstory="""You specialize in file system operations with atomic precision.
            You maintain single source of truth and eliminate duplicate files.""",
            llm=LLMProvider.get_l2_llm(),
            verbose=True,
            allow_delegation=False
        )

    @staticmethod
    def create_validator() -> Agent:
        """Output validation specialist"""
        return Agent(
            role="L3 Validation Specialist",
            goal="Validate outputs meet production standards with zero tolerance for errors",
            backstory="""You validate all outputs against strict production criteria.
            You reject any simulated code, incomplete implementations, or placeholders.""",
            llm=LLMProvider.get_l2_llm(),
            verbose=True,
            allow_delegation=False
        )


class L2SubAgents:
    """L2: Sub-Agent Coordinators - Task Decomposition & Delegation"""

    @staticmethod
    def create_research_coordinator() -> Agent:
        """Research & constraint gathering coordinator"""
        return Agent(
            role="L2 Research Coordinator",
            goal="Gather comprehensive requirements and constraints from verified sources",
            backstory="""You coordinate research activities and constraint analysis.
            You delegate to L3 workers for specific research tasks and synthesize findings.""",
            llm=LLMProvider.get_l1_llm(),
            verbose=True,
            allow_delegation=True  # Can delegate to L3
        )

    @staticmethod
    def create_implementation_coordinator() -> Agent:
        """Implementation & code generation coordinator"""
        return Agent(
            role="L2 Implementation Coordinator",
            goal="Coordinate implementation tasks ensuring production-grade output",
            backstory="""You coordinate code generation and implementation tasks.
            You delegate atomic tasks to L3 workers and validate their outputs.
            Maximum 3 retry iterations on L3 failures.""",
            llm=LLMProvider.get_l1_llm(),
            verbose=True,
            allow_delegation=True,
            max_retry_limit=3
        )

    @staticmethod
    def create_quality_coordinator() -> Agent:
        """Quality assurance & testing coordinator"""
        return Agent(
            role="L2 Quality Assurance Coordinator",
            goal="Ensure zero-defect outputs through comprehensive validation",
            backstory="""You coordinate quality assurance and testing activities.
            You delegate validation tasks to L3 workers and enforce strict standards.""",
            llm=LLMProvider.get_l1_llm(),
            verbose=True,
            allow_delegation=True
        )


class L1Orchestrator:
    """L1: Orchestration Manager - High-Level Strategy & Workflow Control"""

    @staticmethod
    def create_manager() -> Agent:
        """L1 Orchestration manager with hierarchical control"""
        return Agent(
            role="L1 Chief Orchestration Manager",
            goal="Decompose complex objectives into optimal execution strategy",
            backstory="""You are the L1 Orchestration Manager with strategic oversight.
            You analyze user requirements, create execution strategies, and delegate
            to L2 coordinators. You enforce single source of truth and maximum
            practical execution integrity across the entire pipeline.

            OPERATIONAL DIRECTIVES:
            1. Decompose complex tasks into clear L2-level objectives
            2. Assign tasks to appropriate L2 coordinators based on capabilities
            3. Monitor execution progress and intervene on failures
            4. Validate final outputs against user requirements
            5. Enforce zero tolerance for simulated or placeholder code""",
            llm=LLMProvider.get_orchestration_llm(),
            verbose=True,
            allow_delegation=True  # Delegates to L2 only
        )
