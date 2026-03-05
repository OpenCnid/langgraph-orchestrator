# Implementation Plan — LangGraph Orchestrator

**Status:** Greenfield — no source code, tests, or pyproject.toml exist yet.
**Goal:** Working LangGraph-based subagent spawner + merger implementing the Agent Architecture.

---

## Priority 1 — Project Scaffolding

- [ ] **P1.1 — pyproject.toml + dependencies**: Python 3.11+, langgraph, langchain-core, langchain-openai (or langchain-anthropic), faiss-cpu (or chromadb), pydantic. Dev deps: pytest, pytest-asyncio, mypy, ruff. Package name: `langgraph_orchestrator`. Editable install via `pip install -e ".[dev]"`.
- [ ] **P1.2 — Directory structure**: Create `src/`, `src/lib/`, `src/nodes/`, `tests/`, `pieces/forward/`, `pieces/recovery/`, `pieces/skills/`. Empty `__init__.py` files where needed.
- [ ] **P1.3 — Configuration module** (`src/lib/config.py`): Pydantic settings for confidence thresholds (high, moderate), retry limits, compaction trigger, embedding model name, LLM model name. Loaded from env vars or `.env`.
- [ ] **P1.4 — Minimal CLI runner** (`src/main.py`): Bare-bones CLI that accepts a query and runs the graph. Enables manual testing from P1 onward; full CLI polish deferred to P13.

## Priority 2 — Data Models & Piece Format (specs/atlas.md, specs/skills.md)

- [ ] **P2.1 — Piece data model** (`src/lib/models.py`): Pydantic models for `Piece` (id, compact_identifier, title, type: forward|recovery|skill, status: active|archived|draft, connections: list of piece IDs, response_shapes_handled: list[str] (recovery only), content: str (markdown body with mermaid), metadata). Enums: `PieceType` (forward, recovery, skill), `PieceStatus` (active, archived, draft).
- [ ] **P2.2 — Conclusion model** (`src/lib/models.py`): Pydantic model `Conclusion` with `summary: str`, `status: Literal["success", "partial", "failed", "escalated"]`, `key_outputs: dict[str, Any]`, `diagnostics: str | None`. This is the output contract for piece execution (specs/piece-execution.md).
- [ ] **P2.3 — Routing models** (`src/lib/models.py`): `RoutingDecision` with `mode: Literal["A","B","C","D"]`, `matched_pieces: list[PieceMatch]`, `confidence_scores: dict`, `clarification_prompt: str | None`. `PieceMatch` with `piece_id: str`, `score: float`. `SpawnTask` with `piece_id: str`, `inputs: dict`, `dependencies: list[str]`.
- [ ] **P2.4 — Sample forward piece**: Create `pieces/forward/sample_lookup.md` — a simple mermaid-diagram workflow (e.g., "look up a record by ID"). Include compact identifier, metadata, mermaid diagram.
- [ ] **P2.5 — Sample recovery piece**: Create `pieces/recovery/sample_not_found.md` — handles "no results found" response shape.
- [ ] **P2.6 — Sample skill piece**: Create `pieces/skills/sample_interpretation.md` — domain reasoning for interpreting ambiguous lookup results.

## Priority 3 — Atlas: Piece Registry + Embedding Retrieval (specs/atlas.md)

- [ ] **P3.1 — Atlas store** (`src/atlas.py`): Class `Atlas` that manages pieces — load from `pieces/` directory (all subdirs: forward, recovery, skills), store in memory, CRUD operations. Methods: `add_piece()`, `get_piece(id)`, `list_pieces(type, status)`, `archive_piece(id)`, `promote_draft(id)`.
- [ ] **P3.2 — Embedding index** (`src/lib/embeddings.py`): Embed piece content — compact identifiers + titles + prose description (not just identifiers). Use sentence embeddings (or OpenAI embeddings). Build FAISS index. Method: `search(query, top_k) -> list[(piece_id, score)]`.
- [ ] **P3.3 — Atlas retrieval integration**: Wire `Atlas.search(query)` to embed the query, search FAISS index, return matched pieces with scores. Include type filtering (forward, recovery, skill).
- [ ] **P3.4 — Cascade check** (`src/atlas.py`): When a piece is archived/replaced, traverse `connections` to find dependent pieces (including skills referenced by workflows) and flag them for re-examination.
- [ ] **P3.5 — Tests for atlas**: CRUD, search retrieval (verify compact identifiers improve separability), lifecycle transitions, cascade check, skill storage and retrieval.

## Priority 4 — Router: Mode Classification (specs/routing.md)

- [ ] **P4.1 — Router module** (`src/router.py`): Function `classify_query(query, atlas) -> RoutingDecision`. Uses atlas search scores against configurable thresholds to determine mode A/B/C/D.
  - Single match above high threshold → Mode A (piece_id returned)
  - Multiple matches above moderate threshold → Mode B (piece_ids returned)
  - No match above moderate threshold → Mode C
  - Multiple weak matches across unrelated domains → Mode D
- [ ] **P4.2 — Mode D re-routing**: After human clarification, re-classify with narrowed query. Enforce non-D result (prevent infinite clarification loops).
- [ ] **P4.3 — Tests for router**: Verify classification into all four modes, threshold configurability, Mode D re-routing guard.

## Priority 5 — LangGraph State & Graph Topology

- [ ] **P5.1 — State schema** (`src/lib/state.py`): TypedDict `OrchestratorState` with fields: `query: str`, `routing_decision: RoutingDecision`, `spawn_plan: list[SpawnTask]`, `subagent_conclusions: list[Conclusion]`, `merged_response: str`, `context_digest: str`, `memory_log: list`, `human_input: str | None`.
- [ ] **P5.2 — Main graph** (`src/graph.py`): LangGraph `StateGraph` with nodes: `route`, `execute_a` (Mode A), `plan_b` (Mode B planner), `spawn_b` (Mode B spawner via Send()), `merge_b` (Mode B merger), `draft_c` (Mode C), `clarify_d` (Mode D). Conditional edges from `route` based on mode.
- [ ] **P5.3 — Subagent isolation contract**: Define the boundary — subagents receive ONLY piece file + inputs, return ONLY a Conclusion. This contract must be enforced from the start in P7.3, not deferred.
- [ ] **P5.4 — Tests for graph topology**: Verify routing dispatches to correct node for each mode.

## Priority 6 — Piece Execution Engine (specs/piece-execution.md)

- [ ] **P6.1 — Piece loader** (`src/lib/piece_runner.py`): Parse piece markdown into components: front matter/metadata, mermaid diagram, prose context. Validate active status. Reject invalid pieces.
- [ ] **P6.2 — LLM-based workflow interpreter** (`src/lib/piece_runner.py`): Inject piece content into LLM context. LLM interprets the mermaid diagram as structured instructions, identifies nodes and edges, follows the workflow step by step. Returns a Conclusion.
- [ ] **P6.3 — Execution state**: Per-execution state tracking — node_outputs, current_node, execution_trace, error_state. Fully isolated per execution.
- [ ] **P6.4 — Skill loading**: When a workflow node delegates a decision to the LLM, load the relevant skill(s) from the atlas into context for that decision. Unload after the decision (scoped injection).
- [ ] **P6.5 — Recovery hook stubs**: Define entry points in the execution flow where recovery can intercept (post-tool-response, pre-conclusion). Stubs only — full recovery in P10.
- [ ] **P6.6 — Tests for piece execution**: Piece loading/validation, LLM interpretation of sample workflow, conclusion output contract, skill loading for LLM-bridged nodes.

## Priority 7 — Mode A: Librarian (Direct Execution)

- [ ] **P7.1 — Execute node** (`src/nodes/execute.py`): Loads matched piece via piece runner, injects into LLM context, executes workflow via piece_runner, returns Conclusion.
- [ ] **P7.2 — Tests for Mode A**: End-to-end query → route → execute → Conclusion.

## Priority 8 — Mode B: Orchestrator (Spawner + Merger) (specs/orchestration.md)

- [ ] **P8.1 — Planner node** (`src/nodes/planner.py`): Analyzes query + matched pieces. Determines dependencies (sequential vs parallel). Produces `list[SpawnTask]` where `SpawnTask = {piece_id, inputs, dependencies: list[piece_id]}`.
- [ ] **P8.2 — Spawner node** (`src/nodes/spawner.py`): Uses LangGraph `Send()` for parallel fan-out of independent tasks. For sequential dependencies: chain subgraph invocations with explicit state passing (conclusion of piece A feeds as input to piece B). Each subagent enforces isolation (piece file + inputs only).
- [ ] **P8.3 — Subagent subgraph** (`src/subagent.py`): Isolated `StateGraph` that loads piece via piece_runner, executes it, returns Conclusion. Enforces the isolation contract from P5.3.
- [ ] **P8.4 — Merger node** (`src/nodes/merger.py`): Receives all Conclusions. Synthesizes coherent response. Handles partial failures (some succeed, others fail/escalate).
- [ ] **P8.5 — Contradiction detection** (`src/lib/contradiction.py`): LLM-based check that compares conclusions pairwise for conflicting claims. Returns conflicts found. Merger uses this before finalizing.
- [ ] **P8.6 — Tests for Mode B**: Planner dependency analysis (sequential vs parallel), parallel spawn via Send(), sequential chaining, merger synthesis, contradiction detection, partial failure handling, end-to-end multi-piece query.

## Priority 9 — Mode C: Cartographer (Draft + Halt)

- [ ] **P9.1 — Draft node** (`src/nodes/drafter.py`): When no piece matches, halt execution. Draft what a piece would look like: scope, likely structure, connections to adjacent pieces, piece type (workflow, skill, or recovery). Save as draft piece in atlas.
- [ ] **P9.2 — Tests for Mode C**: Verify halt behavior (no improvisation), draft piece created with correct status.

## Priority 10 — Mode D: Clarifier

- [ ] **P10.1 — Clarify node** (`src/nodes/clarifier.py`): Surface what's needed to route confidently. Generate clarification prompt. Accept human input. Re-route with narrowed query (must not return Mode D again).
- [ ] **P10.2 — Human-in-the-loop integration**: LangGraph interrupt mechanism for awaiting human input during Mode D.
- [ ] **P10.3 — Tests for Mode D**: Clarification prompt generation, re-routing guard, human input flow.

## Priority 11 — Recovery Loops / Anti-Workflows (specs/recovery.md)

- [ ] **P11.1 — Response shape classifier** (`src/lib/response_classifier.py`): Classify tool responses into categories: validation, partial, capacity, constraint, shape_mismatch, unknown. Pydantic model `ResponseShape`.
- [ ] **P11.2 — Recovery executor** (`src/recovery.py`): Wire into piece_runner's recovery hooks (P6.5). When tool returns unexpected response: classify shape → look up recovery piece in atlas → execute recovery piece within subagent context → return to forward loop. If no piece found, trigger Mode C (draft diagnostic).
- [ ] **P11.3 — Retry limit enforcement**: Configurable per-piece or global default (3). On limit reached, return escalated Conclusion with diagnostics — do not loop further.
- [ ] **P11.4 — Tests for recovery**: Shape classification, recovery piece lookup, retry limit enforcement, Mode C fallback for unrecognized shapes, recovery → forward loop resumption end-to-end.

## Priority 12 — Context Management (specs/context-management.md)

- [ ] **P12.1 — Context assembler** (`src/lib/context.py`): Assembles fresh context per task — relevant pieces, skills, user preferences, retrieved docs, tool results. Curated, not accumulated. Integrates with atlas retrieval and memory.
- [ ] **P12.2 — Compaction engine** (`src/lib/compaction.py`): Triggered when context exceeds threshold. Collapses history into short digest. Archives full trace to memory. Resets window to digest + current task state. Promotes key decisions to top of context.
- [ ] **P12.3 — Subagent isolation verification**: Logging-based verification that each subagent receives ONLY piece file + inputs. Conclusions returned are concise summaries. No cross-contamination.
- [ ] **P12.4 — Tests for context**: Compaction reduces size while preserving key decisions. Subagent isolation verified via logging. Context assembly includes skills when relevant.

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
