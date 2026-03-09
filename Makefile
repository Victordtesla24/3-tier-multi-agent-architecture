.PHONY: install integrate-crewai ensure-venv audit-duplicates test-audit test-pytest test-e2e test build run-cli benchmark clean

VENV_DIR ?= $(CURDIR)/.venv
PYTHON_BIN ?= $(VENV_DIR)/bin/python
UV_CACHE_DIR ?= /tmp/uv-cache

install:
	@command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
	env -u VIRTUAL_ENV UV_PROJECT_ENVIRONMENT=$(VENV_DIR) UV_CACHE_DIR=$(UV_CACHE_DIR) uv sync --all-extras --python 3.12

ensure-venv:
	@test -x "$(PYTHON_BIN)" || (echo "Error: missing virtualenv interpreter at $(PYTHON_BIN). Run 'make install' or 'uv sync --all-extras --python 3.12' first."; exit 1)

integrate-crewai:
	chmod +x scripts/integrate_crewai.sh
	./scripts/integrate_crewai.sh

audit-duplicates: ensure-venv
	PYTHONPATH=$(CURDIR)/src $(PYTHON_BIN) scripts/enforce_no_duplicates.py

# Audits that the test collection contains a non-trivial number of tests.
# Runs from the tests/ subdirectory to avoid macOS .DS_Store PermissionError
# on /Users/Shared when chromadb/pydantic statically stat('.env') at import time.
test-audit: audit-duplicates
	@echo "Auditing test collection..."
	@cd tests && PYTHONPATH=$(CURDIR)/src $(PYTHON_BIN) -m pytest \
		test_architecture.py test_crewai_integration.py test_contracts.py test_cli_runtime.py test_improvement_plan_workstreams.py test_orchestration_hardening.py \
		--collect-only -q -p no:cacheprovider > /tmp/collect.txt || true
	@COUNT=$$(grep -c "::" /tmp/collect.txt || true); \
	if [ "$$COUNT" -lt 10 ]; then \
		echo "Error: Expected at least 10 tests, collected $$COUNT. Check for import errors:"; \
		cat /tmp/collect.txt; \
		exit 1; \
	fi
	@echo "Tests collected successfully."

test-pytest: test-audit
	cd tests && PYTHONPATH=$(CURDIR)/src $(PYTHON_BIN) -m pytest \
		test_architecture.py test_crewai_integration.py test_contracts.py test_cli_runtime.py test_improvement_plan_workstreams.py test_orchestration_hardening.py test_runtime_graph.py \
		-v -p no:cacheprovider

test-e2e: ensure-venv
	cd tests && PYTHONPATH=$(CURDIR)/src $(PYTHON_BIN) -m pytest \
		test_e2e.py -v -p no:cacheprovider

test: test-pytest test-e2e

build:
	docker build -t antigravity-engine:latest .

run-cli: ensure-venv
	PYTHONPATH=src $(PYTHON_BIN) src/orchestrator/antigravity-cli.py \
		--prompt "test" --workspace /tmp/antigravity_workspace \
		--strict-provider-validation --max-provider-4xx 50

benchmark: ensure-venv
	@echo "Running execution benchmark harness..."
	cd /tmp && PYTHONPATH=$(CURDIR)/src $(PYTHON_BIN) $(CURDIR)/benchmarks/run_benchmark.py

clean:
	rm -rf /tmp/antigravity_workspace
	rm -rf .agent/tmp/*
	rm -rf .agent/memory/*
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.bak" -delete 2>/dev/null || true
