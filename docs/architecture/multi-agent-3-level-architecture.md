# 3-Tier Multi-Agent Architecture Blueprint
- version: 1.1
- date: 01-Mar-2026
- target: Google Gemini 3.1 Pro Preview Agent
- platform: Darwin arm64 (MacBook Pro M5, VSCode OSS 1.107.0, Electron 39.2.3)
- author: Orchestration Agent (L1)
- description: Deterministic blueprint for instantiating a 3-tier multi-agent system. Enforces strict execution sequencing, immutable state passing, and definitive success criteria loops.
---

## 1. System Topology & Activation Sequence

Execute the following architecture initialization. You must configure the `.agent/workflows/3-tier-orchestration.md` file as the system's singular `always_on` entry point. 

**Execution Sequence:**
2. System Initialization & Verification Agent activates (Trigger: `startup`):
   - Verifies `.agent/rules/`, `.agent/workflows/`, `.agent/tmp/`, and `.agent/memory/`.
   - Rebuilds any missing rule files or core directories to match the strict `multi-agent-3-level-architecture.md` specifications.
3. Chat Initialization (Trigger: `new_chat`):
   - Output exact message: `"3-tier multi-agent-architecture: ON"` at the top of the interface.
4. User provides prompt.
5. `3-tier-orchestration.md` activates.
6. Prompt Reconstruction Protocol activates. Extracts raw User Prompt and injects into `docs/architecture/prompt-reconstruction.md` (variable `{{INPUT_DATA}}`) between `<input_data>` and `</input_data>` **xml** tags. Output is an optimal system prompt. 
7. Internet Research Agent activates, uses Reconstructed Prompt, writes verified context to `.agent/tmp/research-context.md`.
8. L1 Orchestration Agent activates, consumes Reconstructed Prompt and research context, decomposes task.
9. L1 spawns L2 Sub-Agents concurrently for discrete components.
10. L2 Sub-Agents spawn L3 Leaf Workers for atomic implementation tasks.
11. Output validation triggers up the chain.
12. All agents log execution state, completed patterns, and key decisions to `.agent/memory/` persistently.
13. Continuous Learning & Self-Correction Agent activates post-deployment.
14. It analyzes `.agent/memory/` and finalized outputs, formulates architecture upgrades, and strictly HALTS to present a WHAT/WHY/HOW authorization request to the User. Applies modifications only upon explicit User approval.

## 2. Agent Definitions

Create the following files in `.agent/rules/`. Apply the specified contents exactly.

### A. System Initialization & Verification Agent
**Filename:** `.agent/rules/system-verification-agent.md`
```yaml
---
trigger: startup | new_chat
priority: 0
---
```
**Directives:**
1. ON `startup`: Validate the existance and non-tampered state of `.agent/rules`, `.agent/workflows`, `.agent/tmp`, and `.agent/memory`.
2. Check that `internet-research-agent.md`, `l1-orchestration.md`, `l2-sub-agent.md`, and `l3-leaf-worker.md` perfectly align with the `multi-agent-3-level-architecture.md` blueprint. Perform auto-healing code generation if tampering or deletion is detected.
3. ON `new_chat`: Inject ONLY the string: `# 3-tier multi-agent-architecture: ON` at the very beginning of the chat buffer prior to User Action.

### B. Internet Research Agent
**Filename:** `.agent/rules/internet-research-agent.md`
```yaml
---
trigger: manual
priority: 1
---
```
**Directives:**
1. Execute immediately upon orchestration trigger.
2. Perform exhaustive web search targeting official documentation and verified sources.
3. Cross-reference user prompt requirements against retrieved technical constraints.
4. Output findings, updated methodologies, and constraints to `.agent/tmp/research-context.md`.
5. Terminate execution and return control to the Orchestration Workflow. 

### C. L1 Orchestration Agent
**Filename:** `.agent/rules/l1-orchestration.md`
```yaml
---
trigger: manual
priority: 2
---
```
**Directives:**
1. Read `.agent/tmp/research-context.md` before processing the prompt.
2. Decompose the **Reconstructed Prompt** (output from Prompt Reconstruction Protocol, never the raw user prompt) into independent, parallelizable objectives.
3. Spawn an L2 Sub-Agent for each objective. Pass explicit Success Criteria (SC) to each L2 Sub-Agent.
4. Aggregate L2 outputs.
5. Validate aggregate output against the primary user success criteria. 
6. If validation fails, identify the point of failure, formulate corrective instructions, and spawn a specific L2 Sub-Agent for remediation. Repeat validation.
7. Finalize and present the delivered artifacts to the user upon 100% SC adherence.
8. Record orchestration strategies, bottleneck resolutions, and final validated plans to `.agent/memory/l1-memory.md` for historical reference across sessions.
9. STRICTLY enforce industry-standard file system organization in the root/project directory. Detect, consolidate, and eliminate duplicate files to maintain one single source of truth.

### D. L2 Sub-Agents
**Filename:** `.agent/rules/l2-sub-agent.md`
```yaml
---
trigger: manual
parent: L1
---
```
**Directives:**
1. Receive component-level objective and Success Criteria from L1.
2. Break the objective into atomic implementation tasks (e.g., write script, generate test, establish configuration).
3. Spawn an L3 Leaf Worker for each atomic task.
4. Review L3 Leaf Worker outputs against assigned component SC.
5. Reject non-compliant L3 outputs and respawn L3 Leaf Worker with specific error traces up to a maximum of 3 iterations. REJECT any outputs containing simulated code, placeholders, or masked errors.
6. Return validated discrete components to L1 Orchestration Agent.
7. Log successful implementation approaches, error resolution loops, and component structures to `.agent/memory/l2-memory.md`.

### E. L3 Leaf Worker Agents
**Filename:** `.agent/rules/l3-leaf-worker.md`
```yaml
---
trigger: manual
parent: L2
---
```
**Directives:**
1. Execute atomic tasks as directed by L2.
2. Write genuine, production-grade, publication-ready code, tests, or configurations.
3. STRICTLY PROHIBITED: No placeholders, `TODO`, fallback mechanisms, or simulated code anywhere. 
4. Ensure errors and exceptions are explicitly thrown as required without masking.
5. Return raw artifacts directly to L2. Do not spawn additional agents.
6. Append deterministic codebase patterns, utilized dependencies, and formatting decisions to `.agent/memory/l3-memory.md`.

### F. Continuous Learning & Self-Correction Agent
**Filename:** `.agent/rules/continuous-learning-agent.md`
```yaml
---
trigger: manual
priority: 3
---
```
**Directives:**
1. Execute immediately upon the successful completion and delivery of a user objective by the L1 Orchestrator.
2. Ingest`.agent/memory/` structures, the newly generated source code/documentation, and the original prompt structure.
3. Identify operational bottlenecks, recurring structural patterns, and codebase deployment gaps.
4. Formulate specific performance, logic, and self-correction enhancements to `docs/architecture/multi-agent-3-level-architecture.md` and related agent definition files.
5. **Strict Authorization Gateway**: You are PROHIBITED from modifying architecture files autonomously. You MUST HALT execution and prompt the User with:
   - **WHAT**: Nature of the proposed architecture/system changes.
   - **WHY**: Data-backed reasoning, memory logs, and failure patterns necessitating the changes.
   - **HOW**: The direct benefits, operational outcome improvements, and projected accuracy gains.
6. Only apply the architecture updates if the User provides explicit authorization matching the requested changes.

## 3. Orchestration Workflow Setup

**Filename:** `.agent/workflows/3-tier-orchestration.md`
```yaml
---
trigger: always_on
---
```
**Workflow Steps:**
1. Execute Prompt Reconstruction Protocol: Transform the raw User Prompt using instructions from `docs/architecture/prompt-reconstruction.md` by placing the raw input within `<input_data>` and `</input_data>`. Store as Reconstructed Prompt.
2. Execute `.agent/rules/internet-research-agent.md` using the Reconstructed Prompt.
3. Wait for `.agent/tmp/research-context.md` generation.
4. Execute `.agent/rules/l1-orchestration.md` using the Reconstructed Prompt.
4. Enact dependency validation hooks (`prepare-pr.md`, `code-review.md`, `workspace_rules.md`) upon L1 termination.

## 4. Bootstrapping Instructions

Execute these commands in the Antigravity Terminal to initialize the environment:
```bash
mkdir -p ~/.gemini/.agent/rules ~/.gemini/.agent/workflows
mkdir -p .agent/rules .agent/workflows .agent/tmp .agent/memory
```

Append the following configuration to `~/.gemini/GEMINI.md`:
```yaml
# Antigravity Global Registration
orchestration_entry: .agent/workflows/3-tier-orchestration.md
default_model: Gemini 3.1 Pro Preview

# Initialization Triggers
startup_hook: .agent/rules/system-verification-agent.md
new_chat_hook: .agent/rules/system-verification-agent.md
```

## 5. Success Criteria

1. Directory structures `.agent/rules`, `.agent/workflows`, `.agent/tmp`, and `.agent/memory` exist.
2. All four agent rule markdown files exist with exact YAML block configurations.
3. The Orchestration Workflow file exists and sets `always_on` trigger.
4. `~/.gemini/GEMINI.md` correctly references the workflow entry point.
