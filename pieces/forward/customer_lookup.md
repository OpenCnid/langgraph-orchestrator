# 👤 Customer Lookup

**Type:** forward
**Status:** active
**Connections:** [sentiment_analysis]
**Compact Identifier:** 👤

Look up a customer by name, email, or account ID and return their profile, order history, and account status.

```mermaid
graph TD
    A[Receive customer identifier] --> B{Identifier type?}
    B -->|Email| C[Search by email]
    B -->|Name| D[Fuzzy name search]
    B -->|Account ID| E[Direct lookup]
    C --> F{Found?}
    D --> F
    E --> F
    F -->|Yes| G[Return customer profile]
    F -->|No| H[Trigger not-found recovery]
    G --> I[Conclude with success]
    H --> J[Conclude with escalated status]
```

## Workflow Notes

- Email search is exact match; name search uses fuzzy matching with Levenshtein distance
- Account ID lookup is the fastest path — prefer it when available
- Customer profile includes: name, email, account status, order count, lifetime value, last activity date
