# Recovery Loops — Anti-Workflows

When a tool call within a subagent returns something unexpected, the recovery system finds the right anti-workflow and heals the loop rather than stalling.

## Response Shape Classification

Tool responses fall into categories:

| Response Shape | What the recovery piece does |
|---|---|
| Validation: specific fields flagged | Correct those fields, resubmit |
| Partial: n of m processed | Resume from the last confirmed step |
| Capacity: rate limit or timeout | Retry with delay, or pause and resume |
| Constraint: policy or permission block | Reroute to compliant path, or escalate |
| Shape mismatch between pieces | Adapt before passing on, or re-synthesize |
| Response shape not covered | Mode C: halt, draft diagnostic, do not improvise |

## Recovery Flow

1. Tool returns unexpected response within a subagent
2. Classify the response shape
3. Look up matching recovery piece in atlas (by response shape)
4. **If found:** execute recovery piece within the subagent's own context, return to forward loop
5. **If not found:** trigger Mode C within that subagent — draft what a recovery piece should look like, escalate
6. Enforce retry limit (configurable, default 3)
7. On limit reached: escalate to human, do not loop further

## Retry Limits

Each recovery loop iteration adds to the context window. A retry limit — set in config or per-piece — caps the cycles before escalating. This prevents context bloat from unbounded recovery attempts.

## Unrecognized Responses

When a response shape has no matching piece in the atlas, the agent halts rather than improvises. It drafts what a piece for this situation might look like — scope, structure, connections. This is Mode C operating within a recovery context.

## Acceptance Criteria

- Response shapes are correctly classified into the defined categories
- Recovery pieces are retrieved by response shape match
- Recovery execution stays within the subagent's context (doesn't pollute main)
- Retry limit is enforced and configurable
- Unrecognized response shapes trigger Mode C drafting, not improvisation
- Recovery → forward loop resumption works end-to-end
