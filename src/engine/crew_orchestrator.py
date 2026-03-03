from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from crewai import Agent, Crew, Process, Task

from engine.llm_config import ModelMatrix, build_model_matrix


class CrewAIThreeTierOrchestrator:
    """
    CrewAI-backed orchestrator that preserves the 3-tier boundaries:
      - Orchestration tier: manager/router (Gemini primary → GPT-5.2-Codex fallback)
      - Level 1: senior/analytical agents (GPT-5.2-Codex primary → MiniMax fallback)
      - Level 2: execution/worker agents (MiniMax primary → DeepSeek fallback)

    Memory is enabled at Crew level and stored under <workspace>/.agent/memory/crewai_storage.
    """

    def __init__(self, workspace_dir: str, *, verbose: bool = True):
        self.workspace = Path(workspace_dir).resolve()
        self.verbose = verbose

        # Load .env if present (workspace-root).
        dotenv_path = self.workspace / ".env"
        if dotenv_path.exists():
            load_dotenv(dotenv_path=dotenv_path, override=False)

        # Ensure 3-tier expected directories exist
        (self.workspace / ".agent" / "tmp").mkdir(parents=True, exist_ok=True)
        (self.workspace / ".agent" / "memory").mkdir(parents=True, exist_ok=True)

        # Bind CrewAI memory storage into the 3-tier memory namespace.
        storage_dir = self.workspace / ".agent" / "memory" / "crewai_storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        os.environ["CREWAI_STORAGE_DIR"] = str(storage_dir)

        self.models: ModelMatrix = build_model_matrix(self.workspace)

    def _extract_input_data(self, raw_prompt: str) -> str:
        """
        If raw_prompt contains <input_data>...</input_data>, extract its inner payload.
        Otherwise return raw_prompt as-is.
        """
        m = re.search(r"<input_data>(.*?)</input_data>", raw_prompt, flags=re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        return raw_prompt.strip()

    def reconstruct_prompt(self, raw_prompt: str) -> str:
        """
        Executes the Prompt Reconstruction Protocol as a CrewAI task using Level 1 models.
        """
        template_path = self.workspace / "docs" / "architecture" / "prompt-reconstruction.md"
        if not template_path.exists():
            raise FileNotFoundError(
                f"Missing prompt reconstruction template at {template_path}. "
                "This integration expects the existing 3-tier architecture docs to be present."
            )

        template = template_path.read_text(encoding="utf-8")
        payload = self._extract_input_data(raw_prompt)
        reconstruction_prompt = template.replace("{{INPUT_DATA}}", payload)

        agent = Agent(
            role="Prompt Reconstruction Protocol Agent",
            goal="Reconstruct <input_data> into an optimal, production-grade system prompt with 1:1 requirement coverage.",
            backstory="You are an elite prompt engineer enforcing deterministic execution constraints.",
            llm=self.models.level1,
            verbose=self.verbose,
            allow_delegation=False,
            reasoning=True,
            max_reasoning_attempts=3,
        )

        task = Task(
            description=reconstruction_prompt,
            expected_output="ONLY a Markdown code block containing the rewritten prompt, OR a list of clarifying questions.",
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            memory=True,
            verbose=self.verbose,
        )

        result = crew.kickoff()

        # Persist for downstream stages
        out_path = self.workspace / ".agent" / "tmp" / "reconstructed_prompt.md"
        out_path.write_text(str(result), encoding="utf-8")

        return str(result)

    def run_research(self, reconstructed_prompt: str) -> str:
        """
        Executes the Internet Research Agent role as a CrewAI task using Level 1 models.
        """
        agent = Agent(
            role="Internet Research Agent",
            goal="Produce verified constraints/context for the reconstructed prompt (official sources only).",
            backstory="You are a technical OSINT analyst. You do not write project code; you provide ground-truth constraints.",
            llm=self.models.level1,
            verbose=self.verbose,
            allow_delegation=False,
            reasoning=True,
            max_reasoning_attempts=3,
        )

        task = Task(
            description=(
                "Perform technical research strictly from official / primary documentation sources.\n\n"
                "INPUT (Reconstructed Prompt):\n"
                f"{reconstructed_prompt}\n\n"
                "OUTPUT REQUIREMENTS:\n"
                "- Provide constraints, API limits, model configuration facts, and integration gotchas.\n"
                "- Prefer official documentation and vendor API references.\n"
                "- Be explicit about any missing configuration that blocks execution.\n"
            ),
            expected_output="A concise but complete research context, suitable to be passed to an orchestrator agent.",
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            memory=True,
            verbose=self.verbose,
        )

        result = crew.kickoff()
        out_path = self.workspace / ".agent" / "tmp" / "research-context.md"
        out_path.write_text(str(result), encoding="utf-8")
        return str(result)

    def execute(self, reconstructed_prompt: str, research_context: str) -> str:
        """
        Executes the main 3-tier Crew using a hierarchical process:
          - Manager/router: orchestration-tier models
          - Senior agents: level1-tier models
          - Worker agent: level2-tier models
        """
        manager = Agent(
            role="Orchestration Tier Manager/Router",
            goal="Plan, delegate, and validate completion using strict success-criteria enforcement.",
            backstory="You are a CTO-level manager agent. You delegate to senior and worker agents, enforce single-source-of-truth, and reject placeholder output.",
            llm=self.models.orchestration,
            verbose=self.verbose,
            allow_delegation=True,
            reasoning=True,
            max_reasoning_attempts=3,
        )

        senior = Agent(
            role="Level 1 Senior/Analytical Agent",
            goal="Decompose objectives and produce an execution plan with strict acceptance criteria per task.",
            backstory="You are a senior systems architect. You translate requirements into executable work packages and guardrails.",
            llm=self.models.level1,
            verbose=self.verbose,
            allow_delegation=True,
            reasoning=True,
            max_reasoning_attempts=3,
        )

        from crewai_tools import FileReadTool, FileWriterTool

        worker = Agent(
            role="Level 2 Execution/Worker Agent",
            goal="Implement atomic tasks with zero placeholders and explicit error handling.",
            backstory="You are an elite staff engineer who produces complete, executable artefacts with no TODOs and no simulated logic.",
            llm=self.models.level2,
            verbose=self.verbose,
            allow_delegation=False,
            tools=[FileReadTool(), FileWriterTool()],
            reasoning=True,
            max_reasoning_attempts=2,
        )

        # The manager will coordinate; tasks encourage delegation and verification loops.
        kickoff_task = Task(
            description=(
                "You are executing inside the Antigravity 3-tier architecture.\n\n"
                "INPUTS:\n"
                "1) Reconstructed Prompt:\n"
                f"{reconstructed_prompt}\n\n"
                "2) Research Context:\n"
                f"{research_context}\n\n"
                "REQUIREMENTS:\n"
                "- Produce a complete, production-grade answer with no placeholder code and no TODOs.\n"
                "- Where code is required, output exact files (paths + full contents).\n"
                "- If shell operations are required, provide a single combined script.\n"
                "- Enforce a strict single-source-of-truth across files.\n"
            ),
            expected_output=(
                "A complete deliverable set (plans + code + scripts) with explicit file paths and full file contents."
            ),
            agent=manager,
        )

        crew = Crew(
            agents=[manager, senior, worker],
            tasks=[kickoff_task],
            process=Process.hierarchical,
            manager_agent=manager,
            memory=True,
            planning=True,
            verbose=self.verbose,
            cache=True,
        )

        result = crew.kickoff()
        out_path = self.workspace / ".agent" / "tmp" / "final_output.md"
        out_path.write_text(str(result), encoding="utf-8")
        return str(result)
