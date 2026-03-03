# 3-Tier Multi-Agent Architecture Repo — Targeted Fix Plan (Precision)

## Objective
Bring the repository to “single-source-of-truth, reproducible execution, auditable tests/benchmarks” standards, consistent with its stated architecture and CI posture.

---

## P0 — Correctness & Reproducibility (must-do)

### 1 Eliminate spec drift between docs and code
**Finding:** The architecture spec references new modules/scripts and also contains embedded integration-script output, breaking doc integrity.  
**Evidence:** docs/architecture/multi-agent-3-level-architecture.md references `llm_providers.py`, `crew_agents.py`, `antigravity_flow.py`, and `scripts/integrate_crewai.sh` and includes mixed-in script content.  
**Sources:** CI + spec drift shown in doc content.  

**Fix:**
- Choose one truth model:
  - Option A (recommended): Make the spec reflect *actual repo files* and delete “generated-script dump” sections from docs.
  - Option B: Create the referenced modules/scripts as real files and ensure they are used by the CLI path.
- Add a “Docs ↔ Code contract” checklist section at top of the architecture doc:
  - Each referenced file path must exist.
  - Each referenced CLI command must execute in Docker and locally.

Acceptance:
- Every file path referenced in `docs/architecture/*.md` exists in the repository.
- No auto-generated script output appears inside architecture documentation.

---

### 2 Align Dockerfile, docker-compose, and README to one runnable entrypoint
**Finding:** Dockerfile uses the CLI; docker-compose runs the LangGraph orchestrator directly.  
**Evidence:** Dockerfile CMD vs docker-compose command mismatch.  

**Fix:**
- Decide primary runtime:
  - If CrewAI is the core: `docker-compose.yml` should run `src/orchestrator/antigravity-cli.py` with a mounted workspace.
  - If LangGraph is retained: make it a documented alternative profile (compose override) and clearly explain when to use it.

Acceptance:
- `docker compose up` runs the same “golden path” described in README.
- README includes one canonical run command, plus explicit alternatives (if any).

---

### 3 Restore “no placeholders” integrity in README and docs
**Finding:** README contains explicit placeholder marker (“PLACEHOLDER DIAGRAM”).  
**Fix:**
- Remove placeholders or replace with final diagrams (Mermaid is fine).
- Any performance/benchmark claims must be backed by:
  - Reproducible benchmark harness
  - Stored benchmark results (versioned) or CI artifacts

Acceptance:
- No “PLACEHOLDER” strings in README/docs.
- Any benchmark claim links to the benchmark harness and a reproducible command.

---

### 4 Provide a real `.env.template` and unify environment variables
**Finding:** README instructs `.env.template`, but it is not present; variables differ across runtime artifacts.  
**Fix:**
- Add `.env.template` at repo root containing *only* the required keys for the canonical run path.
- Standardize variable names across:
  - README
  - `src/engine/llm_config.py`
  - docker-compose
  - CI

Recommended minimal keys (example):
- OPENAI_API_KEY
- GOOGLE_API_KEY (or GEMINI_API_KEY — pick one and standardize)
- MINIMAX_* (if used)
- DEEPSEEK_* (if used)
- CREWAI_STORAGE_DIR (optional)

Acceptance:
- README setup matches actual runtime requirements.
- `docker compose up` works with `.env` created from `.env.template`.

---

## P1 — Tests that actually prove the 3-tier architecture

### 5 Make test outcomes auditable (remove “33/33” ambiguity)
**Finding:** README claims “33/33 tests passing,” but CI uses `pytest tests/` which can pass even with 0 tests.  
**Fix:**
- Add a CI assertion step:
  - `pytest --collect-only -q | tee /tmp/collect.txt`
  - Fail if collected tests < N (choose N based on expected baseline)
- Add a README badge/section that references CI + minimum test count.

Acceptance:
- CI fails if tests are not collected.
- README does not contain unverified “33/33” claims unless enforced.

---

### 6 Add tier-boundary tests (contract tests)
Add tests proving:
- Orchestration tier only routes/assigns and does not “execute”
- L1 only decomposes/validates plans
- L2/L3 produce artifacts and are blocked by verification gates if placeholders appear

Suggested tests:
- `test_input_data_extraction_contract()`: ensures `<input_data>...</input_data>` extraction
- `test_no_placeholder_gate()`: verifies generated output rejects TODO/pass/NotImplemented markers
- `test_manager_agent_required_for_hierarchical()`: asserts CrewAI hierarchical process requires manager agent

CrewAI references for correctness:
- Hierarchical process requires manager agent/LLM
- Memory requires `memory=True` and storage path / CREWAI_STORAGE_DIR
- Reasoning uses `reasoning` and `max_reasoning_attempts`

---

## P2 — Benchmarks (real, reproducible, versioned)

### 7 Define a benchmark harness (and stop calling pytest “benchmarks”)
**Finding:** CI step name includes “benchmarks” but only runs pytest.  
**Fix:**
- Add `benchmarks/` directory with:
  - deterministic fixtures
  - metrics collection (latency, token usage if available, failure rate)
  - a single command: `make benchmark`
- Store benchmark outputs in `docs/benchmarks/` as versioned markdown/JSON.

Acceptance:
- `make benchmark` produces an artifact (JSON/MD).
- README links to the benchmark methodology and latest results.

---

## P3 — Maintenance & Code Quality

### 8 Remove or isolate unused orchestrators (LangGraph vs CrewAI)
**Finding:** Repo includes both LangGraph and CrewAI paths; documentation says CrewAI-first.  
**Fix:**
- Either:
  - remove LangGraph modules from canonical runtime, or
  - keep them under `src/experimental/` with explicit docs and no production claims

Acceptance:
- One canonical orchestrator is used by CLI/Docker/README.
- Alternates are labeled experimental.

---

## “Done” Definition (tight)
- Docs reference only real files.
- One canonical run path works (local + Docker + CI).
- CI enforces non-zero test collection and tier-boundary contracts.
- Benchmarks exist as a real harness with reproducible results.
- README contains no placeholders and no unverified performance claims.