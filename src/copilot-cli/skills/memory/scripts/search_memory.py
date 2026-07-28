#!/usr/bin/env python3
"""Unified memory search across Serena, the episode store, and Forgetful.

Agent-facing script that provides unified memory search with Serena-first
routing and optional Forgetful augmentation per ADR-037. Includes token
budget warnings for large memories.

The lexical path also searches the Tier 2 episode store. Before that was
wired, nothing outside the episode tests read those records, so the write
cost on every session-log commit bought nothing (Issue #3630).

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

# Every episode filename opens with `episode-<date>-` and often `session-<n>-`.
# Those tokens are metadata, not content: leaving them in the haystack made the
# keywords "episode" and "session" match nearly the whole corpus.
EPISODE_NAME_PREFIX = re.compile(r"^episode-\d{4}-\d{2}-\d{2}-(?:session-\d+-?)?")


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

    keywords = query_keywords(query)

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


def query_keywords(query: str) -> list[str]:
    """Split a query into match keywords, dropping very short noise words."""
    keywords = [kw for kw in query.lower().split() if len(kw) > 2]
    return keywords or query.lower().split()


def search_episodes(
    query: str, episodes_path: Path, max_results: int,
) -> list[dict[str, Any]]:
    """Search Tier 2 episode records by keyword.

    Matches the name slug, the task, and any lessons. Structural filename
    tokens are stripped first so that generic words do not match everything.
    """
    if not episodes_path.is_dir():
        return []

    keywords = query_keywords(query)
    results: list[dict[str, Any]] = []
    for episode_file in sorted(episodes_path.glob("episode-*.json")):
        try:
            episode = json.loads(episode_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(episode, dict):
            continue

        slug = EPISODE_NAME_PREFIX.sub("", episode_file.stem).replace("-", " ")
        task = str(episode.get("task") or "")
        lessons = episode.get("lessons")
        lesson_text = (
            " ".join(str(lesson) for lesson in lessons)
            if isinstance(lessons, list) else ""
        )
        haystack = f"{slug} {task} {lesson_text}".lower()

        matching = [kw for kw in keywords if kw in haystack]
        if not matching:
            continue
        score = len(matching) / len(keywords) if keywords else 0
        preview = re.sub(r"\s+", " ", task or slug).strip()
        results.append({
            "Name": episode_file.stem,
            "Source": "Episodes",
            "Score": round(score, 2),
            "Path": str(episode_file),
            "Content": preview[:200],
        })

    # Ties are common because scoring is a fraction of matched keywords. Within
    # a score tier the newest episode is the most useful, and the date sits at a
    # fixed position in the filename, so a stable name sort orders by recency.
    results.sort(key=lambda r: str(r["Name"]), reverse=True)
    results.sort(key=lambda r: float(r["Score"]), reverse=True)
    return results[:max_results]


def test_forgetful_available(host: str = "localhost", port: int = 8020) -> bool:
    """Check if Forgetful MCP is reachable via TCP."""
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def get_memory_router_status(serena_path: Path, episodes_path: Path | None = None) -> dict:
    """Return diagnostic status of memory systems."""
    serena_available = serena_path.is_dir()
    serena_count = 0
    if serena_available:
        serena_count = len(list(serena_path.glob("*.md")))

    episodes_available = episodes_path is not None and episodes_path.is_dir()
    episode_count = 0
    if episodes_available:
        episode_count = len(list(episodes_path.glob("episode-*.json")))

    forgetful_available = test_forgetful_available()
    return {
        "Serena": {
            "Available": serena_available,
            "MemoryCount": serena_count,
            "Path": str(serena_path),
        },
        "Episodes": {
            "Available": episodes_available,
            "MemoryCount": episode_count,
            "Path": str(episodes_path) if episodes_path is not None else "",
        },
        "Forgetful": {
            "Available": forgetful_available,
            "Endpoint": "http://localhost:8020/mcp",
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Unified memory search across Serena, episodes, and Forgetful."
        ),
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
        help="Search only the file-based stores (Serena and episodes)",
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
    parser.add_argument(
        "--episodes-path", type=Path, default=None,
        help="Path to the Tier 2 episode store directory",
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

    # Determine store paths
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent.parent.parent

    if args.serena_path:
        if ".." in args.serena_path.parts:
            msg = "Security: path must not contain traversal sequences."
            print(json.dumps({"Error": msg}, indent=2))
            return 2
        serena_path = args.serena_path.resolve()
    else:
        serena_path = repo_root / ".serena" / "memories"

    if args.episodes_path:
        if ".." in args.episodes_path.parts:
            msg = "Security: path must not contain traversal sequences."
            print(json.dumps({"Error": msg}, indent=2))
            return 2
        episodes_path = args.episodes_path.resolve()
    else:
        episodes_path = repo_root / ".agents" / "memory" / "episodes"

    search_status: dict[str, Any] = {
        "SerenaQueried": not semantic_only,
        "EpisodesQueried": not semantic_only,
        "ForgetfulQueried": not lexical_only,
        "SerenaSucceeded": False,
        "EpisodesSucceeded": False,
        "ForgetfulSucceeded": False,
        "ForgetfulError": None,
    }

    results: list[dict[str, Any]] = []

    # Search the file-based stores
    if not semantic_only:
        results = search_serena(query, serena_path, max_results)
        search_status["SerenaSucceeded"] = True
        results += search_episodes(query, episodes_path, max_results)
        search_status["EpisodesSucceeded"] = True
        results.sort(key=lambda r: float(r["Score"]), reverse=True)
        results = results[:max_results]

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
        source_label = "Lexical" if lexical_only else (
            "Forgetful" if semantic_only else "Unified"
        )
        output = {
            "Query": query,
            "Count": len(results),
            "Source": source_label,
            "SearchStatus": search_status,
            "TokenBudget": token_budget,
            "Results": results,
            "Diagnostic": get_memory_router_status(serena_path, episodes_path),
        }
        print(json.dumps(output, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
