# Context Management

Context discipline drives everything in this architecture. What goes in the context window determines what comes out. What stays out carries little weight regardless of training data.

## Core Principles

- **Fill for relevance, not completeness.** Every item either earns its place (pulling generation toward the task) or competes for attention that should go elsewhere.
- **Context rot** pulls attention sideways — loosely related content steers generation toward adjacent topics rather than the task. It doesn't need to be wrong to cause drift.
- **Context bloat** buries important content — attention concentrates at edges of long windows and thins in the middle. A critical fact at position 40,000 carries a fraction of the weight it would at position 100.

## Subagent Context Isolation

- Each subagent runs in its own context window
- Receives ONLY: the piece file + required inputs
- Returns ONLY: a conclusion (summary finding)
- Intermediate work (tool responses, parse logs, retry traces) stays in the subagent's window and is garbage collected on completion
- The main agent's window accumulates findings, not intermediate state

## Compaction

Over a long session, the window accumulates: tool results, intermediate outputs, recovery traces.

Compaction periodically:
1. Collapses accumulated history into a short digest
2. Archives the full trace to memory
3. Resets the window to digest + current task state
4. Promotes key decisions to top of context (high attention position)

The window after compaction has space for what comes next, and attention reaches what matters.

## Dynamic Assembly

Context is assembled fresh for each task. The relevant pieces, user preferences, retrieved documents, and tool results are chosen for this task — not carried over from previous ones. What the model sees is curated, not accumulated.

## Acceptance Criteria

- Subagent context windows contain only their piece + inputs (verifiable via logging)
- Conclusions returned to main agent are concise summaries, not raw transcripts
- Compaction reduces context size while preserving key decisions
- Post-compaction context maintains enough information for correct continuation
- No cross-contamination between subagent contexts
