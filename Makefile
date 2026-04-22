.PHONY: help test fmt lint clean cloc

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
	@printf "                 CodeCtx Make Targets                 \n"
	@printf "======================================================\n"
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

## test: Run the full verification suite
test:
	$(PYTEST) -vs
	@echo "All tests passed!"

## fmt: Format Python source with Ruff
fmt:
	@echo "Formatting Python files with Ruff..."
	@$(RUFF) format .

## lint: Run Ruff lint checks
lint:
	@echo "Running Ruff..."
	@$(RUFF) check .

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
