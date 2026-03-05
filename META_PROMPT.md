Meta-Prompt: LangGraph Orchestrator — Ralph Loop

## What You're Doing

You are running a Ralph Loop on the LangGraph Orchestrator project. This project implements a subagent spawner + merger based on the Agent Architecture spec.

## Source Files

- **Specs:** `specs/*.md` — 6 topic specs (routing, atlas, orchestration, recovery, context-management, memory). Study all of them.
- **Architecture reference:** `spec/agent-architecture.html` — the full source spec. Study the Foundation, Puzzle Pieces, Recovery Loops, Context Engine, Four Modes, Atlas, Memory, and Principles sections for design rationale when needed.
- **AGENTS.md** — build/test/lint commands
- **PROMPT_plan.md** — planning mode prompt (goal already customized)
- **PROMPT_build.md** — building mode prompt

## First Session Instructions

1. Study all specs in `specs/` thoroughly
2. Study `spec/agent-architecture.html` for deeper context on any unclear concepts
3. Run planning mode: `./loop.sh plan`
4. This will generate `IMPLEMENTATION_PLAN.md` from gap analysis of specs vs code
5. Review the plan — then switch to `./loop.sh` for building

## Project Goal

Build a working LangGraph-based subagent spawner + merger that implements:
- Four routing modes (A: Librarian, B: Orchestrator, C: Cartographer, D: Clarifier)
- An atlas of verified puzzle pieces (forward workflows + recovery anti-workflows)
- Isolated subagent execution returning conclusions, not transcripts
- Recovery loops via anti-workflows with retry limits
- Context compaction for long sessions
- Memory/review cycle that grows the atlas over time

## Tech Stack

- Python 3.11+, LangGraph, LangChain, FAISS or ChromaDB, Pydantic
- Tests: pytest · Types: mypy · Lint: ruff

## Constraints

- Subagent isolation is non-negotiable — each gets its own context
- Mode C means HALT — never let the LLM improvise when no piece matches
- The merge is where risk concentrates — test contradiction detection
- Retry limits are mandatory on all recovery loops
