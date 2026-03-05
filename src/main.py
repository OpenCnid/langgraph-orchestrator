"""CLI runner for the LangGraph orchestrator."""

import argparse
import sys

from src.atlas import Atlas
from src.graph import build_graph
from src.lib.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph Orchestrator")
    parser.add_argument("query", nargs="?", help="Query to process")
    parser.add_argument(
        "--pieces-dir", default=settings.pieces_dir,
        help="Directory containing piece files",
    )
    args = parser.parse_args()

    if not args.query:
        print("Usage: orchestrator <query>")
        sys.exit(1)

    # Load atlas
    atlas = Atlas()
    count = atlas.load_from_directory(args.pieces_dir)
    print(f"Loaded {count} pieces from {args.pieces_dir}")

    # Build and run graph (no LLM configured — uses default stub)
    graph = build_graph(atlas)
    app = graph.compile()

    result = app.invoke({"query": args.query})

    # Display results
    mode = result["routing_decision"].mode
    print(f"\nMode: {mode}")
    print(f"Response: {result['merged_response']}")

    conclusions = result.get("subagent_conclusions", [])
    if conclusions:
        print(f"\nConclusions ({len(conclusions)}):")
        for c in conclusions:
            print(f"  [{c.status}] {c.summary}")
            if c.diagnostics:
                print(f"    Diagnostics: {c.diagnostics}")


if __name__ == "__main__":
    main()
