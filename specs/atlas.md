# Atlas — Piece Registry

The atlas is the collection of all verified puzzle pieces. It stores, retrieves, and manages the lifecycle of forward workflows and recovery anti-workflows.

## Piece Structure

Each piece is a markdown file containing:

- **Compact identifier** — emoji or structured marker for retrieval separation (these occupy sparse regions in embedding space that natural language leaves empty)
- **Mermaid diagram** — the workflow, simultaneously documentation for humans and executable instructions for the model
- **Metadata** — type (forward/recovery), connections to other pieces, response shapes handled (recovery only), status (active/archived/draft)

## Two Kinds of Pieces

- **Forward pieces** (workflows) — the intended path, the steps that move work toward a result
- **Recovery pieces** (anti-workflows) — what to do when a tool returns something unexpected; purpose is recovery rather than forward progress

Both live in the same atlas, retrieved the same way.

## Retrieval

- Pieces are embedded for similarity search (FAISS or ChromaDB)
- Compact identifiers (emoji/structured markers) improve separability — words like "research", "investigate", "look up" cluster near the same embedding coordinates, but emoji occupy distinct sparse regions
- When a match is found, the full piece file loads into context

## Piece Lifecycle

- **Active** — verified, in use
- **Archived** — stale or replaced, failure info preserved (never deleted — a removed failure record means the system encounters the same situation with no warning)
- **Draft** — created by Mode C, awaiting human review

## Cascade Check

When a piece is replaced, pieces built on top of it may need re-examination. The atlas tracks connections between pieces to enable this.

## Acceptance Criteria

- Pieces can be stored, retrieved by embedding similarity, and filtered by type/status
- Compact identifiers demonstrably improve retrieval separability over plain-text descriptions
- Piece lifecycle transitions (active → archived, draft → active) work correctly
- Cascade check identifies dependent pieces when a piece is replaced
