# 💳 Payment Failed Recovery

**Type:** recovery
**Status:** active
**Connections:** [refund_processing]
**Response Shapes Handled:** [payment_declined, gateway_timeout, insufficient_funds, card_expired]
**Compact Identifier:** 💳

Recovery anti-workflow for payment processor failures during refund or charge operations.

```mermaid
graph TD
    A[Receive payment failure] --> B{Failure type?}
    B -->|Gateway timeout| C[Retry with backoff]
    B -->|Card expired| D[Request updated payment method]
    B -->|Insufficient funds| E[Suggest partial refund or store credit]
    B -->|Declined| F[Check fraud flags]
    C --> G{Retry succeeded?}
    G -->|Yes| H[Resume original workflow]
    G -->|No| I[Escalate to manual review]
    D --> J[Conclude with alternative action]
    E --> J
    F --> K{Fraud detected?}
    K -->|Yes| L[Flag and escalate]
    K -->|No| I
```

## Recovery Notes

- Gateway timeouts get 3 retries with exponential backoff (1s, 3s, 9s)
- Card expired is not retryable — must collect new payment info
- Fraud detection is a heuristic check, not definitive — always escalate for human review
- This piece is connected to refund_processing as its primary caller
