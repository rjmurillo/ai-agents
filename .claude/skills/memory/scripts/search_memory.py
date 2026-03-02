#!/usr/bin/env python3
"""Unified memory search across Serena and Forgetful.

Agent-facing skill script that provides unified memory search with
Serena-first routing and optional Forgetful augmentation per ADR-037.

Exit Codes:
    0  - Success: Search completed
    1  - Error: Invalid query or search failed

See: ADR-035 Exit Code Standardization
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


def validate_query(query: str) -> bool:
    """Validate query: 1-500 chars, alphanumeric + common punctuation."""
    if not query or len(query) > 500:
        return False
    return bool(re.match(r"^[a-zA-Z0-9\s\-.,_()&:]+$", query))


def search_serena(query: str, memory_path: Path, max_results: int) -> list[dict]:
    """Search Serena memories by keyword matching in file names and content."""
    results: list[dict] = []

    if not memory_path.is_dir():
        return results

    keywords = [w.lower() for w in query.split() if len(w) > 2]
    if not keywords:
        return results

    for f in sorted(memory_path.glob("*.md")):
        name_lower = f.stem.lower()
        name_matches = sum(1 for kw in keywords if kw in name_lower)

        if name_matches == 0:
            continue

        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        content_preview = " ".join(content.split())[:200]
        score = name_matches / len(keywords)

        results.append({
            "Name": f.stem,
            "Source": "Serena",
            "Score": round(score, 2),
            "Path": str(f),
            "Content": content_preview,
        })

    results.sort(key=lambda r: r["Score"], reverse=True)
    return results[:max_results]


def test_forgetful_available(endpoint: str) -> bool:
    """Check if Forgetful MCP is reachable."""
    try:
        req = urllib.request.Request(endpoint, method="GET")
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


def search_forgetful(query: str, endpoint: str, max_results: int) -> tuple[list[dict], str | None]:
    """Search Forgetful via MCP endpoint."""
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "memory_search",
            "arguments": {"query": query, "limit": max_results},
        },
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            endpoint, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))

        results: list[dict] = []
        if data.get("result", {}).get("content"):
            for item in data["result"]["content"]:
                if isinstance(item, dict) and item.get("type") == "text":
                    results.append({
                        "Name": "forgetful-result",
                        "Source": "Forgetful",
                        "Score": 0.5,
                        "Path": "",
                        "Content": item.get("text", "")[:200],
                    })
        return results, None
    except Exception as e:
        return [], str(e)


def get_router_status(memory_path: Path, forgetful_endpoint: str) -> dict:
    """Get memory router status."""
    serena_available = memory_path.is_dir()
    serena_count = 0
    if serena_available:
        serena_count = len(list(memory_path.glob("*.md")))

    forgetful_available = test_forgetful_available(forgetful_endpoint)

    return {
        "Serena": {
            "Available": serena_available,
            "MemoryCount": serena_count,
            "Path": str(memory_path),
        },
        "Forgetful": {
            "Available": forgetful_available,
            "Endpoint": forgetful_endpoint,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified memory search across Serena and Forgetful."
    )
    parser.add_argument("query", help="Search query (1-500 chars).")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--lexical-only", action="store_true")
    parser.add_argument("--semantic-only", action="store_true")
    parser.add_argument(
        "--format", choices=["json", "table"], default="json",
        dest="output_format",
    )
    args = parser.parse_args()

    if not validate_query(args.query):
        print(json.dumps({
            "Error": "Invalid query. Must be 1-500 chars, alphanumeric + common punctuation.",
            "Query": args.query,
        }))
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    memory_path = script_dir.parent.parent.parent.parent / ".serena" / "memories"
    forgetful_endpoint = "http://localhost:8020/mcp"

    search_status = {
        "SerenaQueried": not args.semantic_only,
        "ForgetfulQueried": not args.lexical_only,
        "SerenaSucceeded": False,
        "ForgetfulSucceeded": False,
        "ForgetfulError": None,
    }

    results: list[dict] = []

    if not args.semantic_only:
        serena_results = search_serena(args.query, memory_path, args.max_results)
        results.extend(serena_results)
        search_status["SerenaSucceeded"] = True

    if not args.lexical_only:
        fg_available = test_forgetful_available(forgetful_endpoint)
        if fg_available:
            fg_results, fg_error = search_forgetful(
                args.query, forgetful_endpoint, args.max_results,
            )
            if fg_error:
                search_status["ForgetfulError"] = fg_error
            else:
                search_status["ForgetfulSucceeded"] = True
                results.extend(fg_results)
        else:
            search_status["ForgetfulError"] = "Forgetful unavailable (TCP health check failed)"

    results.sort(key=lambda r: r["Score"], reverse=True)
    results = results[:args.max_results]

    if args.output_format == "table":
        if not results:
            print(f"No results found for: {args.query}")
        else:
            print(f"{'Name':<40} {'Source':<10} {'Score':<6} Preview")
            print("-" * 80)
            for r in results:
                preview = r["Content"][:57] + "..." if len(r["Content"]) > 60 else r["Content"]
                print(f"{r['Name']:<40} {r['Source']:<10} {r['Score']:<6} {preview}")
    else:
        if args.lexical_only:
            source = "Serena"
        elif args.semantic_only:
            source = "Forgetful"
        else:
            source = "Unified"
        output = {
            "Query": args.query,
            "Count": len(results),
            "Source": source,
            "SearchStatus": search_status,
            "Results": results,
            "Diagnostic": get_router_status(memory_path, forgetful_endpoint),
        }
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
