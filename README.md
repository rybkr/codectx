# CodeCtx: Context Synchronization for Multi-Agent Workflows

## Code Structure

- `agents/`: Defines the agent context manager and models.
- `benchmarks/`: Defines a harness used for static and deterministic testing.
- `cli/`: Implementation of the CLI.
- `context/`: Defines the context service interface.
- `graph/`: Defines the symbol types and symbol graph.
    - `languages/`: Defines language adapters (Python only for now).
- `invalidation/`: The rules for invalidating symbols based on what changed.
- `main.py`: The entrypoint for the cli.
- `mcp_server/`: Simple MCP server implementation.
- `server/`: Simple HTTP server implementation.
- `tests/`: Symbol graph unit testing.

## Dependencies

Dependencies are managed by `uv`.
They are outlined by `pyproject.toml` and `uv.lock`.

## Getting Started

1. Install dependencies:

```bash
uv sync
```

2. Run the cli:

```bash
uv run main.py --help
```

The `cli` help messages serve as a guide.
