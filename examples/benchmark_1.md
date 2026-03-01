# Benchmark Prompt 1

**Description:**
A standard user prompt requesting an architecture adjustment with a specific constraint.

**Input Data:**
<input_data>
Create a new logging format for the L2 agents that outputs structured JSON instead of flat text.
Requirement 1: The JSON must have keys: timestamp, agent_id, status.
Requirement 2: It must be saved in `.agent/memory/structured-logs/`.
</input_data>

**Expected Execution Output Elements:**
- Exact-Match Requirement: Directory `.agent/memory/structured-logs/` must be explicitly defined in outputs.
- Exact-Match Requirement: JSON schema containing `timestamp`, `agent_id`, `status` must be present.
