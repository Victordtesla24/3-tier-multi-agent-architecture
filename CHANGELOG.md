# Changelog

All notable changes to the **3-Tier Multi-Agent Architecture** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-01
### Added
- **Standalone `langgraph` Python Engine** (`src/python/langgraph_orchestrator.py`): Replicates the exact L1/L2/L3 flow outside of the IDE.
- **Strict Pydantic Mapping** (`src/python/models.py`): Added typed schemas for AgentRules and GraphStates.
- **Cross-IDE Enhancements**: Add `.cursorrules` and `.continue/config.json` configurations.
- **Containerization**: Added `docker-compose.yml` and unified `Dockerfile` for cross-platform Linux/Windows/Mac deployments.
- **CI/CD Quality Gates**: Added GitHub actions CI with `pytest` integration, `mypy`, and `ruff` Pre-commits.
- **Visual Documentation**: Inserted Mermaid flowcharts into the multi-agent architecture spec.

### Changed
- Refactored `install.sh` to remove OSX strictness, injecting timestamped configuration backups prior to runtime mutations.

### Fixed
- Replaced dangerous `sed -i` operations in the installer with a mathematically secure `ruamel.yaml` atomic dictionary parser.
