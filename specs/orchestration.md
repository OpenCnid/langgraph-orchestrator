# Orchestration — Subagent Spawner + Merger (Mode B)

The primary build target. When a query requires multiple pieces or parallel branches, the orchestrator plans the work, spawns isolated subagents, and merges their conclusions.

## Planner

- Analyzes the query against matched pieces from the router
- Determines piece dependencies: which are sequential (output of A feeds B) vs parallel (independent)
- Produces a spawn plan: `[{piece_id, inputs, dependencies}]`
- Does NOT execute — planning only

## Spawner

- Executes the spawn plan
- Creates one subagent per piece using LangGraph's `Send()` API for parallel fan-out, or subgraphs for sequential chains
- **Isolation is non-negotiable:** each subagent receives ONLY the piece file and its required inputs — nothing else from the main context
- Parallel branches run concurrently where no dependencies exist
- Sequential chains pass conclusions forward

## Subagent Execution

Each subagent:
1. Loads its assigned piece (markdown with mermaid diagram)
2. Executes the workflow defined in the piece
3. Returns a **conclusion** — a summary finding, not a transcript
4. Example: "retrieved 4 records, Q3 flagged" — NOT the full API response, parse log, or schema trace

This is critical for context discipline. The main agent's window accumulates findings, not the intermediate state each piece generates.

## Merger

- Receives all subagent conclusions
- Synthesizes into a coherent response
- **This is where risk concentrates** (Principle 3: The Generated Parts Carry the Risk)
- Must cross-check for contradictions between conclusions (Self-Contradiction failure mode from the spec)
- Handles partial failures: some subagents succeed, others fail or timeout

## Acceptance Criteria

- Planner correctly identifies sequential vs parallel piece dependencies
- Subagents execute in true isolation (no shared mutable state during execution)
- Conclusions are summaries, not raw transcripts
- Merger detects contradictions between conclusions
- Partial failures (some subagents fail) produce graceful degraded responses
- End-to-end: query → plan → spawn → collect → merge → response works for a multi-piece query
