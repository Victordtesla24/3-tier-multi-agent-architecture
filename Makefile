.PHONY: install test test-pytest build run clean

install:
	@command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
	uv sync

test-pytest:
	pytest tests/ -v

test: test-pytest
	python src/engine/config_manager.py .agent/tmp/mock_gemini.md

build:
	docker build -t antigravity-engine:latest .

run-cli:
	python src/orchestrator/antigravity-cli.py --prompt "test"

clean:
	rm -rf .pytest_cache
	rm -rf .agent/tmp/*
	rm -rf .agent/memory/*
	find . -type d -name "__pycache__" -exec rm -rf {} +
