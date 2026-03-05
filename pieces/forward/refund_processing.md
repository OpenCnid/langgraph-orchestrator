# 💸 Refund Processing

**Type:** forward
**Status:** active
**Connections:** [order_status, payment_failed_recovery]
**Compact Identifier:** 💸

Process a refund for a completed order, validating eligibility and initiating the return flow.

```mermaid
graph TD
    A[Receive refund request] --> B[Verify order exists]
    B --> C{Order found?}
    C -->|No| D[Trigger not-found recovery]
    C -->|Yes| E{Check refund eligibility}
    E -->|Within window| F{Full or partial?}
    E -->|Outside window| G[Deny with explanation]
    F -->|Full| H[Process full refund]
    F -->|Partial| I[Calculate partial amount]
    I --> H
    H --> J{Payment processor response}
    J -->|Success| K[Conclude with success]
    J -->|Failed| L[Trigger payment recovery]
    G --> M[Conclude with failed status]
    D --> N[Conclude with escalated status]
    L --> O[Conclude with escalated status]
```

## Workflow Notes

- Refund window is 30 days from delivery date — configurable per merchant
- Partial refunds require an itemized breakdown of what's being returned
- Connected to order_status because refunds require order verification first
- Connected to payment_failed_recovery for handling payment processor failures
