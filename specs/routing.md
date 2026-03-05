# Routing — Mode Classification

The router classifies each incoming query into one of four modes based on atlas retrieval confidence.

## Modes

| Mode | Name | Trigger | Behavior |
|------|------|---------|----------|
| A | Librarian | Single piece matches with high confidence | Inject piece, execute directly |
| B | Orchestrator | Multiple pieces match, or query spans parallel branches | Spawn subagent per piece, merge conclusions |
| C | Cartographer | No piece matches with sufficient confidence | Halt, draft what a piece would look like, do NOT improvise |
| D | Clarifier | Query is too broad/ambiguous to route confidently | Surface what's needed, ask human, re-route once narrowed |

## Confidence Scoring

- Query is embedded and compared against atlas pieces via similarity search
- Thresholds determine mode:
  - Single match above high threshold → Mode A
  - Multiple matches above moderate threshold → Mode B
  - No match above moderate threshold → Mode C
  - Multiple weak matches across unrelated domains → Mode D
- Thresholds should be configurable

## Mode D Re-routing

After the human provides clarification, the router re-classifies with the narrowed query. The re-route can land on A, B, or C — never back to D (prevent infinite clarification loops).

## Acceptance Criteria

- Router correctly classifies queries into all four modes
- Confidence thresholds are configurable
- Mode D re-routing produces a non-D classification
- Classification latency is under 500ms for typical queries
