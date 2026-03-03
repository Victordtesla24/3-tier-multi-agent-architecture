.PHONY: install test test-pytest build run-cli clean integrate-crewai

install:
	@command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
	export UV_PROJECT_ENVIRONMENT=/tmp/.venv-antigravity && export UV_CACHE_DIR=/tmp/uv-cache && uv sync --python 3.12 --all-extras

integrate-crewai:
	chmod +x scripts/integrate_crewai.sh
	./scripts/integrate_crewai.sh

test-audit:
	@echo "Auditing test collection..."
	@cd tests && PYTHONPATH=$(CURDIR)/src /tmp/.venv-antigravity/bin/pytest test_architecture.py test_crewai_integration.py test_contracts.py --collect-only -q -p no:cacheprovider > /tmp/collect.txt || true
	@if grep -qi "no tests collected" /tmp/collect.txt || grep -qi "error" /tmp/collect.txt; then \
		echo "Error: No tests collected or collection failed!"; \
		exit 1; \
	fi
	@echo "Tests collected successfully."

test-pytest: test-audit
	cd tests && PYTHONPATH=$(CURDIR)/src /tmp/.venv-antigravity/bin/pytest test_architecture.py test_crewai_integration.py test_contracts.py -v -p no:cacheprovider

test-e2e:
	cd tests && PYTHONPATH=$(CURDIR)/src /tmp/.venv-antigravity/bin/pytest test_e2e.py -v -p no:cacheprovider

test: test-pytest test-e2e
	python src/engine/config_manager.py .agent/tmp/mock_gemini.md

build:
	docker build -t antigravity-engine:latest .

run-cli:
	PYTHONPATH=src uv run python src/orchestrator/antigravity-cli.py --prompt "test"

benchmark:
	@echo "Running execution benchmark..."
	PYTHONPATH=src uv run python benchmarks/run_benchmark.py

clean:
	rm -rf .pytest_cache
	rm -rf .agent/tmp/*
	rm -rf .agent/memory/*
	find . -type d -name "__pycache__" -exec rm -rf {} +
