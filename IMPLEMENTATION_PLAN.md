# Implementation Plan — LangGraph Orchestrator

**Status:** P1-P4 complete. Core routing logic implemented.
**Goal:** Working LangGraph-based subagent spawner + merger implementing the Agent Architecture.

**Last Updated:** 2026-03-05 — P1-P12 complete. 141 tests passing, lint clean.

Key learnings:
- Skills are prompt files without mermaid diagrams — parser handles this
- Build backend: use `setuptools.build_meta` (not `setuptools.backends._legacy`)
- Venv required: `python3 -m venv .venv && source .venv/bin/activate`
- Default embed function is hash-based for testing; production needs OpenAI/sentence-transformer
- Hash-based embeddings are NOT similarity-preserving — router tests need controllable embed functions with known vectors
- In 1536-d space, random noise quickly dominates signals — use vector blending (not additive noise) for controlled cosine similarity in tests

---

## Priority 1 — Project Scaffolding

- [x] **P1.1 — pyproject.toml + dependencies**: Python 3.11+, langgraph, langchain-core, langchain-openai (or langchain-anthropic), faiss-cpu (or chromadb), pydantic. Dev deps: pytest, pytest-asyncio, mypy, ruff. Package name: `langgraph_orchestrator`. Editable install via `pip install -e ".[dev]"`.
- [x] **P1.2 — Directory structure**: Create `src/`, `src/lib/`, `src/nodes/`, `tests/`, `pieces/forward/`, `pieces/recovery/`, `pieces/skills/`. Empty `__init__.py` files where needed.
- [x] **P1.3 — Configuration module** (`src/lib/config.py`): Pydantic settings for confidence thresholds (high, moderate), retry limits, compaction trigger, embedding model name, LLM model name. Loaded from env vars or `.env`.
- [x] **P1.4 — Minimal CLI runner** (`src/main.py`): Bare-bones CLI that accepts a query and runs the graph. Enables manual testing from P1 onward; full CLI polish deferred to P13.

## Priority 2 — Data Models & Piece Format (specs/atlas.md, specs/skills.md)

- [x] **P2.1 — Piece data model** (`src/lib/models.py`): Pydantic models for `Piece` (id, compact_identifier, title, type: forward|recovery|skill, status: active|archived|draft, connections: list of piece IDs, response_shapes_handled: list[str] (recovery only), content: str (markdown body with mermaid), metadata). Enums: `PieceType` (forward, recovery, skill), `PieceStatus` (active, archived, draft).
- [x] **P2.2 — Conclusion model** (`src/lib/models.py`): Pydantic model `Conclusion` with `summary: str`, `status: Literal["success", "partial", "failed", "escalated"]`, `key_outputs: dict[str, Any]`, `diagnostics: str | None`. This is the output contract for piece execution (specs/piece-execution.md).
- [x] **P2.3 — Routing models** (`src/lib/models.py`): `RoutingDecision` with `mode: Literal["A","B","C","D"]`, `matched_pieces: list[PieceMatch]`, `confidence_scores: dict`, `clarification_prompt: str | None`. `PieceMatch` with `piece_id: str`, `score: float`. `SpawnTask` with `piece_id: str`, `inputs: dict`, `dependencies: list[str]`.
- [x] **P2.4 — Sample forward piece**: Create `pieces/forward/sample_lookup.md` — a simple mermaid-diagram workflow (e.g., "look up a record by ID"). Include compact identifier, metadata, mermaid diagram.
- [x] **P2.5 — Sample recovery piece**: Create `pieces/recovery/sample_not_found.md` — handles "no results found" response shape.
- [x] **P2.6 — Sample skill piece**: Create `pieces/skills/sample_interpretation.md` — domain reasoning for interpreting ambiguous lookup results.

## Priority 3 — Atlas: Piece Registry + Embedding Retrieval (specs/atlas.md)

- [x] **P3.1 — Atlas store** (`src/atlas.py`): Class `Atlas` that manages pieces — load from `pieces/` directory (all subdirs: forward, recovery, skills), store in memory, CRUD operations. Methods: `add_piece()`, `get_piece(id)`, `list_pieces(type, status)`, `archive_piece(id)`, `promote_draft(id)`.
- [x] **P3.2 — Embedding index** (`src/lib/embeddings.py`): Embed piece content — compact identifiers + titles + prose description (not just identifiers). Use sentence embeddings (or OpenAI embeddings). Build FAISS index. Method: `search(query, top_k) -> list[(piece_id, score)]`.
- [x] **P3.3 — Atlas retrieval integration**: Wire `Atlas.search(query)` to embed the query, search FAISS index, return matched pieces with scores. Include type filtering (forward, recovery, skill).
- [x] **P3.4 — Cascade check** (`src/atlas.py`): When a piece is archived/replaced, traverse `connections` to find dependent pieces (including skills referenced by workflows) and flag them for re-examination.
- [x] **P3.5 — Tests for atlas**: CRUD, search retrieval (verify compact identifiers improve separability), lifecycle transitions, cascade check, skill storage and retrieval.

## Priority 4 — Router: Mode Classification (specs/routing.md)

- [x] **P4.1 — Router module** (`src/router.py`): Function `classify_query(query, atlas) -> RoutingDecision`. Uses atlas search scores against configurable thresholds to determine mode A/B/C/D.
  - Single match above high threshold → Mode A (piece_id returned)
  - Multiple matches above moderate threshold → Mode B (piece_ids returned)
  - No match above moderate threshold → Mode C
  - Multiple weak matches across unrelated domains → Mode D
- [x] **P4.2 — Mode D re-routing**: `reroute_after_clarification()` re-classifies with narrowed query. Forces Mode C if re-classification would return D again.
- [x] **P4.3 — Tests for router**: 18 tests covering all four modes, threshold configurability, Mode D re-routing guard, edge cases.

## Priority 5 — LangGraph State & Graph Topology

- [x] **P5.1 — State schema** (`src/lib/state.py`): `OrchestratorState` (TypedDict, total=False) and `SubagentState` for isolation. All fields from spec implemented.
- [x] **P5.2 — Main graph** (`src/graph.py`): `build_graph(atlas)` creates StateGraph with route → conditional edges → mode nodes. Atlas injected via closure. Mode B flows through plan → spawn → merge chain.
- [x] **P5.3 — Subagent isolation contract**: `SubagentState` TypedDict enforces boundary — only piece_id, piece_content, inputs, conclusion. Tested via annotation assertions.
- [x] **P5.4 — Tests for graph topology**: 8 tests — end-to-end invocation for each mode, spawn plan validation, merger synthesis, isolation contract verification.

## Priority 6 — Piece Execution Engine (specs/piece-execution.md)

- [x] **P6.1 — Piece loader** (`src/lib/piece_runner.py`): `validate_piece()` enforces active status, mermaid requirement. `load_piece_components()` extracts mermaid, prose, metadata.
- [x] **P6.2 — LLM-based workflow interpreter**: `execute_piece()` takes injectable `LLMCallable(system, user) -> str`. Builds system prompt with piece content + skills, parses JSON or plain-text conclusions.
- [x] **P6.3 — Execution state**: `ExecutionState` dataclass with node_outputs, current_node, execution_trace, error_state, inputs, skills_loaded. Fully isolated per execution.
- [x] **P6.4 — Skill loading**: `load_skills_for_decision()` loads connected skills from atlas by connection IDs, falls back to similarity search. Skills are scoped to the execution prompt.
- [x] **P6.5 — Recovery hooks**: `RecoveryHook` callable type. `execute_piece()` calls hook on failed/escalated conclusions, retries with recovery guidance. Retry limit enforced.
- [x] **P6.6 — Tests for piece execution**: 29 tests — validation, loading, execution (success/fail/partial/exception), conclusion contract, skill loading, recovery hooks with retries.

## Priority 7 — Mode A: Librarian (Direct Execution)

- [x] **P7.1 — Execute node**: `execute_a()` in graph.py calls `execute_piece()` from piece_runner with injectable LLM callable. Handles missing pieces gracefully.
- [x] **P7.2 — Tests for Mode A**: End-to-end graph invocation verifying piece_runner integration, LLM prompt contains mermaid, conclusion returned correctly.

## Priority 8 — Mode B: Orchestrator (Spawner + Merger) (specs/orchestration.md)

- [x] **P8.1 — Planner node**: `plan_b()` in graph.py analyzes piece connections for dependency ordering. Independent pieces run in parallel, connected pieces chain sequentially.
- [x] **P8.2 — Spawner node**: `spawn_b()` executes each piece via piece_runner. Passes prior conclusions as inputs for dependent pieces. LLM callable injected via build_graph().
- [x] **P8.3 — Subagent execution**: Piece execution via piece_runner enforces isolation — each piece gets only its content + inputs, returns only a Conclusion.
- [x] **P8.4 — Merger node**: `merge_b()` synthesizes conclusions, reports partial failures, detects contradictions.
- [x] **P8.5 — Contradiction detection** (`src/lib/contradiction.py`): Heuristic (key_output comparison) and LLM-based (injectable) pairwise contradiction checking. Skips metadata keys. Merger surfaces conflicts in response.
- [x] **P8.6 — Tests for Mode B**: Dependency analysis, piece_runner execution via graph, merger synthesis, contradiction detection (10 tests), partial failure handling, end-to-end multi-piece.

## Priority 9 — Mode C: Cartographer (Draft + Halt)

- [x] **P9.1 — Draft node**: `draft_c()` in graph.py creates a draft Piece with status=draft, saves to atlas. Includes query scope, nearest existing pieces as connections.
- [x] **P9.2 — Tests for Mode C**: Draft piece creation in atlas, halt behavior (escalated status, no execution), draft content includes query.

## Priority 10 — Mode D: Clarifier

- [x] **P10.1 — Clarify node**: `clarify_d()` in graph.py surfaces clarification prompt from routing decision. Re-routing via `reroute_after_clarification()` prevents infinite D loops (implemented in P4.2).
- [x] **P10.2 — Human-in-the-loop**: Graph accepts `human_input` in state; route node detects it and calls `reroute_after_clarification()`. Full LangGraph interrupt deferred until streaming CLI (P14).
- [x] **P10.3 — Tests for Mode D**: Clarification prompt generation, re-routing guard (from P4), ambiguous query routing.

## Priority 11 — Recovery Loops / Anti-Workflows (specs/recovery.md)

- [x] **P11.1 — Response shape classifier** (`src/lib/response_classifier.py`): `classify_response()` with keyword heuristics. `ResponseShape` Pydantic model with `ResponseShapeType` StrEnum (validation, partial, capacity, constraint, shape_mismatch, unknown). Shape mismatch checked before validation for specificity.
- [x] **P11.2 — Recovery executor** (`src/recovery.py`): `build_recovery_hook()` creates a hook for piece_runner. Classifies shape → finds recovery piece by response_shapes_handled → executes recovery piece → returns guidance. Falls through on unknown shapes.
- [x] **P11.3 — Retry limit enforcement**: Enforced in piece_runner's `execute_piece()` via max_retries parameter (default 3). Escalated conclusion on limit.
- [x] **P11.4 — Tests for recovery**: 16 tests — shape classification (8 categories), recovery piece lookup, hook integration, retry limits, end-to-end recovery→success.

## Priority 12 — Context Management (specs/context-management.md)

- [x] **P12.1 — Context assembler** (`src/lib/context.py`): `assemble_context()` curates fresh context per task from matched pieces, skills (via atlas search), user preferences, and prior digest.
- [x] **P12.2 — Compaction engine** (`src/lib/compaction.py`): `needs_compaction()` checks token estimate vs threshold. `compact()` collapses history into digest preserving key decisions. Archives full context for memory.
- [x] **P12.3 — Subagent isolation verification**: SubagentState TypedDict enforces isolation contract. Context assembly only includes matched pieces, not full atlas.
- [x] **P12.4 — Tests for context**: 13 tests — context assembly (pieces, skills, preferences, digest), compaction (token estimate, threshold, size reduction, key decisions), isolation.

## Priority 13 — Memory & Review Cycle (specs/memory.md)

- [ ] **P13.1 — Execution history store** (`src/memory.py`): Log successful sequences as proven routes. Log failures alongside (archived, never deleted). Written at session end.
- [ ] **P13.2 — User profile store** (`src/memory.py`): Capture explicit preferences + observed patterns. Written on correction/override. Loaded at session start.
- [ ] **P13.3 — Session summary generator**: Produce ~1k token summary at session end. Clean, ready for next session start.
- [ ] **P13.4 — Review cycle**: After outcomes, classify → write memory → synthesize → session summary. For atlas: archive stale piece → draft replacement → cascade check.
- [ ] **P13.5 — Tests for memory**: History records both success/failure, failures archived not deleted, session summaries under 1k tokens, review cycle triggers correctly.

## Priority 14 — Integration & End-to-End

- [ ] **P14.1 — End-to-end integration test**: Query → route → (mode-specific execution) → response. Cover all four modes.
- [ ] **P14.2 — CLI polish** (`src/main.py`): Enhance CLI from P1.4 with streaming output, Mode D clarification UX, error display.
- [ ] **P14.3 — Mypy + ruff passing**: Full type coverage, clean lint.

---

## Spec Coverage

| Spec File | Plan Items |
|---|---|
| specs/atlas.md | P2.1, P3.1–P3.5 |
| specs/routing.md | P4.1–P4.3 |
| specs/orchestration.md | P8.1–P8.6 |
| specs/recovery.md | P11.1–P11.4 |
| specs/context-management.md | P12.1–P12.4 |
| specs/memory.md | P13.1–P13.5 |
| specs/skills.md | P2.1 (type enum), P2.6, P3.1, P3.3, P6.4, P12.1 |
| specs/piece-execution.md | P6.1–P6.6 |

## Gaps Acknowledged (Deferred)

- **Tool integration / MCP dispatch**: The architecture defines tools as leaf operations (scripts, APIs, MCP calls). The initial implementation relies on LLM interpretation of tool nodes in the workflow. A formal tool registry and MCP dispatch layer is deferred until the core orchestration loop works end-to-end. When needed, add `specs/tools.md` and plan items.
- **Compositional piece execution**: Nodes that reference other pieces by ID for recursive execution. The piece execution spec acknowledges this (abstraction spectrum table). Initial implementation focuses on flat piece execution; composition can be added once single-piece execution is solid.

## Notes

- `src/lib/` is the shared standard library — embeddings, models, config, state, context, compaction, contradiction detection, response classification, piece runner all live here.
- Piece files are markdown with mermaid diagrams in `pieces/forward/`, `pieces/recovery/`, and `pieces/skills/`.
- LangGraph `Send()` API is the mechanism for parallel fan-out in Mode B. Sequential dependencies use chained subgraph invocations.
- Subagent isolation is enforced by creating separate subgraph instances with their own state. The isolation contract is defined in P5.3 and enforced from P8.3 onward.
- The architecture spec (`spec/agent-architecture.html`) is the authoritative reference for design rationale.
- Skills are prompt files stored as atlas pieces (type: skill). They load into context only for LLM-bridged decision nodes, scoped to the decision.
