#!/usr/bin/env python3
"""Comprehensive diagnostics for CodeQL setup and configuration.

Performs a complete health check of the CodeQL infrastructure including:
- CodeQL CLI installation (version, path, permissions)
- Configuration validation (YAML syntax, query pack resolution)
- Database status (existence, size, creation timestamp, cache validity)
- Last scan results (SARIF files, finding counts, scan duration)

Exit codes follow ADR-035:
    0 - All checks passed
    1 - Some checks failed
    3 - Unable to run diagnostics (missing dependencies)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def build_parser():
    import argparse
    parser = argparse.ArgumentParser(
        description="Run CodeQL diagnostics and health checks.",
    )
    parser.add_argument(
        "--repo-path", default=os.environ.get("CODEQL_REPO_PATH", "."),
        help="Path to the repository root directory.",
    )
    parser.add_argument(
        "--config-path",
        default=os.environ.get(
            "CODEQL_CONFIG_PATH", ".github/codeql/codeql-config.yml",
        ),
        help="Path to the CodeQL configuration YAML file.",
    )
    parser.add_argument(
        "--database-path",
        default=os.environ.get("CODEQL_DATABASE_PATH", ".codeql/db"),
        help="Path where CodeQL databases are cached.",
    )
    parser.add_argument(
        "--results-path",
        default=os.environ.get("CODEQL_RESULTS_PATH", ".codeql/results"),
        help="Path where SARIF result files are stored.",
    )
    parser.add_argument(
        "--output-format", choices=["console", "json", "markdown"],
        default="console",
        help="Output format for diagnostics results.",
    )
    return parser


def check_cli() -> dict:
    result = {
        "installed": False,
        "path": None,
        "version": None,
        "executable_permissions": False,
        "recommendations": [],
    }

    codeql = shutil.which("codeql")
    if codeql:
        result["installed"] = True
        result["path"] = codeql
        result["executable_permissions"] = True
    else:
        script_dir = Path(__file__).resolve().parent
        default_path = script_dir / ".." / "cli" / "codeql"
        if default_path.exists():
            result["installed"] = True
            result["path"] = str(default_path)
            result["executable_permissions"] = True
        else:
            result["recommendations"].append(
                "CLI not found. Run: python3 .codeql/scripts/install_codeql.py --add-to-path"
            )
            return result

    try:
        proc = subprocess.run(
            [result["path"], "version"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if proc.returncode == 0:
            result["version"] = proc.stdout.strip().split("\n")[0]
    except (OSError, subprocess.TimeoutExpired):
        result["recommendations"].append(
            "Unable to execute CLI. Check permissions or reinstall"
        )

    return result


def check_config(config_path: str, codeql_path: str | None) -> dict:
    result = {
        "exists": False,
        "valid_yaml": False,
        "query_packs": [],
        "languages": [],
        "recommendations": [],
    }

    if not os.path.isfile(config_path):
        result["recommendations"].append(
            f"Config file not found at {config_path}. Create configuration file"
        )
        return result

    result["exists"] = True

    try:
        content = Path(config_path).read_text(encoding="utf-8")
    except OSError:
        result["recommendations"].append("Unable to read config file")
        return result

    if not content.strip():
        result["recommendations"].append("Config file is empty")
        return result

    for line_num, line in enumerate(content.split("\n"), 1):
        if re.match(r"^\s*(#|$)", line):
            continue
        if line.startswith("\t"):
            result["recommendations"].append(
                f"Config invalid YAML syntax: tabs at line {line_num}"
            )
            return result

    result["valid_yaml"] = True

    if codeql_path:
        packs_match = re.search(
            r"packs:\s*\n((?:\s+-\s+.+\n?)+)", content,
        )
        if packs_match:
            packs_section = packs_match.group(1)
            packs = [
                m.group(1).strip()
                for m in re.finditer(r"^\s+-\s+(.+)", packs_section, re.MULTILINE)
            ]
            result["query_packs"] = packs

    return result


def compute_file_hash(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_directory_hash(directory: str) -> str:
    if not os.path.isdir(directory):
        return ""
    all_files = sorted(Path(directory).rglob("*"))
    hash_parts: list[str] = []
    for f in all_files:
        if f.is_file():
            file_hash = compute_file_hash(str(f))
            hash_parts.append(f"{f}:{file_hash}")
    combined = "\n".join(hash_parts).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


def check_database_cache(
    database_path: str, config_path: str, repo_path: str,
) -> bool:
    metadata_path = os.path.join(database_path, ".cache-metadata.json")
    if not os.path.isfile(metadata_path):
        return False

    try:
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)

        proc = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip() != metadata.get("git_head"):
            return False

        if os.path.isfile(config_path):
            if compute_file_hash(config_path) != metadata.get("config_hash"):
                return False

        scripts_dir = os.path.join(repo_path, ".codeql", "scripts")
        if os.path.isdir(scripts_dir):
            if compute_directory_hash(scripts_dir) != metadata.get("scripts_hash"):
                return False

        config_dir = os.path.join(repo_path, ".github", "codeql")
        if os.path.isdir(config_dir):
            if compute_directory_hash(config_dir) != metadata.get("config_dir_hash"):
                return False

        return True
    except (json.JSONDecodeError, OSError):
        return False


def check_database(
    database_path: str, config_path: str, repo_path: str,
) -> dict:
    result = {
        "exists": False,
        "languages": [],
        "cache_valid": False,
        "size_mb": 0,
        "created_timestamp": None,
        "recommendations": [],
    }

    if not os.path.isdir(database_path):
        result["recommendations"].append(
            "Database directory not found. Run scan to create database"
        )
        return result

    result["exists"] = True

    lang_dirs = [
        d.name
        for d in Path(database_path).iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]
    result["languages"] = lang_dirs

    total_size = sum(
        f.stat().st_size
        for f in Path(database_path).rglob("*")
        if f.is_file()
    )
    result["size_mb"] = round(total_size / (1024 * 1024), 2)

    if lang_dirs:
        timestamps = []
        for d in Path(database_path).iterdir():
            if d.is_dir() and not d.name.startswith("."):
                timestamps.append(d.stat().st_mtime)
        if timestamps:
            oldest = min(timestamps)
            result["created_timestamp"] = datetime.fromtimestamp(
                oldest, tz=UTC,
            ).isoformat()

    metadata_path = os.path.join(database_path, ".cache-metadata.json")
    if os.path.isfile(metadata_path):
        result["cache_valid"] = check_database_cache(
            database_path, config_path, repo_path,
        )
    else:
        result["recommendations"].append(
            "Cache metadata missing. Database will be rebuilt on next scan"
        )

    return result


def check_results(results_path: str) -> dict:
    result = {
        "exists": False,
        "sarif_files": [],
        "total_findings": 0,
        "last_scan_timestamp": None,
        "findings_by_language": {},
        "recommendations": [],
    }

    if not os.path.isdir(results_path):
        result["recommendations"].append(
            "Results directory not found. Run scan to generate results"
        )
        return result

    result["exists"] = True

    sarif_files = list(Path(results_path).glob("*.sarif"))
    if not sarif_files:
        result["recommendations"].append(
            "No SARIF files found. Run scan to generate results"
        )
        return result

    result["sarif_files"] = [f.name for f in sarif_files]
    newest = max(sarif_files, key=lambda f: f.stat().st_mtime)
    result["last_scan_timestamp"] = datetime.fromtimestamp(
        newest.stat().st_mtime, tz=UTC,
    ).isoformat()

    for sarif_file in sarif_files:
        try:
            with open(sarif_file, encoding="utf-8") as f:
                sarif = json.load(f)
            findings = sarif.get("runs", [{}])[0].get("results", [])
            language = sarif_file.stem
            result["findings_by_language"][language] = len(findings)
            result["total_findings"] += len(findings)
        except (json.JSONDecodeError, OSError, IndexError):
            result["recommendations"].append(
                f"Failed to parse {sarif_file.name}. SARIF file may be corrupted"
            )

    return result


def format_console(diagnostics: dict) -> None:
    print("\n========================================")
    print("CodeQL Diagnostics Report")
    print("========================================")

    cli = diagnostics["cli"]
    print("\n[CodeQL CLI]")
    if cli["installed"]:
        print(f"  [PASS] Status: INSTALLED")
        print(f"  Path: {cli['path']}")
        print(f"  Version: {cli['version']}")
    else:
        print("  [FAIL] Status: NOT INSTALLED")
    for rec in cli["recommendations"]:
        print(f"  -> {rec}")

    cfg = diagnostics["config"]
    print("\n[Configuration]")
    if cfg["exists"] and cfg["valid_yaml"]:
        print("  [PASS] Status: VALID")
        if cfg["query_packs"]:
            print(f"  Query Packs: {len(cfg['query_packs'])}")
    elif cfg["exists"]:
        print("  [FAIL] Status: INVALID YAML")
    else:
        print("  [FAIL] Status: NOT FOUND")
    for rec in cfg["recommendations"]:
        print(f"  -> {rec}")

    db = diagnostics["database"]
    print("\n[Database]")
    if db["exists"]:
        print("  [PASS] Status: EXISTS")
        print(f"  Languages: {', '.join(db['languages'])}")
        print(f"  Size: {db['size_mb']} MB")
        print(f"  Created: {db['created_timestamp']}")
        cache_status = "[PASS] VALID" if db["cache_valid"] else "[WARNING] INVALID (will rebuild on next scan)"
        print(f"  Cache: {cache_status}")
    else:
        print("  [FAIL] Status: NOT FOUND")
    for rec in db["recommendations"]:
        print(f"  -> {rec}")

    res = diagnostics["results"]
    print("\n[Last Scan Results]")
    if res["exists"] and res["sarif_files"]:
        print("  [PASS] Status: AVAILABLE")
        print(f"  Last Scan: {res['last_scan_timestamp']}")
        print(f"  Total Findings: {res['total_findings']}")
        for lang, count in res["findings_by_language"].items():
            print(f"    - {lang}: {count}")
    else:
        print("  [WARNING] Status: NO RESULTS")
    for rec in res["recommendations"]:
        print(f"  -> {rec}")

    print("\n========================================")
    print(f"Overall Status: {diagnostics['overall_status']}")
    print("========================================\n")


def format_json(diagnostics: dict) -> None:
    print(json.dumps(diagnostics, indent=2, default=str))


def format_markdown(diagnostics: dict) -> None:
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    cli = diagnostics["cli"]
    cfg = diagnostics["config"]
    db = diagnostics["database"]
    res = diagnostics["results"]

    lines = [
        "# CodeQL Diagnostics Report",
        "",
        f"**Generated**: {timestamp}",
        "",
        "## Overall Status",
        "",
        f"**Status**: {diagnostics['overall_status']}",
        "",
        "---",
        "",
        "## CodeQL CLI",
        "",
        f"- **Installed**: {cli['installed']}",
        f"- **Path**: {cli['path'] or 'N/A'}",
        f"- **Version**: {cli['version'] or 'N/A'}",
        "",
        "---",
        "",
        "## Configuration",
        "",
        f"- **Exists**: {cfg['exists']}",
        f"- **Valid YAML**: {cfg['valid_yaml']}",
        f"- **Query Packs**: {len(cfg['query_packs'])}",
        "",
        "---",
        "",
        "## Database",
        "",
        f"- **Exists**: {db['exists']}",
        f"- **Languages**: {', '.join(db['languages'])}",
        f"- **Size**: {db['size_mb']} MB",
        f"- **Created**: {db['created_timestamp']}",
        f"- **Cache Valid**: {db['cache_valid']}",
        "",
        "---",
        "",
        "## Last Scan Results",
        "",
        f"- **Available**: {res['exists']}",
        f"- **Last Scan**: {res['last_scan_timestamp']}",
        f"- **Total Findings**: {res['total_findings']}",
        "",
        "---",
        "",
        "**End of Report**",
    ]
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        repo_path = os.path.realpath(args.repo_path)
        config_path = args.config_path
        if not os.path.isabs(config_path):
            config_path = os.path.join(repo_path, config_path)
        database_path = args.database_path
        if not os.path.isabs(database_path):
            database_path = os.path.join(repo_path, database_path)
        results_path = args.results_path
        if not os.path.isabs(results_path):
            results_path = os.path.join(repo_path, results_path)

        cli_check = check_cli()
        config_check = check_config(config_path, cli_check["path"])
        db_check = check_database(database_path, config_path, repo_path)
        results_check = check_results(results_path)

        all_recommendations = (
            cli_check["recommendations"]
            + config_check["recommendations"]
            + db_check["recommendations"]
            + results_check["recommendations"]
        )

        overall_status = "PASS" if not all_recommendations else "WARNINGS"

        diagnostics = {
            "cli": cli_check,
            "config": config_check,
            "database": db_check,
            "results": results_check,
            "overall_status": overall_status,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }

        if args.output_format == "console":
            format_console(diagnostics)
        elif args.output_format == "json":
            format_json(diagnostics)
        elif args.output_format == "markdown":
            format_markdown(diagnostics)

        return 0 if overall_status == "PASS" else 1

    except Exception as exc:
        print(f"Diagnostics failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
