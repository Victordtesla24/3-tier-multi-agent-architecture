---
review_agents: [kieran-python-reviewer, code-simplicity-reviewer, security-sentinel, performance-oracle]
plan_review_agents: [kieran-python-reviewer, code-simplicity-reviewer]
---

# Review Context

Prioritize runtime safety for agent-exposed tools, deterministic completion semantics,
and low-overhead orchestration loops. Treat any ability for an LLM worker to execute
arbitrary shell operations or modify out-of-scope configuration as a critical finding.
