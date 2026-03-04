.PHONY: install integrate-crewai test-audit test-pytest test-e2e test build run-cli benchmark clean

install:
	@command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
	export UV_PROJECT_ENVIRONMENT=/tmp/.venv-antigravity && export UV_CACHE_DIR=/tmp/uv-cache && uv sync --all-extras --python 3.12

integrate-crewai:
	chmod +x scripts/integrate_crewai.sh
	./scripts/integrate_crewai.sh

# Audits that the test collection contains a non-trivial number of tests.
# Runs from the tests/ subdirectory to avoid macOS .DS_Store PermissionError
# on /Users/Shared when chromadb/pydantic statically stat('.env') at import time.
test-audit:
	@echo "Auditing test collection..."
	@cd tests && PYTHONPATH=$(CURDIR)/src /tmp/.venv-antigravity/bin/pytest \
		test_architecture.py test_crewai_integration.py test_contracts.py \
		--collect-only -q -p no:cacheprovider > /tmp/collect.txt || true
	@COUNT=$$(grep -c "::" /tmp/collect.txt || true); \
	if [ "$$COUNT" -lt 10 ]; then \
		echo "Error: Expected at least 10 tests, collected $$COUNT. Check for import errors:"; \
		cat /tmp/collect.txt; \
		exit 1; \
	fi
	@echo "Tests collected successfully."

test-pytest: test-audit
	cd tests && PYTHONPATH=$(CURDIR)/src /tmp/.venv-antigravity/bin/pytest \
		test_architecture.py test_crewai_integration.py test_contracts.py \
		-v -p no:cacheprovider

test-e2e:
	cd tests && PYTHONPATH=$(CURDIR)/src /tmp/.venv-antigravity/bin/pytest \
		test_e2e.py -v -p no:cacheprovider

test: test-pytest test-e2e

build:
	docker build -t antigravity-engine:latest .

run-cli:
	PYTHONPATH=src /tmp/.venv-antigravity/bin/python src/orchestrator/antigravity-cli.py \
		--prompt "test" --workspace /tmp/antigravity_workspace

benchmark:
	@echo "Running execution benchmark harness..."
	PYTHONPATH=src /tmp/.venv-antigravity/bin/python benchmarks/run_benchmark.py

clean:
	rm -rf /tmp/antigravity_workspace
	rm -rf .agent/tmp/*
	rm -rf .agent/memory/*
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.bak" -delete 2>/dev/null || true
