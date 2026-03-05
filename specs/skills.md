# Skills — Reusable Domain Reasoning

Skills are prompt files encoding reusable domain reasoning. They provide the interpretation patterns and decision logic that the LLM uses when a workflow delegates choices rather than prescribing deterministic steps.

## Role

Skills are the reasoning layer for LLM-bridged decisions. When a workflow step requires judgment — selecting between alternatives, interpreting ambiguous tool output, applying domain-specific heuristics — a skill supplies the reasoning frame.

When a workflow is fully deterministic (every branch is explicit, every output maps to a known next step), skills are unnecessary. Skills matter at the boundary where structured workflow meets LLM discretion.

## Skill Structure

Each skill is a prompt file stored in the atlas alongside workflows and recovery pieces. A skill contains:

- **Compact identifier** — emoji or structured marker, consistent with atlas piece conventions for retrieval separability
- **Domain context** — the background knowledge and constraints relevant to the reasoning task
- **Interpretation patterns** — how to read and classify inputs that lack a single deterministic mapping
- **Decision heuristics** — the priorities, trade-offs, and defaults to apply when choosing between options
- **Metadata** — connections to the workflows and recovery pieces that reference this skill, status (active/archived/draft)

## When Skills Are Used

- **Context assembly** loads relevant skills for each task alongside the matched workflow pieces
- **Forward workflows** invoke skills at steps where the LLM must make a judgment call (e.g., selecting a research strategy, interpreting a partial result, choosing output format)
- **Recovery pieces** use skills to interpret tool responses through domain-specific reasoning when response classification requires more than pattern matching

## Relationship to Workflows

Skills live at the higher-abstraction end of the spectrum. A workflow defines the steps; a skill defines how to think within a step. The same skill can be referenced by multiple workflows, and a single workflow step may load more than one skill when the decision spans domains.

## Skill Lifecycle

Skills follow the same lifecycle as other atlas pieces:

- **Active** — verified and referenced by at least one workflow or recovery piece
- **Archived** — superseded or no longer referenced; retained for context, never deleted
- **Draft** — proposed by Mode C or by a human, awaiting review

## Mutability

Skills are updated at the prompt layer. Changing a skill does not require code changes — it is a prompt edit within the atlas. Cascade checks apply: when a skill is updated, workflows and recovery pieces that reference it should be re-examined.

## Acceptance Criteria

- Skills are stored in the atlas and retrieved via the same embedding similarity mechanism as other pieces
- Context assembly loads relevant skills alongside workflow pieces for a given task
- Skills are only injected when the workflow delegates a decision to the LLM, not for fully deterministic steps
- Skill lifecycle transitions (active, archived, draft) work consistently with other atlas pieces
- Cascade checks identify workflows and recovery pieces affected when a skill is updated
- A skill can be referenced by multiple workflows, and a workflow step can load multiple skills
