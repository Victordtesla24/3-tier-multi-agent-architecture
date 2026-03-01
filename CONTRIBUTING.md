# Contributing to the 3-Tier Multi-Agent Architecture

We welcome community contributions, but all pull requests must strictly adhere to our core architectural constraints:

## The Zero-Tolerance Policy

This architecture exists mathematically to eradicate "hallucinated" or incomplete AI outputs. All PRs must adhere to the following rules or they will be summarily rejected by our CI/CD pipelines:

1. **No Simulated Code**: You may not introduce `// TODO`, `pass`, or fake variables into the Python execution engine.
2. **Deterministic Validation**: Any modifications to the `src/python/langgraph_orchestrator.py` must include a mapped `pytest` validation function asserting exact architectural state transitions.
3. **Typing Completeness**: All new Python code must pass `mypy --strict`.

## Development Setup

1. Clone the repository natively.
2. Run `make install` to configure the Python environment.
3. Run `pre-commit install` to register our quality gates locally.
4. Execute `make test` prior to submitting any patches.

## Submitting Pull Requests

1. Fork the repo and create your branch from `main`.
2. Update the `README.md` if adjusting user-facing APIs.
3. Describe the *probabilistic optimization* achieved by your patch. We do not accept PRs claiming "100% guarantees".
