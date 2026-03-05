# 😤 Customer Sentiment Analysis

**Type:** skill
**Status:** active
**Connections:** [customer_lookup, ticket_creation]
**Compact Identifier:** 😤

Skill for analyzing customer sentiment from message text to inform priority routing and agent assignment.

## Domain Context

Customer messages carry emotional signals that affect how they should be handled. A frustrated customer asking a simple question needs different treatment than a calm customer reporting a complex bug.

## Sentiment Categories

- **Positive**: Compliments, thanks, satisfaction expressions. Route normally.
- **Neutral**: Factual inquiries, status checks, information requests. Route normally.
- **Frustrated**: Repeated contacts, "still waiting", "this is the third time". Escalate priority.
- **Angry**: Profanity, threats to leave, ALL CAPS, exclamation marks. Escalate to senior agent.
- **Urgent**: Medical, safety, financial loss language. Immediate escalation regardless of queue.

## Scoring Heuristics

1. Weight explicit emotional language highest (profanity, "furious", "unacceptable")
2. Repeated punctuation (!!! or ???) amplifies detected sentiment by one level
3. ALL CAPS sections indicate frustration even in otherwise neutral text
4. Message length correlates with frustration — longer messages usually mean the customer has been dealing with the issue for a while
5. Prior interaction count matters — 3+ contacts on the same issue = frustrated regardless of tone
