#!/usr/bin/env python3
"""Benchmark memory search performance across Serena and Forgetful systems.

Implements M-008 from Phase 2A: Create memory search benchmarks.

Measures:
1. Serena lexical search (file-based, keyword matching)
2. Forgetful semantic search (vector-based, embeddings)

Exit Codes:
    0  - Success: Benchmarking completed

See: ADR-035 Exit Code Standardization
"""

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

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

SERENA_MEMORY_PATH = ".serena/memories"
FORGETFUL_ENDPOINT = "http://localhost:8020/mcp"


def measure_serena_search(
    query: str,
    memory_path: str,
    iterations: int,
    warmup_iterations: int,
) -> dict:
    """Benchmark Serena's lexical memory search."""
    result = {
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

    path = Path(memory_path)
    if not path.is_dir():
        result["Error"] = f"Memory path not found: {memory_path}"
        return result

    keywords = [w for w in query.lower().split() if len(w) > 2]

    # Warmup
    for _ in range(warmup_iterations):
        files = list(path.glob("*.md"))
        for f in files:
            name = f.stem.lower()
            if any(re.search(re.escape(kw), name) for kw in keywords):
                f.read_text(encoding="utf-8", errors="replace")

    list_times = []
    match_times = []
    read_times = []
    total_times = []
    matched_counts = []

    for _ in range(iterations):
        iter_start = time.perf_counter()

        list_start = time.perf_counter()
        files = list(path.glob("*.md"))
        list_end = time.perf_counter()
        list_times.append((list_end - list_start) * 1000)

        match_start = time.perf_counter()
        matched = []
        for f in files:
            name = f.stem.lower()
            if any(re.search(re.escape(kw), name) for kw in keywords):
                matched.append(f)
        match_end = time.perf_counter()
        match_times.append((match_end - match_start) * 1000)

        read_start = time.perf_counter()
        for f in matched:
            f.read_text(encoding="utf-8", errors="replace")
        read_end = time.perf_counter()
        read_times.append((read_end - read_start) * 1000)

        iter_end = time.perf_counter()
        total_times.append((iter_end - iter_start) * 1000)
        matched_counts.append(len(matched))

    result["ListTimeMs"] = round(sum(list_times) / len(list_times), 2)
    result["MatchTimeMs"] = round(sum(match_times) / len(match_times), 2)
    result["ReadTimeMs"] = round(sum(read_times) / len(read_times), 2)
    result["TotalTimeMs"] = round(sum(total_times) / len(total_times), 2)
    result["MatchedFiles"] = round(sum(matched_counts) / len(matched_counts))
    result["TotalFiles"] = len(files)
    result["IterationTimes"] = total_times

    return result


def test_forgetful_available(endpoint: str) -> bool:
    """Check if Forgetful MCP is available."""
    try:
        req = urllib.request.Request(endpoint, method="GET")
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


def measure_forgetful_search(
    query: str,
    endpoint: str,
    iterations: int,
    warmup_iterations: int,
) -> dict:
    """Benchmark Forgetful's semantic memory search."""
    result = {
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

    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "memory_search",
            "arguments": {"query": query, "limit": 10},
        },
    }).encode("utf-8")

    for _ in range(warmup_iterations):
        try:
            req = urllib.request.Request(
                endpoint, data=body, method="POST",
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

    search_times = []
    memory_counts = []

    for _ in range(iterations):
        start = time.perf_counter()
        try:
            req = urllib.request.Request(
                endpoint, data=body, method="POST",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=30)
            end = time.perf_counter()
            search_times.append((end - start) * 1000)
            data = json.loads(resp.read().decode("utf-8"))
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
        result["SearchTimeMs"] = round(sum(search_times) / len(search_times), 2)
        result["TotalTimeMs"] = result["SearchTimeMs"]
        result["MatchedMemories"] = round(sum(memory_counts) / len(memory_counts))
        result["IterationTimes"] = search_times

    return result


def format_console(benchmark: dict) -> None:
    """Print benchmark results to console."""
    print(f"Serena Average: {benchmark['Summary']['SerenaAvgMs']}ms")
    if benchmark["Summary"]["ForgetfulAvgMs"] > 0:
        print(f"Forgetful Average: {benchmark['Summary']['ForgetfulAvgMs']}ms")
        print(f"Speedup Factor: {benchmark['Summary']['SpeedupFactor']}x")
        print(f"Target: {benchmark['Summary']['Target']}")
    else:
        print("Forgetful: Not available")


def format_markdown(benchmark: dict) -> str:
    """Format benchmark results as markdown."""
    from datetime import datetime

    lines = [
        "# Memory Performance Benchmark Report",
        "",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
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
        status = "Target Met" if benchmark["Summary"]["SpeedupFactor"] >= 10 else "Below Target"
        lines.append(f"| Forgetful | {benchmark['Summary']['ForgetfulAvgMs']} | {status} |")

    lines.append("")
    if benchmark["Summary"]["SpeedupFactor"] > 0:
        lines.append(f"**Speedup Factor**: {benchmark['Summary']['SpeedupFactor']}x")
        lines.append(f"**Target**: {benchmark['Summary']['Target']}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark memory search performance."
    )
    parser.add_argument("--queries", nargs="*", default=None)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--warmup-iterations", type=int, default=2)
    parser.add_argument("--serena-only", action="store_true")
    parser.add_argument(
        "--format", choices=["console", "markdown", "json"], default="console",
        dest="output_format",
    )
    args = parser.parse_args()

    queries = args.queries if args.queries else DEFAULT_QUERIES

    benchmark = {
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "Configuration": {
            "Queries": len(queries),
            "Iterations": args.iterations,
            "WarmupIterations": args.warmup_iterations,
            "SerenaPath": SERENA_MEMORY_PATH,
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
            f"Queries: {len(queries)}, "
            f"Iterations: {args.iterations}, "
            f"Warmup: {args.warmup_iterations}"
        )
        print("\nBenchmarking Serena (lexical search)...")

    for query in queries:
        if args.output_format == "console":
            print(f"  Query: '{query}'")

        serena_result = measure_serena_search(
            query, SERENA_MEMORY_PATH, args.iterations, args.warmup_iterations,
        )
        benchmark["SerenaResults"].append(serena_result)

        if args.output_format == "console":
            if "Error" in serena_result:
                print(f"    Error: {serena_result['Error']}")
            else:
                print(
                    f"    Total: {serena_result['TotalTimeMs']}ms "
                    f"(List: {serena_result['ListTimeMs']}ms, "
                    f"Match: {serena_result['MatchTimeMs']}ms, "
                    f"Read: {serena_result['ReadTimeMs']}ms)"
                )

    valid_serena = [r for r in benchmark["SerenaResults"] if "Error" not in r]
    if valid_serena:
        avg = sum(r["TotalTimeMs"] for r in valid_serena) / len(valid_serena)
        benchmark["Summary"]["SerenaAvgMs"] = round(avg, 2)

    if not args.serena_only:
        if args.output_format == "console":
            print("\nBenchmarking Forgetful (semantic search)...")

        if test_forgetful_available(FORGETFUL_ENDPOINT):
            for query in queries:
                if args.output_format == "console":
                    print(f"  Query: '{query}'")

                fg_result = measure_forgetful_search(
                    query, FORGETFUL_ENDPOINT, args.iterations, args.warmup_iterations,
                )
                benchmark["ForgetfulResults"].append(fg_result)

                if args.output_format == "console":
                    if "Error" in fg_result:
                        print(f"    Error: {fg_result['Error']}")
                    else:
                        print(f"    Total: {fg_result['TotalTimeMs']}ms")

            valid_fg = [r for r in benchmark["ForgetfulResults"] if "Error" not in r]
            if valid_fg:
                avg = sum(r["TotalTimeMs"] for r in valid_fg) / len(valid_fg)
                benchmark["Summary"]["ForgetfulAvgMs"] = round(avg, 2)
        else:
            if args.output_format == "console":
                print(f"  Forgetful MCP not available at {FORGETFUL_ENDPOINT}")

    if benchmark["Summary"]["SerenaAvgMs"] > 0 and benchmark["Summary"]["ForgetfulAvgMs"] > 0:
        benchmark["Summary"]["SpeedupFactor"] = round(
            benchmark["Summary"]["SerenaAvgMs"] / benchmark["Summary"]["ForgetfulAvgMs"], 2
        )

    if args.output_format == "console":
        print("\n=== Summary ===")
        format_console(benchmark)
    elif args.output_format == "markdown":
        print(format_markdown(benchmark))
    else:
        print(json.dumps(benchmark, indent=2))


if __name__ == "__main__":
    main()
