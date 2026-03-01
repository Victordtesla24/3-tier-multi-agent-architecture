# Benchmark 2: Circular Dependency Resolution

**Description:**
This benchmark tests the L1 Orchestrator's ability to preemptively identify architectural faults before delegating to L2 Sub-Agents. It presents a codebase request containing an implicit circular dependency. 

**Input Data:**
<input_data>
Create a Python data pipeline with two core modules: `extractor.py` and `transformer.py`. 
Requirement 1: `extractor.py` must import a constant `CONFIG_MAP` from `transformer.py` to know what to extract.
Requirement 2: `transformer.py` must import the `ExtractionEngine` class from `extractor.py` to instantiate it during the transformation phase.
Requirement 3: Both modules must be fully typed and adhere to PEP 8.
</input_data>

**Expected Execution Output Elements:**
- **Exact-Match Requirement (Negative Constraint Check)**: The L1 Orchestrator MUST halt and invoke the **Critical Clarification Protocol**. It must refuse to generate the code as requested because Requirements 1 and 2 create a fatal circular import in Python.
- **Architectural Refactoring**: The system must autonomously propose a third module (e.g., `config.py` or `shared.py`) to break the dependency chain before authorizing L2/L3 execution.

**Benefits Showcased:**
Proves the architecture acts as an "Elite Engineer" that prevents deployment-breaking logic loops rather than blindly fulfilling flawed instructions.
