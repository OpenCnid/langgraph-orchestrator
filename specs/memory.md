# Memory — Execution History and Review Cycle

Memory loads into the context window at session start. It captures two kinds of signal: what worked/broke (execution history) and how the user prefers to work (user profile).

## Execution History

- Successful sequences logged as proven routes with enough context to recognize similar situations later
- Failures logged alongside successes — wrong pieces, broken joints, coverage gaps
- Failures are **archived, never deleted** — a removed failure record means the system encounters the same situation with no warning

Written at session end — both success and failure.

## User Profile

Captures two things:
- **Explicit preferences** stated by the user
- **Patterns observed** across sessions (output style, interaction pacing, confirmation behavior)

Written on correction, override, or observed pattern. Loads at session start so the agent calibrates without re-asking.

## The Review Cycle

After any outcome, the same question applies: was this a one-off, or does something need updating?

1. **Classify** — success or failure? Calibrate or flag?
2. **Write memory** — domain store, conservatively
3. **Synthesize** — distill across all history
4. **Session summary** — ~1k tokens, clean, ready for next session start

For the atlas:
1. **Archive stale piece** — not deleted, failure info preserved
2. **Draft replacement** — scope, structure, connections
3. **Atlas updated** — replacement filed, cascade check on dependent pieces

This cycle drives atlas evolution. Day 1 → Day 30 → Day 100 coverage growth comes from these review passes.

## Acceptance Criteria

- Execution history records both successes and failures with enough context for pattern recognition
- Failures are archived, never deleted
- Session summaries are under 1k tokens and sufficient for session start context
- Review cycle correctly triggers piece archival and replacement drafting
- Atlas cascade check fires when a piece is updated/replaced
