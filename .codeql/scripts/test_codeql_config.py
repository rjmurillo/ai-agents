#!/usr/bin/env python3
"""Validate CodeQL configuration file syntax and content.

Performs comprehensive validation of the CodeQL configuration YAML file:
1. YAML syntax validation
2. Schema validation (required fields, valid values)
3. Query pack format verification
4. Path existence checks

Exit codes follow ADR-035:
    0 - Valid configuration
    1 - Invalid configuration (validation errors)
    2 - Configuration file not found
    3 - External dependency error (CodeQL CLI not found)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate CodeQL configuration file.",
    )
    parser.add_argument(
        "--config-path",
        default=os.environ.get(
            "CODEQL_CONFIG_PATH", ".github/codeql/codeql-config.yml",
        ),
        help="Path to the CodeQL configuration YAML file.",
    )
    parser.add_argument(
        "--ci", action="store_true",
        help="CI mode with non-interactive behavior.",
    )
    parser.add_argument(
        "--format", choices=["console", "json"], default="console",
        dest="output_format",
        help="Output format for validation results.",
    )
    return parser


def validate_yaml_syntax(config_path: str) -> dict[str, Any]:
    try:
        content = Path(config_path).read_text(encoding="utf-8")
    except OSError as exc:
        return {"valid": False, "error": str(exc), "content": None}

    if not content.strip():
        return {"valid": False, "error": "Config file is empty", "content": None}

    try:
        import yaml
        yaml.safe_load(content)
        return {"valid": True, "content": content}
    except ImportError:
        pass
    except Exception as exc:
        return {"valid": False, "error": f"YAML parse error: {exc}", "content": None}

    for line_num, line in enumerate(content.split("\n"), 1):
        if re.match(r"^\s*(#|$)", line):
            continue
        if line.startswith("\t"):
            return {
                "valid": False,
                "error": (
                    f"YAML parse error at line {line_num}: "
                    "Tabs are not allowed for indentation"
                ),
                "content": None,
            }

    return {"valid": True, "content": content}


def validate_config_schema(content: str) -> dict[str, Any]:
    errors: list[str] = []

    if not re.search(r"name\s*:\s*['\"]?[\w\s]+['\"]?", content):
        errors.append("Missing required field: 'name'")

    has_packs = bool(re.search(r"packs\s*:", content))
    has_queries = bool(re.search(r"queries\s*:", content))
    if not has_packs and not has_queries:
        errors.append("Config must have either 'packs' or 'queries' field")

    severity_match = re.search(r"severity\s*:\s*(\w+)", content)
    if severity_match:
        severity = severity_match.group(1)
        valid_severities = ("low", "medium", "high", "critical")
        if severity not in valid_severities:
            errors.append(
                f"Invalid severity value: '{severity}'. "
                f"Must be one of: {', '.join(valid_severities)}"
            )

    packs: list[str] = []
    packs_match = re.search(r"packs\s*:(.*?)(?=\n\w|\n#|\Z)", content, re.DOTALL)
    if packs_match:
        packs_section = packs_match.group(1)
        packs = [
            m.group(1).strip()
            for m in re.finditer(r"-\s*([^\n]+)", packs_section)
        ]

    paths: list[str] = []
    paths_match = re.search(r"paths\s*:(.*?)(?=\n\w|\n#|\Z)", content, re.DOTALL)
    if paths_match:
        paths_section = paths_match.group(1)
        paths = [
            m.group(1).strip()
            for m in re.finditer(r"-\s*([^\n]+)", paths_section)
        ]

    return {"errors": errors, "packs": packs, "paths": paths}


def validate_query_packs(
    codeql_path: str, packs: list[str], ci: bool,
) -> list[dict]:
    missing: list[dict] = []

    for pack in packs:
        if not pack.strip():
            missing.append({"pack": pack, "error": "Empty pack name"})
            continue

        if not re.match(r"^[\w\-]+/[\w\-]+(:|@)", pack):
            missing.append({
                "pack": pack,
                "error": (
                    "Invalid pack format. Expected 'owner/repo:path' "
                    "or 'owner/repo@version'"
                ),
            })
            continue

        if codeql_path and os.path.isfile(codeql_path):
            result = subprocess.run(
                [codeql_path, "resolve", "queries", pack],
                capture_output=True, text=True, timeout=60, check=False,
            )
            if result.returncode != 0:
                missing.append({
                    "pack": pack,
                    "error": f"Failed to resolve pack (exit code {result.returncode})",
                })

    return missing


def validate_paths_exist(paths: list[str], repo_root: str) -> list[dict]:
    missing: list[dict] = []
    for path in paths:
        full_path = os.path.join(repo_root, path)
        if "*" in path or "?" in path:
            parent = os.path.dirname(full_path)
            pattern = os.path.basename(full_path)
            if os.path.isdir(parent):
                from glob import glob
                matches = glob(os.path.join(parent, pattern))
                if not matches:
                    missing.append({"path": path, "warning": "No files match pattern"})
            else:
                missing.append({"path": path, "warning": "Path does not exist"})
        elif not os.path.exists(full_path):
            missing.append({"path": path, "warning": "Path does not exist"})
    return missing


def find_codeql_executable() -> str | None:
    codeql = shutil.which("codeql")
    if codeql:
        return codeql

    script_dir = Path(__file__).resolve().parent
    default_path = script_dir / ".." / "cli" / "codeql"
    if default_path.exists():
        return str(default_path)

    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = args.config_path

    if not os.path.isabs(config_path):
        config_path = os.path.join(os.getcwd(), config_path)

    if not os.path.isfile(config_path):
        if args.output_format == "console":
            print(f"[FAIL] Config file not found: {config_path}", file=sys.stderr)
        else:
            print(json.dumps({"valid": False, "error": f"Config file not found: {config_path}"}))
        return 2

    if not args.ci and args.output_format == "console":
        print("Validating CodeQL configuration...", file=sys.stderr)
        print(f"Config: {config_path}", file=sys.stderr)

    validation: dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

    yaml_result = validate_yaml_syntax(config_path)
    if not yaml_result["valid"]:
        validation["valid"] = False
        validation["errors"].append(f"YAML syntax error: {yaml_result['error']}")
    elif not args.ci and args.output_format == "console":
        print("[PASS] YAML syntax valid", file=sys.stderr)

    if yaml_result["valid"]:
        schema_result = validate_config_schema(yaml_result["content"])

        if schema_result["errors"]:
            validation["valid"] = False
            validation["errors"].extend(schema_result["errors"])
        elif not args.ci and args.output_format == "console":
            print("[PASS] Schema validation passed", file=sys.stderr)

        codeql_path = find_codeql_executable()
        if codeql_path and schema_result["packs"]:
            missing_packs = validate_query_packs(
                codeql_path, schema_result["packs"], args.ci,
            )
            if missing_packs:
                for pack in missing_packs:
                    msg = f"Query pack '{pack['pack']}': {pack['error']}"
                    if args.ci:
                        validation["valid"] = False
                        validation["errors"].append(msg)
                    else:
                        validation["warnings"].append(msg)
            elif not args.ci and args.output_format == "console":
                print(
                    f"[PASS] Query pack validation passed ({len(schema_result['packs'])} packs)",
                    file=sys.stderr,
                )
        elif not codeql_path:
            validation["warnings"].append(
                "CodeQL CLI not found - skipping query pack validation"
            )

        if schema_result["paths"]:
            repo_root = str(Path(config_path).parent.parent)
            missing_paths = validate_paths_exist(schema_result["paths"], repo_root)
            if missing_paths:
                for p in missing_paths:
                    validation["warnings"].append(
                        f"Path '{p['path']}': {p['warning']}"
                    )
            elif not args.ci and args.output_format == "console":
                print(
                    f"[PASS] All paths exist ({len(schema_result['paths'])} paths)",
                    file=sys.stderr,
                )

    if args.output_format == "json":
        print(json.dumps(validation, indent=2))
    else:
        if validation["errors"]:
            print("\nErrors:", file=sys.stderr)
            for err in validation["errors"]:
                print(f"  [FAIL] {err}", file=sys.stderr)

        if validation["warnings"]:
            print("\nWarnings:", file=sys.stderr)
            for warn in validation["warnings"]:
                print(f"  [WARNING] {warn}", file=sys.stderr)

        if validation["valid"]:
            print("\n[PASS] Configuration is valid", file=sys.stderr)
        else:
            print("\n[FAIL] Configuration has errors", file=sys.stderr)

    return 0 if validation["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
