# 🔍 Record Lookup

**Type:** forward
**Status:** active
**Connections:** [sample_not_found]
**Compact Identifier:** 🔍

Look up a record by its unique identifier across available data sources.

```mermaid
graph TD
    A[Receive record ID] --> B{Validate ID format}
    B -->|Valid| C[Query data source]
    B -->|Invalid| D[Return validation error]
    C --> E{Record found?}
    E -->|Yes| F[Return record data]
    E -->|No| G[Trigger not-found recovery]
    D --> H[Conclude with failed status]
    F --> I[Conclude with success]
    G --> J[Conclude with escalated status]
```

## Workflow Notes

- The ID format validation checks for expected patterns (UUID, numeric, etc.)
- The data source query is a tool call — the specific tool depends on the domain
- When no record is found, the `sample_not_found` recovery piece handles the response
