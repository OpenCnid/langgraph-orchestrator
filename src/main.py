"""Minimal CLI runner for the LangGraph orchestrator."""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph Orchestrator")
    parser.add_argument("query", nargs="?", help="Query to process")
    args = parser.parse_args()

    if not args.query:
        print("Usage: orchestrator <query>")
        sys.exit(1)

    # Graph execution will be wired here once P5 (graph topology) is built
    print(f"Query received: {args.query}")
    print("Graph not yet wired — scaffolding only.")


if __name__ == "__main__":
    main()
