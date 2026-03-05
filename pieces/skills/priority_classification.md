# 🔴 Priority Classification

**Type:** skill
**Status:** active
**Connections:** [ticket_creation]
**Compact Identifier:** 🔴

Skill for classifying support ticket priority based on issue type, customer tier, and business impact.

## Domain Context

Not all support tickets are equal. A VIP customer's billing issue during a flash sale outweighs a free-tier user's feature request. Priority classification balances urgency, impact, and customer value.

## Priority Levels

| Level | Label | Response Target | Criteria |
|-------|-------|----------------|----------|
| P0 | Critical | 15 minutes | Service outage, data loss, security breach |
| P1 | High | 1 hour | Payment failures, account locked, order stuck |
| P2 | Medium | 4 hours | Feature broken, incorrect data, shipping delay |
| P3 | Low | 24 hours | Feature requests, general questions, feedback |

## Classification Rules

1. **Issue type drives base priority**: outage/security → P0, payment/access → P1, functionality → P2, everything else → P3
2. **Customer tier adjusts**: Enterprise customers get -1 level (higher priority). Free tier gets +1 level (lower priority, min P3).
3. **Business impact overrides**: If the issue affects revenue (checkout broken, pricing wrong), force P1 minimum.
4. **Sentiment modifier**: Angry or urgent sentiment from sentiment_analysis bumps priority by -1 level.
5. **Time decay**: Unresolved tickets auto-escalate one level every 2x their response target.

## Edge Cases

- Multiple issues in one ticket: classify by the highest-priority issue
- Vague descriptions: default to P2 and re-classify after first agent response
- Duplicate tickets: merge and keep the highest priority assigned
