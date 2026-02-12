#!/usr/bin/env python3
"""Health check for all memory system tiers.

Validates that all components of the four-tier memory system are operational.
Returns structured status for each tier to enable agent decision-making.

Tier 0: Working Memory (always available, Claude context)
Tier 1: Semantic Memory (Serena + Forgetful)
Tier 2: Episodic Memory (episodes directory)
Tier 3: Causal Memory (causal graph and patterns)

Exit codes follow ADR-035:
    0 - Success
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def test_serena_available(serena_path: Path) -> dict:
    """Check if Serena memories are accessible."""
    if not serena_path.is_dir():
        return {
            "available": False,
            "message": f"Serena memories directory not found: {serena_path}",
            "count": 0,
        }

    try:
        memories = list(serena_path.glob("*.md"))
        count = len(memories)
        return {
            "available": True,
            "message": f"Serena available with {count} memories",
            "count": count,
            "path": str(serena_path),
        }
    except PermissionError as e:
        return {
            "available": False,
            "message": f"Permission denied accessing Serena memories: {e}",
            "count": -1,
            "path": str(serena_path),
        }
    except OSError as e:
        return {
            "available": False,
            "message": f"Failed to enumerate Serena memories: {e}",
            "count": -1,
            "path": str(serena_path),
        }


def test_forgetful_available(
    host: str = "localhost", port: int = 8020,
) -> dict:
    """Check if Forgetful MCP is accessible."""
    uri = f"http://{host}:{port}/mcp"
    try:
        with socket.create_connection((host, port), timeout=5):
            return {
                "available": True,
                "message": f"Forgetful MCP reachable at {uri}",
                "endpoint": uri,
            }
    except OSError as e:
        return {
            "available": False,
            "message": f"Forgetful MCP not reachable: {e}",
            "endpoint": uri,
        }


def test_episodes_available(episodes_path: Path) -> dict:
    """Check if episodic memory storage is accessible."""
    if not episodes_path.is_dir():
        return {
            "available": False,
            "message": f"Episodes directory not found: {episodes_path}",
            "count": 0,
        }

    try:
        episodes = list(episodes_path.glob("episode-*.json"))
        count = len(episodes)
        return {
            "available": True,
            "message": f"Episodes directory available with {count} episodes",
            "count": count,
            "path": str(episodes_path),
        }
    except PermissionError as e:
        return {
            "available": False,
            "message": f"Permission denied accessing episodes: {e}",
            "count": -1,
            "path": str(episodes_path),
        }
    except OSError as e:
        return {
            "available": False,
            "message": f"Failed to enumerate episodes: {e}",
            "count": -1,
            "path": str(episodes_path),
        }


def test_causal_graph_available(causality_path: Path) -> dict:
    """Check if causal memory storage is accessible."""
    graph_path = causality_path / "causal-graph.json"

    if not causality_path.is_dir():
        return {
            "available": False,
            "message": f"Causality directory not found: {causality_path}",
            "nodes": 0,
            "edges": 0,
            "patterns": 0,
        }

    if not graph_path.is_file():
        return {
            "available": True,
            "message": "Causality directory exists but graph not initialized",
            "nodes": 0,
            "edges": 0,
            "patterns": 0,
            "path": str(causality_path),
        }

    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        node_count = len(graph.get("nodes", []))
        edge_count = len(graph.get("edges", []))
        pattern_count = len(graph.get("patterns", []))
        return {
            "available": True,
            "message": (
                f"Causal graph loaded: {node_count} nodes, "
                f"{edge_count} edges, {pattern_count} patterns"
            ),
            "nodes": node_count,
            "edges": edge_count,
            "patterns": pattern_count,
            "path": str(graph_path),
        }
    except (json.JSONDecodeError, OSError) as e:
        return {
            "available": False,
            "message": f"Failed to parse causal graph: {e}",
            "nodes": 0,
            "edges": 0,
            "patterns": 0,
        }


def test_modules_available(memory_root: Path) -> list[dict]:
    """Check if required module files exist."""
    core_dir = memory_root / "memory_core"
    modules: list[dict[str, Any]] = [
        {"name": "memory_router", "path": core_dir / "memory_router.py"},
        {"name": "reflexion_memory", "path": core_dir / "reflexion_memory.py"},
    ]

    results = []
    for module in modules:
        path = Path(module["path"])
        if path.is_file():
            results.append({
                "name": module["name"],
                "available": True,
                "message": "Module file exists",
                "path": str(path),
            })
        else:
            results.append({
                "name": module["name"],
                "available": False,
                "message": "Module file not found",
                "path": str(path),
            })
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Health check for all memory system tiers.",
    )
    parser.add_argument(
        "--format", choices=["json", "table"], default="json",
        dest="output_format",
        help="Output format: json (default) or table",
    )
    parser.add_argument(
        "--base-path", type=Path, default=None,
        help="Base project path (default: auto-detect from script location)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Determine base path
    if args.base_path:
        base_path = args.base_path
    else:
        script_dir = Path(__file__).resolve().parent
        base_path = script_dir.parent.parent.parent.parent

    serena_path = base_path / ".serena" / "memories"
    episodes_path = base_path / ".agents" / "memory" / "episodes"
    causality_path = base_path / ".agents" / "memory" / "causality"
    scripts_dir = Path(__file__).resolve().parent

    health: dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "overall": "healthy",
        "tiers": {},
        "modules": [],
        "recommendations": [],
    }

    # Tier 0: Working Memory (always available)
    health["tiers"]["tier0_working"] = {
        "name": "Working Memory",
        "available": True,
        "message": "Claude context window (always available)",
    }

    # Tier 1: Semantic Memory
    serena = test_serena_available(serena_path)
    forgetful = test_forgetful_available()

    tier1_available = serena["available"]
    if serena["available"] and forgetful["available"]:
        tier1_message = "Full semantic memory: Serena + Forgetful"
    elif serena["available"]:
        tier1_message = "Degraded: Serena only (use --lexical-only)"
    else:
        tier1_message = "UNAVAILABLE: Serena not accessible"

    health["tiers"]["tier1_semantic"] = {
        "name": "Semantic Memory",
        "available": tier1_available,
        "serena": serena,
        "forgetful": forgetful,
        "message": tier1_message,
    }

    if not forgetful["available"]:
        health["recommendations"].append(
            "Forgetful MCP unavailable - use --lexical-only flag for search_memory.py",
        )

    # Tier 2: Episodic Memory
    episodes = test_episodes_available(episodes_path)
    health["tiers"]["tier2_episodic"] = {
        "name": "Episodic Memory",
        "available": episodes["available"],
        "episodes": episodes,
        "message": episodes["message"],
    }

    if episodes["available"] and episodes.get("count", 0) == 0:
        health["recommendations"].append(
            "No episodes found - run extract_session_episode.py on completed sessions",
        )

    # Tier 3: Causal Memory
    causal = test_causal_graph_available(causality_path)
    health["tiers"]["tier3_causal"] = {
        "name": "Causal Memory",
        "available": causal["available"],
        "graph": causal,
        "message": causal["message"],
    }

    if causal["available"] and causal.get("nodes", 0) == 0:
        health["recommendations"].append(
            "Causal graph empty - run update_causal_graph.py after extracting episodes",
        )

    # Modules
    if args.base_path:
        memory_root = base_path / ".claude" / "skills" / "memory"
    else:
        memory_root = scripts_dir.parent
    health["modules"] = test_modules_available(memory_root)

    module_issues = [m for m in health["modules"] if not m["available"]]
    if module_issues:
        health["overall"] = "degraded"
        for issue in module_issues:
            health["recommendations"].append(
                f"Module {issue['name']} unavailable: {issue['message']}",
            )

    # Overall status
    tier_issues = [
        t for t in health["tiers"].values() if not t["available"]
    ]
    if tier_issues:
        critical = [t for t in tier_issues if t["name"] == "Semantic Memory"]
        if critical:
            health["overall"] = "unhealthy"
        else:
            health["overall"] = "degraded"

    # Output
    if args.output_format == "table":
        print("\nMemory System Health Check")
        print("=" * 50)
        print(f"Timestamp: {health['timestamp']}")
        overall = health["overall"]
        print(f"Overall: {overall.upper()}")
        print("\nTiers:")
        for key in sorted(health["tiers"]):
            tier = health["tiers"][key]
            status = "[OK]" if tier["available"] else "[X]"
            print(f"  {status} {tier['name']}: {tier['message']}")
        print("\nModules:")
        for module in health["modules"]:
            status = "[OK]" if module["available"] else "[X]"
            print(f"  {status} {module['name']}: {module['message']}")
        if health["recommendations"]:
            print("\nRecommendations:")
            for rec in health["recommendations"]:
                print(f"  - {rec}")
    else:
        print(json.dumps(health, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
