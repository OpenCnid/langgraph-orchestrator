# Piece Execution — Runtime Engine

The piece execution engine is the runtime core that loads a piece markdown file, interprets its mermaid workflow, dispatches tool calls, manages LLM-bridged decisions, and returns a conclusion. Every subagent delegates to this engine to run its assigned piece.

## Piece Loading

A piece markdown file is parsed into its constituent parts:

- **Front matter extraction** — compact identifier, metadata block (type, connections, response shapes handled, status)
- **Mermaid diagram extraction** — the fenced `mermaid` code block is isolated from the markdown body
- **Prose context extraction** — any surrounding markdown text outside the mermaid block is retained as supplementary instructions for the LLM

The loader validates that a mermaid diagram exists and that the piece status is `active`. Draft and archived pieces are rejected at load time unless explicitly overridden (recovery pieces executing within a Mode C context).

## Workflow Interpretation

The engine does not parse mermaid syntax into an AST. Instead, the LLM interprets the diagram as structured instructions:

1. The full piece content (diagram + prose) is injected into the LLM context as a system-level instruction
2. The LLM identifies the current node, its outgoing edges, and the conditions on those edges
3. At each step, the LLM determines whether the current node requires a tool call, a skill-based decision, or is a pass-through

This is the LLM-bridged end of the abstraction spectrum. Future iterations can add deterministic mermaid parsing for workflows where every node maps to a known tool call, but the initial implementation treats the diagram as instructions the model follows.

### Abstraction Spectrum Support

| Level | Behavior | Initial Implementation |
|---|---|---|
| Deterministic | Every node is a tool call, edges are conditionals on return values | Supported via LLM interpretation; no dedicated parser yet |
| Compositional | Nodes reference other pieces by ID | Engine recursively loads and executes referenced pieces |
| LLM-bridged | Model reads the diagram and picks the path | Primary mode — the LLM is the interpreter |

## Tool Dispatch

When the LLM identifies a workflow node as a tool invocation:

1. **Tool resolution** — the node label or annotation maps to a registered tool (MCP tool name, script path, or API endpoint)
2. **Input assembly** — tool inputs are assembled from the current execution state (prior node outputs, original piece inputs, constants from the diagram)
3. **Invocation** — the tool is called via the MCP tool interface or direct function dispatch
4. **Response capture** — the tool response is added to the execution state for downstream nodes
5. **Response validation** — the response is checked against expected shape; unexpected shapes trigger the recovery hook

Tool calls are leaf operations. The engine does not allow a tool call to spawn further subagents or modify the workflow graph. Tools execute and return.

## Skill Loading for LLM-Bridged Decisions

When a workflow node delegates a decision to the LLM rather than calling a tool:

- The engine loads the relevant skill into context — a focused instruction set for this particular decision
- The skill is injected alongside the current execution state, the LLM produces a decision, and the engine uses that decision to select the outgoing edge
- Skills are scoped: they load for the decision node and unload after — they do not persist across the entire piece execution

## Execution State

The engine maintains per-execution state:

- **node_outputs** — `dict[str, Any]`: keyed by node identifier, stores each node's output
- **current_node** — `str`: the active node in the workflow
- **execution_trace** — `list[str]`: ordered list of visited nodes (for debugging, not returned in conclusion)
- **error_state** — `Optional[RecoveryContext]`: populated when a tool response triggers recovery
- **inputs** — `dict[str, Any]`: the original inputs provided to this piece execution

State is local to the execution. It is not shared with other piece executions or with the parent orchestrator.

## Conclusion Contract

The engine's output is a **conclusion** — never a transcript:

- **summary** — `str`: a concise natural-language finding (e.g., "retrieved 4 records, Q3 flagged for margin anomaly")
- **status** — `Literal["success", "partial", "failed", "escalated"]`: execution outcome
- **key_outputs** — `dict[str, Any]`: named values that downstream pieces or the merger may need (kept minimal)
- **diagnostics** — `Optional[str]`: populated only on partial/failed/escalated — what went wrong, which node, what was attempted

The conclusion crosses the isolation boundary back to the orchestrator. The execution trace, intermediate tool responses, skill reasoning, and retry logs stay inside the subagent.

## Recovery Hooks

Recovery integrates at two points in the execution flow:

1. **Post-tool-response** — after every tool call, the response is checked. If unexpected:
   - Classify the response shape
   - Look up a matching recovery piece in the atlas
   - If found: execute recovery piece within current context, resume forward workflow
   - If not found: halt, set status to `escalated`, draft a diagnostic (Mode C behavior)

2. **Pre-conclusion** — before finalizing, validate that the overall execution produced a coherent result. Missing required outputs trigger recovery rather than returning a silently broken conclusion.

Recovery executions share the retry limit (configurable, default 3). On limit reached, the engine stops, sets status to `escalated`, and returns a conclusion with diagnostics.

## Acceptance Criteria

- Piece markdown files are parsed into diagram, prose, and metadata; invalid pieces are rejected
- LLM interprets the mermaid diagram and follows the workflow step by step
- Tool calls are dispatched and responses captured into execution state
- Skills load for LLM-bridged decision nodes and unload after the decision
- Compositional pieces (nodes referencing other piece IDs) trigger recursive execution
- Conclusions are structured objects with summary, status, key outputs, and optional diagnostics
- Execution trace and intermediate state do not leak into the conclusion
- Recovery hooks fire on unexpected tool responses and on pre-conclusion validation
- Retry limit is enforced; exceeded limit produces an escalated conclusion
- Execution state is fully isolated — no shared mutable state between concurrent piece executions
