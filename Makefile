.PHONY: help \
	test unit validate \
	fmt fmt-check lint \
	run graph-build graph-query context-query eval \
	ci-local \
	clean cloc

UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
UV_RUN = UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run
PYTHON = $(UV_RUN) python
PYTEST = $(UV_RUN) --with pytest python -m pytest
RUFF = $(UV_RUN) --with ruff ruff
ROOT ?= .
HOST ?= 127.0.0.1
PORT ?= 27962
DEPTH ?= 1
LIMIT ?= 12

.DEFAULT_GOAL := help

##@ Help
## help: Display this informational message
help:
	@printf "  CodeCtx Make Targets  \n"
	@printf "======================\n"
	@awk ' \
		function flush() { \
			if (target == "") return; \
			line = sprintf("  %-16s %s", target, desc); \
			if (options != "") line = line " [" options "]"; \
			printf "%s\n", line; \
			target = ""; \
			desc = ""; \
			options = ""; \
		} \
		/^##@/ {next} \
		/^##   options:/ {pending_options = substr($$0, 15); next} \
		/^## / { \
			line = substr($$0, 4); \
			split(line, parts, ": "); \
			pending_desc = substr(line, length(parts[1]) + 3); \
			next; \
		} \
		/^[a-zA-Z0-9_.-]+:[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/ {next} \
		/^\.(PHONY|DEFAULT_GOAL)/ {next} \
		/^[a-zA-Z0-9_.-]+:/ { \
			flush(); \
			split($$1, parts, ":"); \
			target = parts[1]; \
			desc = pending_desc; \
			options = pending_options; \
			pending_desc = ""; \
			pending_options = ""; \
			next; \
		} \
		END {flush()} \
	' $(MAKEFILE_LIST)

##@ Test
## test: Run the full verification suite
test: unit validate
	@echo "All tests passed!"

## unit: Run Python tests
unit:
	$(PYTEST) -q

## validate: Compile Python modules to catch syntax/import-level issues
validate:
	@echo "Validating Python sources..."
	@python3 -m py_compile \
		cli/__init__.py cli/app.py cli/instructions.py cli/output.py \
		cli/commands/__init__.py cli/commands/context.py cli/commands/eval.py cli/commands/graph.py cli/commands/serve.py \
		core/__init__.py core/models.py core/service.py \
		graph/__init__.py graph/context_graph.py graph/dependency_graph.py graph/incremental_update.py graph/semantic_diff.py \
		server/context_server.py \
		clients/__init__.py clients/context_http.py \
		agents/__init__.py agents/base_agent.py agents/beliefs.py \
		detection/__init__.py detection/context_manager.py detection/invalidation_engine.py \
		experiments/__init__.py experiments/harness.py \
		tests/test_context_http_client.py tests/test_context_server.py \
		main.py

##@ Code Quality
## fmt: Format Python source with Ruff
fmt:
	@echo "Formatting Python files with Ruff..."
	@$(RUFF) format .

## fmt-check: Verify Python formatting with Ruff
fmt-check:
	@echo "Checking Ruff formatting..."
	@$(RUFF) format --check .

## lint: Run Ruff lint checks
lint:
	@echo "Running Ruff..."
	@$(RUFF) check .

##@ Run
## run: Start the context server
##   options: ROOT=., HOST=127.0.0.1, PORT=27962
run:
	$(PYTHON) main.py serve "$(ROOT)" --host "$(HOST)" --port "$(PORT)"

## graph-build: Build the dependency graph and export NDJSON
##   options: ROOT=., OUTPUT=graph.ndjson
graph-build:
	@if [ -n "$(OUTPUT)" ]; then \
		$(PYTHON) main.py graph build "$(ROOT)" --output "$(OUTPUT)"; \
	else \
		$(PYTHON) main.py graph build "$(ROOT)"; \
	fi

## graph-query: Query dependents of a symbol
##   options: ROOT=., SYMBOL=package.module.symbol
graph-query:
	@if [ -z "$(SYMBOL)" ]; then \
		echo "SYMBOL is required"; \
		echo "Usage: make graph-query ROOT=. SYMBOL=package.module.symbol"; \
		exit 1; \
	fi
	$(PYTHON) main.py graph dependents "$(ROOT)" "$(SYMBOL)"

## context-query: Query file, task, or subgraph context
##   options: ROOT=., FILE=..., TASK=..., SYMBOL=..., DEPTH=1, LIMIT=12
context-query:
	@if [ -n "$(FILE)" ]; then \
		$(PYTHON) main.py context file "$(ROOT)" "$(FILE)"; \
	elif [ -n "$(TASK)" ]; then \
		$(PYTHON) main.py context task "$(ROOT)" "$(TASK)" --limit "$(LIMIT)"; \
	elif [ -n "$(SYMBOL)" ]; then \
		$(PYTHON) main.py context symbol "$(ROOT)" "$(SYMBOL)" --depth "$(DEPTH)"; \
	else \
		echo "One of FILE, TASK, or SYMBOL is required"; \
		echo "Usage: make context-query ROOT=. FILE=path/to/file.py"; \
		echo "   or: make context-query ROOT=. TASK='update client' LIMIT=8"; \
		echo "   or: make context-query ROOT=. SYMBOL=package.module.symbol DEPTH=1"; \
		exit 1; \
	fi

## eval: Run reproducible invalidation scenarios
##   options: SCENARIOS="body ctor"
eval:
	@SCENARIOS="$(SCENARIOS)" $(PYTHON) main.py eval $(SCENARIOS)

##@ CI
## ci-local: Run local CI checks
ci-local: fmt-check lint validate test
	@echo "All local CI checks passed!"

##@ Maintenance
## clean: Remove common local caches
clean:
	@echo "Cleaning..."
	@find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	@find . -type d -name '.pytest_cache' -prune -exec rm -rf {} +
	@find . -type d -name '.ruff_cache' -prune -exec rm -rf {} +
	@echo "Clean complete"

## cloc: Count lines of code
cloc:
	@echo "Counting lines of code..."
	@if command -v cloc >/dev/null; then \
		cloc . \
			--fullpath \
			--exclude-dir=.git,.venv,.cache,.pytest_cache,.ruff_cache,__pycache__; \
	else \
		echo "cloc not found - install with: brew install cloc or apt install cloc"; \
		exit 1; \
	fi
