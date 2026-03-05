# 📦 Order Status Check

**Type:** forward
**Status:** active
**Connections:** [customer_lookup]
**Compact Identifier:** 📦

Check the current status of an order including shipping, payment, and fulfillment details.

```mermaid
graph TD
    A[Receive order ID] --> B{Validate order ID format}
    B -->|Valid| C[Query order database]
    B -->|Invalid| D[Return validation error]
    C --> E{Order exists?}
    E -->|Yes| F[Fetch shipping status]
    E -->|No| G[Trigger not-found recovery]
    F --> H[Compile order summary]
    H --> I[Conclude with success]
    D --> J[Conclude with failed status]
    G --> K[Conclude with escalated status]
```

## Workflow Notes

- Order summary includes: items, quantities, payment status, shipping carrier, tracking number, estimated delivery
- Connected to customer_lookup because order queries often need customer context
- If the order ID looks like a tracking number instead, suggest the user meant shipment tracking
