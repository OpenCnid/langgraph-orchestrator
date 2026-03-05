# Meta-Prompt: Build the Subagent Spawner + Merger in LangGraph

## What You're Building

A LangGraph implementation of the **Mode B Orchestrator** from the Agent Architecture spec. This is the system that takes a query, identifies which puzzle pieces (workflows/skills) apply, spawns isolated subagents — one per piece — collects their conclusions (not transcripts), and merges findings into a coherent response.

The full architecture spec is at: `projects/langgraph-orchestrator/spec/agent-architecture.html`

**Study it.** The HTML contains 8 tabs: Foundation, Puzzle Pieces, Recovery Loops, Context Engine, Four Modes, The Atlas, Memory, and Principles. All are relevant, but the critical sections for this build are:

- **Four Modes tab → Mode B (The Orchestrator)** — the core pattern you're implementing
- **Context Engine tab → Subagents Keep the Main Window Clean** — why each subagent gets isolated context
- **Puzzle Pieces tab → Composition** — how pieces nest and relate
- **Recovery Loops tab → The Ralph Loop** — forward + recovery channels
- **Principles tab → Principles 1-3** — context relevance, signal visibility, risk at generated joints

## Architecture Overview

```
Query → Router → Planner → [Spawn Subagents] → [Collect Conclusions] → Merger → Response
                    ↓              ↓                     ↓
              Mode Selection   1 per piece         Conclusions only
              (A/B/C/D)       Isolated context     No transcripts
```

### The Four Modes (implement all, B is primary)

| Mode | Name | When | What happens |
|------|------|------|-------------|
| **A** | Librarian | Single piece matches with high confidence | Inject piece, execute directly — no subagent spawn needed |
| **B** | Orchestrator | Multiple pieces or parallel branches | Planner identifies pieces → spawns subagent per piece → merge conclusions |
| **C** | Cartographer | No piece matches with enough confidence | Halt, draft what a piece might look like — do NOT improvise |
| **D** | Clarifier | Query is too broad to route | Surface what's needed to route, ask human, then re-route to A/B/C |

### Core Concepts from the Spec

**Pieces** are the atomic building blocks — markdown files containing mermaid diagrams that serve as both documentation and executable instructions. Two kinds:
- **Forward pieces** (workflows): the intended path
- **Recovery pieces** (anti-workflows): what to do when a tool returns something unexpected

**The Atlas** is the collection of all verified pieces. It grows over time through the review cycle. Gaps in the atlas are meaningful — they show where coverage should grow.

**Context discipline** is the single most important principle:
- Main agent = scheduler only. Never burn main context on work.
- Subagents = memory extension. Each gets its own context window (~156KB), garbage collected on completion.
- Conclusions, not transcripts. Subagents return findings, not intermediate state.
- Context rot (loosely related content steering generation sideways) is as dangerous as context bloat.

**The merge is where risk concentrates.** Each subagent runs verified pieces; the unverified part is whatever the agent generates to connect their conclusions. This is Principle 3: "The Generated Parts Carry the Risk."

**Retry limits.** Each recovery loop adds to the context window. Cap retry cycles before escalating. Set in metaprompt or code.

## Implementation Plan

### Phase 1: Core Graph Structure

Build the LangGraph state machine with these nodes:

1. **Router** — Classifies incoming query into Mode A/B/C/D
   - Uses confidence scoring against the atlas (piece registry)
   - High confidence single match → A
   - Multiple matches or parallel branches → B
   - No match → C
   - Ambiguous/broad → D

2. **Planner** (Mode B path) — Identifies which pieces apply to the query
   - Determines piece dependencies (sequential vs parallel)
   - Plans the spawn: which subagents, what inputs each receives
   - Outputs a spawn plan: `[{piece_id, inputs, dependencies}]`

3. **Spawner** — Executes the spawn plan
   - Creates isolated subagent per piece (LangGraph subgraph or `Send()` API)
   - Each subagent receives ONLY: the piece file + its required inputs
   - Subagents run in parallel where no dependencies exist
   - Sequential where outputs chain

4. **Collector** — Gathers subagent conclusions
   - Waits for all subagents to complete (or timeout)
   - Receives conclusions only — no intermediate state, no tool call logs
   - Handles partial failures (some subagents succeed, others fail)

5. **Merger** — Synthesizes conclusions into response
   - This is the unverified joint — handle with care
   - Cross-checks for contradictions between conclusions (Self-Contradiction failure mode)
   - Produces the final response

6. **Recovery Handler** — When a subagent hits an unexpected tool response
   - Looks up recovery piece (anti-workflow) in atlas
   - If found: run recovery piece, return to forward loop
   - If not found: Mode C — halt, draft diagnostic, escalate
   - Retry limit enforced

### Phase 2: Piece Registry (Atlas)

The atlas is the piece store. For this implementation:

```python
# Each piece is a markdown file with:
# - Compact identifier (emoji + structured marker)
# - Mermaid diagram (the workflow)
# - Metadata: type (forward/recovery), connections, response shapes handled
# - Embedding for retrieval

@dataclass
class Piece:
    id: str                    # Compact identifier
    name: str                  # Human-readable name
    type: Literal["forward", "recovery"]
    markdown: str              # The full piece content
    embedding: list[float]     # For retrieval
    connections: list[str]     # IDs of connected pieces
    response_shapes: list[str] # What tool response shapes this handles (recovery only)
    status: Literal["active", "archived", "draft"]
```

Retrieval: Use embedding similarity with a confidence threshold. Emoji/structured markers occupy sparse regions in embedding space — this keeps similarly-described pieces separable.

### Phase 3: State Schema

```python
class OrchestratorState(TypedDict):
    query: str                           # Incoming query
    mode: Literal["A", "B", "C", "D"]   # Classified mode
    matched_pieces: list[Piece]          # Pieces matched by router
    spawn_plan: list[SpawnTask]          # Planner output
    conclusions: dict[str, Conclusion]   # Subagent findings
    recovery_attempts: dict[str, int]    # Retry counters per subagent
    final_response: str                  # Merged output
    draft_pieces: list[dict]             # Mode C drafts
    clarification_needed: str            # Mode D question for human
```

### Phase 4: Mode Implementations

**Mode A (Librarian):** Single piece → inject into context → execute → return result. Simplest path. No subagent needed.

**Mode B (Orchestrator):** The primary build target.
- Planner analyzes query against matched pieces
- Spawns subagents using LangGraph's `Send()` for parallel fan-out
- Each subagent is a subgraph that loads one piece and executes it
- Merger receives conclusions and synthesizes

**Mode C (Cartographer):** No matching piece → halt → draft what the piece would look like (scope, structure, connections to adjacent pieces) → return draft for human review. Never improvise.

**Mode D (Clarifier):** Query too broad → generate clarifying question → wait for human input → re-route to A/B/C with narrowed query.

### Phase 5: Recovery Loop Integration

When a tool call within a subagent returns an unexpected response:

1. Classify the response shape (validation error, partial result, rate limit, constraint, shape mismatch, unknown)
2. Look up matching recovery piece in atlas
3. If found: execute recovery piece within the subagent's context
4. If not found: trigger Mode C within that subagent — draft what a recovery piece should look like
5. Enforce retry limit (configurable, default 3)
6. On limit reached: escalate, do not loop

### Phase 6: Compaction

For long-running sessions:
- Periodically collapse accumulated context into a short digest
- Archive full trace to memory
- Reset window to digest + current task state
- Key decisions promoted to top of context (high attention position)

## Tech Stack

- **LangGraph** — Core graph framework
- **Python 3.11+** — Implementation language
- **LangChain** — LLM integration, tool definitions
- **FAISS or ChromaDB** — Atlas piece retrieval (embedding store)
- **Pydantic** — State and piece schema validation

## Key Constraints

1. **Subagent isolation is non-negotiable.** Each subagent gets its own context. No shared mutable state during execution. Communicate only through the spawn plan (inputs) and conclusions (outputs).

2. **Conclusions, not transcripts.** A subagent returns "retrieved 4 records, Q3 flagged" — not the full API response, parse log, or schema trace.

3. **The merge is the risk point.** Test it. The merger is where self-contradiction sneaks in. Each conclusion may be individually valid but conflicting when combined.

4. **Mode C means HALT.** When no piece matches, do not let the LLM improvise. Draft what the piece would look like, surface it for review. This is the safety boundary.

5. **Retry limits are mandatory.** Every recovery loop adds tokens. Cap it. Default 3, configurable per piece.

6. **Context relevance over completeness.** (Principle 1) Don't load everything. Load what this specific task needs. Every item either earns its place or competes for attention.

7. **Pieces are prompt files; tools are code.** (Principle 6) Workflows live in markdown. Tool calls live in code. Don't mix these layers.

## File Structure

```
projects/langgraph-orchestrator/
├── spec/
│   └── agent-architecture.html    # Source spec (the HTML file)
├── src/
│   ├── graph/
│   │   ├── orchestrator.py        # Main LangGraph graph
│   │   ├── router.py              # Mode classification (A/B/C/D)
│   │   ├── planner.py             # Piece selection + spawn planning
│   │   ├── spawner.py             # Subagent creation + fan-out
│   │   ├── merger.py              # Conclusion synthesis
│   │   └── recovery.py            # Recovery loop handler
│   ├── atlas/
│   │   ├── registry.py            # Piece storage + retrieval
│   │   ├── piece.py               # Piece data model
│   │   └── embeddings.py          # Embedding + similarity search
│   ├── state/
│   │   └── schema.py              # State definitions (Pydantic)
│   ├── subagent/
│   │   ├── runner.py              # Subagent execution subgraph
│   │   └── compaction.py          # Context compaction logic
│   └── memory/
│       ├── execution_history.py   # What worked / what broke
│       └── review_cycle.py        # Post-session piece updates
├── pieces/                         # Atlas piece files (markdown)
│   ├── forward/                    # Forward workflow pieces
│   └── recovery/                   # Anti-workflow pieces
├── tests/
│   ├── test_router.py
│   ├── test_planner.py
│   ├── test_spawner.py
│   ├── test_merger.py
│   └── test_recovery.py
├── AGENTS.md                       # Operational guide
├── IMPLEMENTATION_PLAN.md          # Task tracking
└── specs/
    ├── orchestrator.md             # Mode B orchestration spec
    ├── atlas.md                    # Piece registry spec
    ├── recovery.md                 # Recovery loop spec
    └── context.md                  # Context management spec
```

## Build Order

1. State schema + piece data model
2. Atlas registry (piece storage + retrieval with embeddings)
3. Router (mode classification)
4. Mode A (simplest path — single piece execution)
5. Planner (piece selection + spawn planning for Mode B)
6. Spawner + Subagent runner (LangGraph subgraph + Send() fan-out)
7. Merger (conclusion synthesis with contradiction detection)
8. Recovery handler (anti-workflow execution + retry limits)
9. Mode C (draft generation when no piece matches)
10. Mode D (clarification loop)
11. Compaction (context summarization for long sessions)
12. Memory / review cycle (post-session atlas updates)

## What Success Looks Like

A query enters. The router classifies it. If Mode B: the planner picks pieces from the atlas, the spawner fans out isolated subagents, each runs its piece and returns a conclusion, the merger synthesizes them into a response. If a subagent hits an unexpected tool response, the recovery handler finds the right anti-workflow and heals the loop. If no recovery piece exists, Mode C kicks in and drafts one for review. The atlas grows with each session. Context stays lean throughout.

---

*Source: Agent Architecture spec by Cnid — projects/langgraph-orchestrator/spec/agent-architecture.html*
