.PHONY: install test test-pytest build run-cli clean integrate-crewai

install:
	@command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
	export UV_PROJECT_ENVIRONMENT=/tmp/.venv-antigravity && export UV_CACHE_DIR=/tmp/uv-cache && uv sync --all-extras

integrate-crewai:
	chmod +x scripts/integrate_crewai.sh
	./scripts/integrate_crewai.sh

test-pytest:
	PYTHONPATH=src /tmp/.venv-antigravity/bin/pytest tests/ -v

test: test-pytest
	python src/engine/config_manager.py .agent/tmp/mock_gemini.md

build:
	docker build -t antigravity-engine:latest .

run-cli:
	PYTHONPATH=src uv run python src/orchestrator/antigravity-cli.py --prompt "test"

clean:
	rm -rf .pytest_cache
	rm -rf .agent/tmp/*
	rm -rf .agent/memory/*
	find . -type d -name "__pycache__" -exec rm -rf {} +
