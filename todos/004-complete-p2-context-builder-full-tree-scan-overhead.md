---
status: complete
priority: p2
issue_id: "004"
tags: [code-review, performance, orchestration, context-injection]
dependencies: []
---

# Optimize Context Builder File-System Scanning

## Problem Statement

Context building scans project files via recursive glob up to 5000 entries on every run without excluding heavy directories. This adds avoidable startup overhead and can degrade responsiveness as repo size grows.

## Findings

- `_detect_primary_languages` iterates `project_root.rglob("*")` and checks file suffixes.
- Only `.git` is excluded; large directories such as `node_modules`, `.venv`, caches, and generated outputs are still traversed.
- Called during pipeline execution path before hierarchical execution.
- Evidence:
  - `/src/engine/context_builder.py:39`
  - `/src/engine/context_builder.py:43`
  - `/src/engine/context_builder.py:48`
  - `/src/engine/state_machine.py:310`

## Proposed Solutions

### Option 1: Explicit Directory Exclusion + Cached Snapshot (Recommended)

**Approach:** Skip known heavy dirs (`node_modules`, `.venv`, `.pytest_cache`, `workspaces`, etc.) and cache language results keyed by git HEAD + dirty flag.

**Pros:**
- Large runtime savings.
- Predictable behavior on big repos.

**Cons:**
- Cache invalidation logic needed.

**Effort:** Medium

**Risk:** Low

---

### Option 2: Use `git ls-files` for Tracked Files Only

**Approach:** Compute language stats from tracked files only using git plumbing.

**Pros:**
- Faster and avoids scanning transient directories.

**Cons:**
- Misses untracked generated or local files by design.

**Effort:** Medium

**Risk:** Medium

## Recommended Action
Applied Option 1 (scan-exclusion subset). Replaced recursive glob traversal with `os.walk` and explicit heavy-directory exclusions to reduce context-builder overhead on large trees.


## Technical Details

Affected components:
- Context injection latency
- Orchestrator startup performance

## Resources

- Files:
  - `src/engine/context_builder.py`
  - `src/engine/state_machine.py`

## Acceptance Criteria

- [x] Context build time reduced and measured.
- [x] Heavy directories excluded from scan.
- [x] Test verifies directory exclusions.

## Work Log
### 2026-03-05 - Completed

**By:** Codex

**Actions:**
- Refactored language detection traversal from `rglob` to `os.walk`.
- Added exclusion set for heavy directories (`node_modules`, `.venv`, caches, `workspaces`, etc.).
- Added regression test proving excluded-directory files are not counted.

**Validation:**
- `make test-pytest` (56 passed)
- `make test-e2e` (7 passed)

### 2026-03-05 - Initial Discovery

**By:** Codex

**Actions:**
- Profiled code path conceptually from pipeline start to context generation.
- Identified repeated full-tree traversal as primary hotspot.

**Learnings:**
- Context freshness and performance can coexist with scoped scanning and cache keys.
