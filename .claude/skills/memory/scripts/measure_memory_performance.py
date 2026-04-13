#!/usr/bin/env python3
"""Benchmark memory search performance across Serena and Forgetful systems.

Implements M-008 from Phase 2A: Create memory search benchmarks.
Measures Serena lexical search, Forgetful semantic search, and outputs
performance metrics for comparison against claude-flow baseline (96-164x target).

Exit codes follow ADR-035:
    0 - Success
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_QUERIES = [
    "PowerShell array handling patterns",
    "git pre-commit hook validation",
    "GitHub CLI PR operations",
    "session protocol compliance",
    "security vulnerability detection",
    "Pester test isolation",
    "CI workflow patterns",
    "memory-first architecture",
]

FORGETFUL_ENDPOINT = "http://localhost:8020/mcp"


def test_forgetful_available(endpoint: str = FORGETFUL_ENDPOINT) -> bool:
    """Check if Forgetful MCP is reachable."""
    try:
        parsed = urlparse(endpoint)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8020
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def measure_serena_search(
    query: str,
    memory_path: Path,
    iterations: int,
    warmup_iterations: int,
) -> dict:
    """Benchmark Serena's lexical memory search."""
    result: dict = {
        "Query": query,
        "System": "Serena",
        "ListTimeMs": 0.0,
        "MatchTimeMs": 0.0,
        "ReadTimeMs": 0.0,
        "TotalTimeMs": 0.0,
        "MatchedFiles": 0,
        "TotalFiles": 0,
        "IterationTimes": [],
    }

    if not memory_path.is_dir():
        result["Error"] = f"Memory path not found: {memory_path}"
        return result

    keywords = [
        kw for kw in query.lower().split() if len(kw) > 2
    ]

    # Warmup iterations
    for _ in range(warmup_iterations):
        files = list(memory_path.glob("*.md"))
        for f in files:
            name = f.stem.lower()
            matching = [kw for kw in keywords if re.search(re.escape(kw), name)]
            if matching:
                try:
                    f.read_text(encoding="utf-8")
                except OSError:
                    pass

    # Measured iterations
    list_times = []
    match_times = []
    read_times = []
    total_times = []
    matched_file_counts = []

    for _ in range(iterations):
        iter_start = time.perf_counter()

        # Phase 1: List files
        list_start = time.perf_counter()
        files = list(memory_path.glob("*.md"))
        list_end = time.perf_counter()
        list_times.append((list_end - list_start) * 1000)

        # Phase 2: Match keywords
        match_start = time.perf_counter()
        matched_files = []
        for f in files:
            name = f.stem.lower()
            matching = [kw for kw in keywords if re.search(re.escape(kw), name)]
            if matching:
                matched_files.append(f)
        match_end = time.perf_counter()
        match_times.append((match_end - match_start) * 1000)

        # Phase 3: Read matched files
        read_start = time.perf_counter()
        for f in matched_files:
            try:
                f.read_text(encoding="utf-8")
            except OSError:
                pass
        read_end = time.perf_counter()
        read_times.append((read_end - read_start) * 1000)

        iter_end = time.perf_counter()
        total_times.append((iter_end - iter_start) * 1000)
        matched_file_counts.append(len(matched_files))

    result["ListTimeMs"] = round(sum(list_times) / len(list_times), 2)
    result["MatchTimeMs"] = round(sum(match_times) / len(match_times), 2)
    result["ReadTimeMs"] = round(sum(read_times) / len(read_times), 2)
    result["TotalTimeMs"] = round(sum(total_times) / len(total_times), 2)
    result["MatchedFiles"] = round(
        sum(matched_file_counts) / len(matched_file_counts),
    )
    result["TotalFiles"] = len(files)
    result["IterationTimes"] = total_times

    return result


def measure_forgetful_search(
    query: str,
    endpoint: str,
    iterations: int,
    warmup_iterations: int,
) -> dict:
    """Benchmark Forgetful's semantic memory search."""
    result: dict = {
        "Query": query,
        "System": "Forgetful",
        "SearchTimeMs": 0.0,
        "TotalTimeMs": 0.0,
        "MatchedMemories": 0,
        "IterationTimes": [],
    }

    if not test_forgetful_available(endpoint):
        result["Error"] = f"Forgetful MCP not available at {endpoint}"
        return result

    search_body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "memory_search",
            "arguments": {"query": query, "limit": 10},
        },
    }).encode("utf-8")

    # Warmup
    for _ in range(warmup_iterations):
        try:
            req = urllib.request.Request(
                endpoint, data=search_body,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

    # Measured iterations
    search_times = []
    memory_counts = []

    for _ in range(iterations):
        start = time.perf_counter()
        try:
            req = urllib.request.Request(
                endpoint, data=search_body,
                headers={"Content-Type": "application/json"},
            )
            response = urllib.request.urlopen(req, timeout=30)
            end = time.perf_counter()
            search_times.append((end - start) * 1000)

            data = json.loads(response.read())
            if data.get("result", {}).get("content"):
                memory_counts.append(1)
            else:
                memory_counts.append(0)
        except Exception as e:
            end = time.perf_counter()
            search_times.append((end - start) * 1000)
            memory_counts.append(0)
            result["Error"] = str(e)

    if search_times:
        result["SearchTimeMs"] = round(
            sum(search_times) / len(search_times), 2,
        )
        result["TotalTimeMs"] = result["SearchTimeMs"]
        result["MatchedMemories"] = round(
            sum(memory_counts) / len(memory_counts),
        )
        result["IterationTimes"] = search_times

    return result


def format_console(benchmark: dict) -> str:
    """Format benchmark results for console output."""
    lines = []
    lines.append(f"Serena Average: {benchmark['Summary']['SerenaAvgMs']}ms")
    if benchmark["Summary"]["ForgetfulAvgMs"] > 0:
        lines.append(
            f"Forgetful Average: {benchmark['Summary']['ForgetfulAvgMs']}ms",
        )
        lines.append(
            f"Speedup Factor: {benchmark['Summary']['SpeedupFactor']}x",
        )
        lines.append(f"Target: {benchmark['Summary']['Target']}")
    else:
        lines.append("Forgetful: Not available")
    return "\n".join(lines)


def format_markdown(benchmark: dict) -> str:
    """Format benchmark results as markdown report."""
    lines = [
        "# Memory Performance Benchmark Report",
        "",
        f"**Date**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}",
        "**Task**: M-008 (Phase 2A Memory System)",
        "",
        "## Configuration",
        "",
        "| Setting | Value |",
        "|---------|-------|",
        f"| Queries | {benchmark['Configuration']['Queries']} |",
        f"| Iterations | {benchmark['Configuration']['Iterations']} |",
        f"| Warmup | {benchmark['Configuration']['WarmupIterations']} |",
        "",
        "## Results",
        "",
        "| System | Average (ms) | Status |",
        "|--------|-------------|--------|",
        f"| Serena | {benchmark['Summary']['SerenaAvgMs']} | Baseline |",
    ]

    if benchmark["Summary"]["ForgetfulAvgMs"] > 0:
        status = (
            "Target Met"
            if benchmark["Summary"]["SpeedupFactor"] >= 10
            else "Below Target"
        )
        lines.append(
            f"| Forgetful | {benchmark['Summary']['ForgetfulAvgMs']} | {status} |",
        )

    lines.append("")
    if benchmark["Summary"]["SpeedupFactor"] > 0:
        lines.append(
            f"**Speedup Factor**: {benchmark['Summary']['SpeedupFactor']}x",
        )
        lines.append(f"**Target**: {benchmark['Summary']['Target']}")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark memory search performance.",
    )
    parser.add_argument(
        "--queries", nargs="*", default=None,
        help="Test queries to benchmark (default: built-in set)",
    )
    parser.add_argument(
        "--iterations", type=int, default=5,
        help="Number of iterations per query (default: 5)",
    )
    parser.add_argument(
        "--warmup", type=int, default=2,
        help="Number of warmup iterations (default: 2)",
    )
    parser.add_argument(
        "--serena-only", action="store_true",
        help="Only benchmark Serena (skip Forgetful)",
    )
    parser.add_argument(
        "--format", choices=["console", "markdown", "json"],
        default="console", dest="output_format",
        help="Output format (default: console)",
    )
    parser.add_argument(
        "--serena-path", type=Path, default=None,
        help="Path to Serena memories directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    queries = args.queries if args.queries else DEFAULT_QUERIES

    if args.serena_path:
        serena_path = args.serena_path
    else:
        serena_path = Path(".serena/memories")

    benchmark: dict = {
        "Timestamp": datetime.now(UTC).isoformat(),
        "Configuration": {
            "Queries": len(queries),
            "Iterations": args.iterations,
            "WarmupIterations": args.warmup,
            "SerenaPath": str(serena_path),
            "ForgetfulEndpoint": FORGETFUL_ENDPOINT,
        },
        "SerenaResults": [],
        "ForgetfulResults": [],
        "Summary": {
            "SerenaAvgMs": 0.0,
            "ForgetfulAvgMs": 0.0,
            "SpeedupFactor": 0.0,
            "Target": "96-164x (claude-flow baseline)",
        },
    }

    if args.output_format == "console":
        print("=== Memory Performance Benchmark (M-008) ===")
        print(
            f"Queries: {len(queries)}, Iterations: {args.iterations}, "
            f"Warmup: {args.warmup}",
        )
        print()

    # Benchmark Serena
    if args.output_format == "console":
        print("Benchmarking Serena (lexical search)...")

    for query in queries:
        if args.output_format == "console":
            print(f"  Query: '{query}'")

        serena_result = measure_serena_search(
            query, serena_path, args.iterations, args.warmup,
        )
        benchmark["SerenaResults"].append(serena_result)

        if args.output_format == "console":
            if serena_result.get("Error"):
                print(f"    Error: {serena_result['Error']}")
            else:
                print(
                    f"    Total: {serena_result['TotalTimeMs']}ms "
                    f"(List: {serena_result['ListTimeMs']}ms, "
                    f"Match: {serena_result['MatchTimeMs']}ms, "
                    f"Read: {serena_result['ReadTimeMs']}ms)",
                )
                print(
                    f"    Matched: {serena_result['MatchedFiles']} "
                    f"of {serena_result['TotalFiles']} files",
                )

    # Calculate Serena average
    valid_serena = [
        r for r in benchmark["SerenaResults"] if not r.get("Error")
    ]
    if valid_serena:
        avg = sum(r["TotalTimeMs"] for r in valid_serena) / len(valid_serena)
        benchmark["Summary"]["SerenaAvgMs"] = round(avg, 2)

    # Benchmark Forgetful
    if not args.serena_only:
        if args.output_format == "console":
            print()
            print("Benchmarking Forgetful (semantic search)...")

        if test_forgetful_available():
            for query in queries:
                if args.output_format == "console":
                    print(f"  Query: '{query}'")

                forgetful_result = measure_forgetful_search(
                    query, FORGETFUL_ENDPOINT, args.iterations, args.warmup,
                )
                benchmark["ForgetfulResults"].append(forgetful_result)

                if args.output_format == "console":
                    if forgetful_result.get("Error"):
                        print(f"    Error: {forgetful_result['Error']}")
                    else:
                        print(f"    Total: {forgetful_result['TotalTimeMs']}ms")
                        print(
                            f"    Matched: "
                            f"{forgetful_result['MatchedMemories']} memories",
                        )

            valid_forgetful = [
                r for r in benchmark["ForgetfulResults"] if not r.get("Error")
            ]
            if valid_forgetful:
                avg = (
                    sum(r["TotalTimeMs"] for r in valid_forgetful)
                    / len(valid_forgetful)
                )
                benchmark["Summary"]["ForgetfulAvgMs"] = round(avg, 2)
        else:
            if args.output_format == "console":
                print(f"  Forgetful MCP not available at {FORGETFUL_ENDPOINT}")
                print("  Skipping Forgetful benchmarks")

    # Calculate speedup factor
    serena_avg = benchmark["Summary"]["SerenaAvgMs"]
    forgetful_avg = benchmark["Summary"]["ForgetfulAvgMs"]
    if serena_avg > 0 and forgetful_avg > 0:
        benchmark["Summary"]["SpeedupFactor"] = round(
            serena_avg / forgetful_avg, 2,
        )

    # Output results
    if args.output_format == "console":
        print()
        print("=== Summary ===")
        print(format_console(benchmark))
    elif args.output_format == "markdown":
        print(format_markdown(benchmark))
    elif args.output_format == "json":
        print(json.dumps(benchmark, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
