#!/usr/bin/env python3
"""Synchronize MCP configuration from Claude's .mcp.json to VS Code and Factory formats.

Transforms Claude Code's .mcp.json (using "mcpServers" root key) to Factory's
.factory/mcp.json and VS Code's .vscode/mcp.json formats.

Format differences:
  - Claude (.mcp.json):          { "mcpServers": { ... } }
  - Factory (.factory/mcp.json): { "mcpServers": { ... } }
  - VS Code (.vscode/mcp.json):  { "servers": { ... } }

EXIT CODES:
  0  - Success: Configuration synced
  1  - Error: File not found, invalid JSON, transformation failure

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path


def get_repo_root(override: str | None = None) -> Path:
    if override:
        return Path(override)
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return Path.cwd()


def transform_for_vscode(source: dict) -> dict:
    servers = copy.deepcopy(source.get("mcpServers", {}))

    if "serena" in servers and "args" in servers["serena"]:
        args = servers["serena"]["args"]
        servers["serena"]["args"] = [
            "ide" if a == "claude-code" else ("24283" if a == "24282" else a)
            for a in args
        ]

    result = {"servers": servers}
    for key, value in source.items():
        if key != "mcpServers" and key not in result:
            result[key] = value
    return result


def transform_for_factory(source: dict) -> dict:
    result = {"mcpServers": copy.deepcopy(source.get("mcpServers", {}))}
    for key, value in source.items():
        if key != "mcpServers" and key not in result:
            result[key] = value
    return result


def sync_config(
    source_path: Path,
    dest_path: Path,
    target: str,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    if not source_path.exists():
        print(f"ERROR: Source file not found: {source_path}", file=sys.stderr)
        sys.exit(1)

    if source_path.is_symlink():
        print(f"ERROR: Security: Source path is a symlink: {source_path}", file=sys.stderr)
        sys.exit(1)

    try:
        source_content = source_path.read_text(encoding="utf-8")
        source_json = json.loads(source_content)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: Failed to parse source JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if "mcpServers" not in source_json:
        print("ERROR: Source file does not contain 'mcpServers' key.", file=sys.stderr)
        sys.exit(1)

    if target == "vscode":
        dest_json = transform_for_vscode(source_json)
    else:
        dest_json = transform_for_factory(source_json)

    dest_content = json.dumps(dest_json, indent=2).replace("\r\n", "\n")
    if not dest_content.endswith("\n"):
        dest_content += "\n"

    if dest_path.exists():
        if dest_path.is_symlink():
            print(f"ERROR: Security: Destination is a symlink: {dest_path}", file=sys.stderr)
            sys.exit(1)
        existing = dest_path.read_text(encoding="utf-8").replace("\r\n", "\n")
        if existing == dest_content and not force:
            print(f"MCP config already in sync: {dest_path}")
            return False

    if dry_run:
        print(f"[DRY-RUN] Would sync: {source_path} -> {dest_path}")
        return False

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(dest_content, encoding="utf-8")
    print(f"Synced MCP config: {source_path} -> {dest_path}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync MCP config to VS Code/Factory formats")
    parser.add_argument("--source", type=Path, help="Path to .mcp.json source file")
    parser.add_argument("--destination", type=Path, help="Path to destination mcp.json file")
    parser.add_argument("--target", choices=["factory", "vscode"], default="vscode", help="Target platform")
    parser.add_argument("--sync-all", action="store_true", help="Sync to both Factory and VS Code")
    parser.add_argument("--force", action="store_true", help="Overwrite even if identical")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    parser.add_argument("--repo-root-override", help="Override repo root detection")
    args = parser.parse_args(argv)

    if args.sync_all and args.destination:
        print("ERROR: Cannot use --sync-all with --destination", file=sys.stderr)
        return 1
    if args.sync_all and args.target != "vscode":
        print("ERROR: Cannot use --sync-all with --target", file=sys.stderr)
        return 1

    repo_root = get_repo_root(args.repo_root_override)
    source_path = args.source or (repo_root / ".mcp.json")

    if args.sync_all:
        any_synced = False
        factory_dest = repo_root / ".factory" / "mcp.json"
        if sync_config(source_path, factory_dest, "factory", args.force, args.dry_run):
            any_synced = True
        vscode_dest = repo_root / ".vscode" / "mcp.json"
        if sync_config(source_path, vscode_dest, "vscode", args.force, args.dry_run):
            any_synced = True
        return 0

    if not args.destination:
        if args.target == "vscode":
            args.destination = repo_root / ".vscode" / "mcp.json"
        else:
            args.destination = repo_root / ".factory" / "mcp.json"

    sync_config(source_path, args.destination, args.target, args.force, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
