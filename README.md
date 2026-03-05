# LangGraph Orchestrator

A LangGraph-based autonomous orchestrator that routes queries through verified workflow "pieces," spawns isolated sub-agents, merges their outputs, and grows its knowledge base over time.

Built with the [Ralph Loop](https://github.com/OpenCnid/langgraph-orchestrator/blob/master/loop.sh) — an iterative autonomous coding loop where an LLM agent plans and builds from specs, one task per iteration.

## How It Works

The orchestrator classifies every incoming query into one of four modes:

| Mode | Role | What Happens |
|------|------|-------------|
| **A — Librarian** | Direct execution | Single verified piece matches → execute it |
| **B — Orchestrator** | Multi-piece coordination | Multiple pieces match → plan dependencies, spawn sub-agents in parallel/sequence, merge results |
| **C — Cartographer** | Draft & halt | No piece matches → draft a new piece, **halt** (never improvise) |
| **D — Clarifier** | Disambiguation | Ambiguous query → ask for clarification, re-route |

### Key Concepts

- **Pieces** — Markdown files with Mermaid diagrams describing workflows. Three types: forward (do something), recovery (handle failures), and skills (domain reasoning).
- **Atlas** — A registry of all pieces with embedding-based retrieval (FAISS). Supports CRUD, lifecycle transitions, and cascade checks when pieces change.
- **Sub-agent Isolation** — Each spawned sub-agent gets only its piece content and inputs. Returns a structured `Conclusion`, never a raw transcript.
- **Recovery Loops** — Failed executions trigger anti-workflows matched by response shape (validation errors, capacity limits, shape mismatches, etc.). Retry limits are mandatory.
- **Context Compaction** — Long sessions get compacted into digests preserving key decisions, keeping context windows manageable.
- **Memory** — Execution history (successes and failures both logged), user preferences, and session summaries persist across runs.

## Architecture

```
Query → Router → Mode Classification
                    ├─ A: execute_piece()
                    ├─ B: plan → spawn (parallel/sequential) → merge
                    ├─ C: draft_piece() → HALT
                    └─ D: clarify → re-route
```

The LangGraph state machine manages transitions. Mode B uses `Send()` for parallel fan-out and chained subgraph invocations for sequential dependencies. Contradiction detection runs during merge (heuristic + LLM-based).

## Project Structure

```
src/
├── main.py                  # CLI entry point
├── graph.py                 # LangGraph state machine & mode nodes
├── router.py                # Query → Mode classification
├── atlas.py                 # Piece registry + FAISS retrieval
├── recovery.py              # Recovery hook builder
├── memory.py                # Execution history & user profiles
└── lib/
    ├── models.py            # Pydantic models (Piece, Conclusion, RoutingDecision)
    ├── state.py             # OrchestratorState & SubagentState
    ├── config.py            # Pydantic settings (thresholds, models, retries)
    ├── embeddings.py        # Embedding index (FAISS)
    ├── piece_parser.py      # Markdown + Mermaid piece parser
    ├── piece_runner.py      # Piece execution engine
    ├── context.py           # Context assembly per task
    ├── compaction.py         # Token-aware context compaction
    ├── contradiction.py     # Pairwise contradiction detection
    └── response_classifier.py  # Response shape classification

pieces/
├── forward/                 # Forward workflow pieces
├── recovery/                # Recovery anti-workflow pieces
└── skills/                  # Domain reasoning pieces

specs/                       # Design specs (8 topic specs)
spec/                        # Source architecture reference
tests/                       # 163 tests
```

## Quick Start

```bash
# Requires Python 3.11+
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run the orchestrator
orchestrator "look up record 42"

# Run tests
pytest

# Type check & lint
mypy src/
ruff check src/
```

## The Ralph Loop

This project was built entirely by an autonomous LLM agent using the Ralph Loop pattern:

1. **Plan** — Agent reads all specs, analyzes gaps, produces a prioritized implementation plan
2. **Build** — Agent picks the next priority, implements it, runs tests, commits
3. **Loop** — Repeat until all priorities are complete

The loop script (`loop.sh`) drives iterations with configurable modes:

```bash
./loop.sh plan    # Planning mode — gap analysis → IMPLEMENTATION_PLAN.md
./loop.sh         # Build mode — pick next priority, implement, test, commit
./loop.sh 10      # Build mode, max 10 iterations
```

12 iterations took the project from empty directory to 163 passing tests across all 14 priorities.

## Specs

The design is driven by 8 topic specs covering the full architecture:

| Spec | Covers |
|------|--------|
| `specs/routing.md` | Mode classification, thresholds, re-routing |
| `specs/atlas.md` | Piece registry, embeddings, lifecycle, cascades |
| `specs/orchestration.md` | Spawn planning, parallel/sequential execution, merge |
| `specs/piece-execution.md` | Piece loading, LLM interpretation, conclusion contract |
| `specs/recovery.md` | Response shapes, anti-workflows, retry limits |
| `specs/context-management.md` | Context assembly, compaction, isolation |
| `specs/memory.md` | Execution history, user profiles, session summaries |
| `specs/skills.md` | Skill pieces, scoped loading, prompt integration |

## Tech Stack

- **Python 3.11+**
- **LangGraph** — State machine orchestration
- **LangChain** — LLM abstraction layer
- **FAISS** — Vector similarity search for piece retrieval
- **Pydantic** — Data models and settings
- **pytest** — 163 tests covering all modes, recovery, context, memory

## License

MIT
