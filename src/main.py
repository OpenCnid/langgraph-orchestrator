"""CLI runner for the LangGraph orchestrator."""

import argparse
import os
import sys

from src.atlas import Atlas
from src.graph import build_graph
from src.lib.config import settings
from src.lib.piece_runner import LLMCallable


def _make_openai_llm() -> LLMCallable | None:
    """Create an OpenAI LLM callable if API key is available."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None

    import openai

    client = openai.OpenAI()

    def llm_fn(system: str, user: str) -> str:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content or ""

    return llm_fn


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph Orchestrator")
    parser.add_argument("query", nargs="?", help="Query to process")
    parser.add_argument(
        "--pieces-dir", default=settings.pieces_dir,
        help="Directory containing piece files",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show detailed routing and execution info",
    )
    args = parser.parse_args()

    if not args.query:
        print("Usage: orchestrator <query>")
        sys.exit(1)

    # Detect LLM availability
    llm_fn = _make_openai_llm()
    if llm_fn:
        print(f"🧠 LLM: {settings.llm_model} | Embeddings: {settings.embedding_model}")
    else:
        print("⚠️  No OPENAI_API_KEY — using stub LLM and hash embeddings")

    # Load atlas
    atlas = Atlas()
    count = atlas.load_from_directory(args.pieces_dir)
    print(f"📦 Loaded {count} pieces from {args.pieces_dir}")

    # Build and run graph
    graph = build_graph(atlas, llm_fn=llm_fn)
    app = graph.compile()

    result = app.invoke({"query": args.query})

    # Display results
    mode = result["routing_decision"].mode
    mode_names = {"A": "Librarian", "B": "Orchestrator", "C": "Cartographer", "D": "Clarifier"}
    print(f"\n🔀 Mode {mode} — {mode_names.get(mode, 'Unknown')}")

    if args.verbose:
        decision = result["routing_decision"]
        for m in decision.matched_pieces:
            piece = atlas.get_piece(m.piece_id)
            label = piece.title if piece else m.piece_id
            print(f"   📎 {label} (score: {m.score:.3f})")

    print(f"\n💬 {result['merged_response']}")

    conclusions = result.get("subagent_conclusions", [])
    if conclusions:
        print(f"\n📋 Conclusions ({len(conclusions)}):")
        for c in conclusions:
            status_icons = {"success": "✅", "partial": "⚠️", "failed": "❌", "escalated": "🚨"}
            icon = status_icons.get(c.status, "•")
            print(f"  {icon} [{c.status}] {c.summary}")
            if c.diagnostics and args.verbose:
                print(f"    Diagnostics: {c.diagnostics}")


if __name__ == "__main__":
    main()
