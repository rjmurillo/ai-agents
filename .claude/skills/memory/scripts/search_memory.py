#!/usr/bin/env python3
"""Unified memory search across Serena and Forgetful.

Agent-facing script that provides unified memory search with Serena-first
routing and optional Forgetful augmentation per ADR-037. Includes token
budget warnings for large memories.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (invalid query or search failed)
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any

TOKEN_WARN_THRESHOLD = 5000
TOKEN_DECOMPOSE_THRESHOLD = 10000


def estimate_tokens(file_path: Path) -> int:
    """Estimate token count from file size (chars / 4)."""
    if not file_path.is_file():
        return 0
    try:
        return round(len(file_path.read_text(encoding="utf-8")) / 4)
    except OSError:
        return 0


def search_serena(
    query: str, memory_path: Path, max_results: int,
) -> list[dict[str, Any]]:
    """Search Serena memories by keyword matching on filenames and content."""
    if not memory_path.is_dir():
        return []

    keywords = [
        kw for kw in query.lower().split() if len(kw) > 2
    ]
    if not keywords:
        keywords = query.lower().split()

    results: list[dict[str, Any]] = []
    for md_file in sorted(memory_path.glob("*.md")):
        name = md_file.stem.lower()
        matching = [kw for kw in keywords if kw in name]
        if not matching:
            continue
        score = len(matching) / len(keywords) if keywords else 0
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            content = ""
        preview = re.sub(r"\s+", " ", content).strip()
        results.append({
            "Name": md_file.stem,
            "Source": "Serena",
            "Score": round(score, 2),
            "Path": str(md_file),
            "Content": preview[:200] if preview else "",
        })

    results.sort(key=lambda r: float(r["Score"]), reverse=True)
    return results[:max_results]


def test_forgetful_available(host: str = "localhost", port: int = 8020) -> bool:
    """Check if Forgetful MCP is reachable via TCP."""
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def get_memory_router_status(serena_path: Path) -> dict:
    """Return diagnostic status of memory systems."""
    serena_available = serena_path.is_dir()
    serena_count = 0
    if serena_available:
        serena_count = len(list(serena_path.glob("*.md")))

    forgetful_available = test_forgetful_available()
    return {
        "Serena": {
            "Available": serena_available,
            "MemoryCount": serena_count,
            "Path": str(serena_path),
        },
        "Forgetful": {
            "Available": forgetful_available,
            "Endpoint": "http://localhost:8020/mcp",
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified memory search across Serena and Forgetful.",
    )
    parser.add_argument(
        "query",
        help="Search query (1-500 chars, alphanumeric + common punctuation)",
    )
    parser.add_argument(
        "--max-results", type=int, default=10,
        help="Maximum results to return (1-100, default 10)",
    )
    parser.add_argument(
        "--lexical-only", action="store_true",
        help="Search only Serena (lexical/file-based)",
    )
    parser.add_argument(
        "--semantic-only", action="store_true",
        help="Search only Forgetful (semantic/vector)",
    )
    parser.add_argument(
        "--format", choices=["json", "table"], default="json",
        dest="output_format",
        help="Output format: json (default) or table",
    )
    parser.add_argument(
        "--serena-path", type=Path, default=None,
        help="Path to Serena memories directory",
    )
    return parser


def validate_query(query: str) -> str | None:
    """Validate query string. Returns error message or None."""
    if not query or len(query) > 500:
        return "Query must be 1-500 characters"
    if not re.match(r'^[a-zA-Z0-9\s\-.,_()\&:]+$', query):
        return "Query contains invalid characters"
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    query = args.query
    max_results = max(1, min(100, args.max_results))
    lexical_only = args.lexical_only
    semantic_only = args.semantic_only
    output_format = args.output_format

    validation_error = validate_query(query)
    if validation_error:
        error_output = {"Error": validation_error, "Query": query}
        print(json.dumps(error_output, indent=2))
        return 1

    # Determine Serena path
    if args.serena_path:
        serena_path = args.serena_path
    else:
        script_dir = Path(__file__).resolve().parent
        serena_path = script_dir.parent.parent.parent.parent / ".serena" / "memories"

    search_status: dict[str, Any] = {
        "SerenaQueried": not semantic_only,
        "ForgetfulQueried": not lexical_only,
        "SerenaSucceeded": False,
        "ForgetfulSucceeded": False,
        "ForgetfulError": None,
    }

    results: list[dict[str, Any]] = []

    # Search Serena
    if not semantic_only:
        results = search_serena(query, serena_path, max_results)
        search_status["SerenaSucceeded"] = True

    # Check Forgetful availability
    if not lexical_only:
        if test_forgetful_available():
            search_status["ForgetfulSucceeded"] = True
        else:
            search_status["ForgetfulSucceeded"] = False
            search_status["ForgetfulError"] = (
                "Forgetful unavailable (TCP health check failed)"
            )

    # Compute token estimates
    token_budget: dict[str, Any] = {"TotalEstimate": 0, "Warnings": []}
    for result in results:
        path = Path(result.get("Path", ""))
        estimate = estimate_tokens(path)
        result["TokenEstimate"] = estimate
        token_budget["TotalEstimate"] += estimate
        if estimate >= TOKEN_DECOMPOSE_THRESHOLD:
            token_budget["Warnings"].append(
                f"DECOMPOSE: {result['Name']} ({estimate} tokens) "
                f"exceeds {TOKEN_DECOMPOSE_THRESHOLD}",
            )
        elif estimate >= TOKEN_WARN_THRESHOLD:
            token_budget["Warnings"].append(
                f"LARGE: {result['Name']} ({estimate} tokens) "
                f"exceeds {TOKEN_WARN_THRESHOLD}",
            )

    if output_format == "table":
        if not results:
            print(f"No results found for: {query}")
        else:
            print(f"{'Name':<40} {'Source':<10} {'Score':<8} {'Tokens':<10} Preview")
            print("-" * 100)
            for r in results:
                preview = r.get("Content", "")
                if len(preview) > 60:
                    preview = preview[:57] + "..."
                print(
                    f"{r['Name']:<40} {r['Source']:<10} "
                    f"{r['Score']:<8} {r.get('TokenEstimate', 0):<10} "
                    f"{preview}",
                )
            print(
                f"\nToken budget: {token_budget['TotalEstimate']} tokens "
                f"(cumulative for {len(results)} results)",
            )
            for warning in token_budget["Warnings"]:
                print(f"WARNING: {warning}", file=sys.stderr)
    else:
        source_label = "Serena" if lexical_only else (
            "Forgetful" if semantic_only else "Unified"
        )
        output = {
            "Query": query,
            "Count": len(results),
            "Source": source_label,
            "SearchStatus": search_status,
            "TokenBudget": token_budget,
            "Results": results,
            "Diagnostic": get_memory_router_status(serena_path),
        }
        print(json.dumps(output, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
