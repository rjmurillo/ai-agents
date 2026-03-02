#!/usr/bin/env python3
"""Health check for all memory system tiers.

Validates that all components of the four-tier memory system are operational.
Returns structured status for each tier to enable agent decision-making.

Tier 0: Working Memory - Always available (Claude context)
Tier 1: Semantic Memory - Serena + Forgetful
Tier 2: Episodic Memory - Episodes directory
Tier 3: Causal Memory - Causal graph and patterns

Exit Codes:
    0  - Success: Health check completed

See: ADR-035 Exit Code Standardization
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


def test_serena_available(base_path: Path) -> dict:
    """Check if Serena memories are accessible."""
    serena_path = base_path / ".serena" / "memories"

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


def test_forgetful_available() -> dict:
    """Check if Forgetful MCP is accessible."""
    endpoint = "http://localhost:8020/mcp"
    try:
        req = urllib.request.Request(endpoint, method="GET")
        urllib.request.urlopen(req, timeout=5)
        return {
            "available": True,
            "message": f"Forgetful MCP reachable at {endpoint}",
            "endpoint": endpoint,
        }
    except Exception as e:
        return {
            "available": False,
            "message": f"Forgetful MCP not reachable: {e}",
            "endpoint": endpoint,
        }


def test_episodes_available(base_path: Path) -> dict:
    """Check if episodic memory storage is accessible."""
    episodes_path = base_path / ".agents" / "memory" / "episodes"

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


def test_causal_graph_available(base_path: Path) -> dict:
    """Check if causal memory storage is accessible."""
    causality_path = base_path / ".agents" / "memory" / "causality"
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
        nodes = len(graph.get("nodes", []))
        edges = len(graph.get("edges", []))
        patterns = len(graph.get("patterns", []))
        return {
            "available": True,
            "message": f"Causal graph loaded: {nodes} nodes, {edges} edges, {patterns} patterns",
            "nodes": nodes,
            "edges": edges,
            "patterns": patterns,
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


def test_modules_available(script_dir: Path) -> list[dict]:
    """Check if expected module files exist."""
    modules = [
        {"name": "MemoryRouter", "path": str(script_dir / "MemoryRouter.psm1")},
        {"name": "ReflexionMemory", "path": str(script_dir / "ReflexionMemory.psm1")},
    ]

    results: list[dict] = []
    for module in modules:
        if Path(module["path"]).is_file():
            results.append({
                "name": module["name"],
                "available": True,
                "message": "Module file exists",
                "path": module["path"],
            })
        else:
            results.append({
                "name": module["name"],
                "available": False,
                "message": "Module file not found",
                "path": module["path"],
            })

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Health check for all memory system tiers."
    )
    parser.add_argument(
        "--format", choices=["json", "table"], default="json",
        dest="output_format",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    base_path = script_dir.parent.parent.parent.parent

    health: dict = {
        "timestamp": datetime.now().isoformat(),
        "overall": "healthy",
        "tiers": {},
        "modules": [],
        "recommendations": [],
    }

    # Tier 0: Working Memory
    health["tiers"]["tier0_working"] = {
        "name": "Working Memory",
        "available": True,
        "message": "Claude context window (always available)",
    }

    # Tier 1: Semantic Memory
    serena = test_serena_available(base_path)
    forgetful = test_forgetful_available()

    if serena["available"] and forgetful["available"]:
        msg = "Full semantic memory: Serena + Forgetful"
    elif serena["available"]:
        msg = "Degraded: Serena only (use --lexical-only)"
    else:
        msg = "UNAVAILABLE: Serena not accessible"

    health["tiers"]["tier1_semantic"] = {
        "name": "Semantic Memory",
        "available": serena["available"],
        "serena": serena,
        "forgetful": forgetful,
        "message": msg,
    }

    if not forgetful["available"]:
        health["recommendations"].append(
            "Forgetful MCP unavailable - use --lexical-only flag for search_memory"
        )

    # Tier 2: Episodic Memory
    episodes = test_episodes_available(base_path)
    health["tiers"]["tier2_episodic"] = {
        "name": "Episodic Memory",
        "available": episodes["available"],
        "episodes": episodes,
        "message": episodes["message"],
    }
    if episodes["available"] and episodes.get("count", 0) == 0:
        health["recommendations"].append(
            "No episodes found - run extract_session_episode.py on completed sessions"
        )

    # Tier 3: Causal Memory
    causal = test_causal_graph_available(base_path)
    health["tiers"]["tier3_causal"] = {
        "name": "Causal Memory",
        "available": causal["available"],
        "graph": causal,
        "message": causal["message"],
    }
    if causal["available"] and causal.get("nodes", 0) == 0:
        health["recommendations"].append(
            "Causal graph empty - run update_causal_graph.py after extracting episodes"
        )

    # Modules
    health["modules"] = test_modules_available(script_dir)
    module_issues = [m for m in health["modules"] if not m["available"]]
    if module_issues:
        health["overall"] = "degraded"
        for issue in module_issues:
            health["recommendations"].append(
                f"Module {issue['name']} unavailable: {issue['message']}"
            )

    # Overall status
    tier_issues = [t for t in health["tiers"].values() if not t["available"]]
    if tier_issues:
        critical = [t for t in tier_issues if t["name"] == "Semantic Memory"]
        health["overall"] = "unhealthy" if critical else "degraded"

    if args.output_format == "table":
        print("\nMemory System Health Check")
        print("=" * 50)
        print(f"Timestamp: {health['timestamp']}")
        print(f"Overall: {health['overall'].upper()}")

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


if __name__ == "__main__":
    main()
