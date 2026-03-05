# 🧠 Ambiguous Result Interpretation

**Type:** skill
**Status:** active
**Connections:** [sample_lookup]
**Compact Identifier:** 🧠

Skill for interpreting ambiguous or partial lookup results when the data source returns multiple candidates or incomplete matches.

## Domain Context

When a lookup returns multiple potential matches rather than a single definitive result, the LLM needs a reasoning frame to select the best candidate or determine that clarification is needed.

## Interpretation Patterns

- **Exact match present among candidates**: If one result matches all query parameters exactly, prefer it over partial matches
- **Partial overlap**: When multiple results share some but not all attributes, rank by the number of matching fields
- **Recency bias**: When relevance scores are close, prefer more recently updated records
- **Ambiguity threshold**: If the top two candidates score within 10% of each other, flag as ambiguous rather than guessing

## Decision Heuristics

1. Never silently pick a candidate when the distinction matters — surface the ambiguity
2. If domain context narrows the field to one, state the reasoning explicitly
3. When all candidates are weak matches, recommend re-querying with additional constraints rather than selecting the least-bad option
