## Build & Run

- Python 3.11+
- Venv setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Build backend is `setuptools.build_meta` (not `setuptools.backends._legacy`)
- Source code in `src/`
- Shared utilities in `src/lib/`

## Validation

Run these after implementing to get immediate feedback:

- Tests: `python -m pytest tests/ -v`
- Typecheck: `python -m mypy src/`
- Lint: `python -m ruff check src/ tests/`

## Operational Notes

- LangGraph is the core framework — use `StateGraph`, `Send()` for fan-out, subgraphs for isolated subagent execution
- Piece files live in `pieces/forward/` and `pieces/recovery/` as markdown
- The source architecture spec is at `spec/agent-architecture.html` — study it for detailed design rationale
- The META_PROMPT.md in project root has additional implementation context

### Codebase Patterns

- State schemas use `TypedDict` (LangGraph convention)
- Pydantic for piece data models and validation
- FAISS or ChromaDB for atlas embedding store
