# 🚚 Shipment Tracking

**Type:** forward
**Status:** active
**Connections:** [order_status, rate_limit_recovery]
**Compact Identifier:** 🚚

Track a shipment using a tracking number or order ID, returning real-time location and delivery estimate.

```mermaid
graph TD
    A[Receive tracking input] --> B{Input type?}
    B -->|Tracking number| C[Query carrier API]
    B -->|Order ID| D[Look up tracking from order]
    D --> C
    C --> E{API response?}
    E -->|Success| F[Parse tracking events]
    E -->|Rate limited| G[Trigger rate limit recovery]
    E -->|Not found| H[Trigger not-found recovery]
    F --> I[Compile tracking summary]
    I --> J[Conclude with success]
    G --> K[Conclude with escalated status]
    H --> L[Conclude with escalated status]
```

## Workflow Notes

- Supports UPS, FedEx, USPS, DHL carrier APIs
- Connected to order_status because tracking often starts from an order lookup
- Rate limit recovery handles carrier API throttling with exponential backoff
- Tracking summary: current location, status, estimated delivery, event history
