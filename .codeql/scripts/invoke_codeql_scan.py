#!/usr/bin/env python3
"""Orchestrate CodeQL database creation and analysis for the repository.

Performs a complete CodeQL security scan by:
1. Auto-detecting languages in the repository (Python, GitHub Actions)
2. Creating CodeQL databases for each detected language
3. Running security queries against the databases using shared configuration
4. Generating SARIF output files for review and upload
5. Formatting results for console, JSON, or SARIF output

Exit codes follow ADR-035:
    0 - Success (no findings or not in CI mode)
    1 - Logic error or findings detected in CI mode
    2 - Configuration error (missing config, invalid paths)
    3 - External dependency error (CodeQL CLI not found, analysis failed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run CodeQL security scan on the repository.",
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
        help="Path where CodeQL databases will be created or cached.",
    )
    parser.add_argument(
        "--results-path",
        default=os.environ.get("CODEQL_RESULTS_PATH", ".codeql/results"),
        help="Path where SARIF result files will be saved.",
    )
    parser.add_argument(
        "--languages", nargs="*", default=None,
        help="Languages to scan. Auto-detected if not specified.",
    )
    parser.add_argument(
        "--use-cache", action="store_true",
        help="Reuse cached databases if still valid.",
    )
    parser.add_argument(
        "--ci", action="store_true",
        help="CI mode. Exits with code 1 if findings detected.",
    )
    parser.add_argument(
        "--format", choices=["console", "sarif", "json"], default="console",
        dest="output_format",
        help="Output format for scan results.",
    )
    parser.add_argument(
        "--quick-scan", action="store_true",
        help="Quick scan mode with targeted query selection.",
    )
    return parser


def find_codeql_executable() -> str:
    codeql = shutil.which("codeql")
    if codeql:
        return codeql

    script_dir = Path(__file__).resolve().parent
    default_path = script_dir / ".." / "cli" / "codeql"
    if default_path.exists():
        return str(default_path)

    print(
        "CodeQL CLI not found. Please install using install_codeql.py or add to PATH.",
        file=sys.stderr,
    )
    sys.exit(3)


def detect_languages(repo_path: str) -> list[str]:
    detected: list[str] = []

    for root, _dirs, files in os.walk(repo_path):
        if any(f.endswith(".py") for f in files):
            detected.append("python")
            break

    workflow_path = os.path.join(repo_path, ".github", "workflows")
    if os.path.isdir(workflow_path):
        yml_files = [f for f in os.listdir(workflow_path) if f.endswith(".yml")]
        if yml_files:
            detected.append("actions")

    if not detected:
        print("WARNING: No supported languages detected in repository", file=sys.stderr)

    return detected


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
    if not os.path.isdir(database_path):
        return False

    metadata_path = os.path.join(database_path, ".cache-metadata.json")
    if not os.path.isfile(metadata_path):
        return False

    try:
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    result = subprocess.run(
        ["git", "-C", repo_path, "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode == 0:
        current_head = result.stdout.strip()
        if current_head != metadata.get("git_head"):
            return False

    if os.path.isfile(config_path):
        config_hash = compute_file_hash(config_path)
        if config_hash != metadata.get("config_hash"):
            return False

    scripts_dir = os.path.join(repo_path, ".codeql", "scripts")
    if os.path.isdir(scripts_dir):
        scripts_hash = compute_directory_hash(scripts_dir)
        if scripts_hash != metadata.get("scripts_hash"):
            return False

    config_dir = os.path.join(repo_path, ".github", "codeql")
    if os.path.isdir(config_dir):
        config_dir_hash = compute_directory_hash(config_dir)
        if config_dir_hash != metadata.get("config_dir_hash"):
            return False

    return True


def write_cache_metadata(
    database_path: str, config_path: str, repo_path: str,
) -> None:
    result = subprocess.run(
        ["git", "-C", repo_path, "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    git_head = result.stdout.strip() if result.returncode == 0 else "unknown"

    config_hash = compute_file_hash(config_path) if os.path.isfile(config_path) else ""
    scripts_hash = compute_directory_hash(
        os.path.join(repo_path, ".codeql", "scripts"),
    )
    config_dir_hash = compute_directory_hash(
        os.path.join(repo_path, ".github", "codeql"),
    )

    metadata = {
        "created": datetime.now(tz=UTC).isoformat(),
        "git_head": git_head,
        "config_hash": config_hash,
        "scripts_hash": scripts_hash,
        "config_dir_hash": config_dir_hash,
    }

    metadata_path = os.path.join(database_path, ".cache-metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def create_database(
    codeql_path: str,
    language: str,
    source_root: str,
    database_path: str,
    config_path: str,
    repo_path: str,
    ci: bool,
) -> None:
    lang_db_path = os.path.join(database_path, language)

    if not ci:
        print(f"Creating CodeQL database for {language}...", file=sys.stderr)

    os.makedirs(database_path, exist_ok=True)

    if os.path.isdir(lang_db_path):
        shutil.rmtree(lang_db_path)

    cmd = [
        codeql_path, "database", "create", lang_db_path,
        f"--language={language}",
        f"--source-root={source_root}",
    ]

    if os.path.isfile(config_path):
        cmd.append(f"--codescanning-config={config_path}")

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300, check=False,
    )
    if result.returncode != 0:
        error_detail = result.stderr.strip() or result.stdout.strip()
        print(
            f"CodeQL database creation failed for {language} "
            f"(exit code {result.returncode}):\n{error_detail}",
            file=sys.stderr,
        )
        raise RuntimeError(
            f"CodeQL database creation failed with exit code {result.returncode}"
        )

    if not ci:
        print(f"[PASS] Database created for {language}", file=sys.stderr)

    write_cache_metadata(database_path, config_path, repo_path)


def analyze_database(
    codeql_path: str,
    language: str,
    database_path: str,
    results_path: str,
    config_path: str,
    ci: bool,
) -> dict:
    lang_db_path = os.path.join(database_path, language)
    sarif_output = os.path.join(results_path, f"{language}.sarif")

    if not ci:
        print(f"Analyzing {language} code...", file=sys.stderr)

    os.makedirs(results_path, exist_ok=True)

    cmd = [
        codeql_path, "database", "analyze", lang_db_path,
        "--format=sarif-latest",
        f"--output={sarif_output}",
        f"--sarif-category={language}",
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=600, check=False,
    )
    if result.returncode != 0:
        error_detail = result.stderr.strip() or result.stdout.strip()
        print(
            f"CodeQL analysis failed for {language} "
            f"(exit code {result.returncode}):\n{error_detail}",
            file=sys.stderr,
        )
        raise RuntimeError(
            f"CodeQL analysis failed with exit code {result.returncode}"
        )

    findings: list = []
    try:
        if os.path.isfile(sarif_output):
            with open(sarif_output, encoding="utf-8") as f:
                sarif = json.load(f)
            runs = sarif.get("runs", [])
            if runs and "results" in runs[0]:
                findings = runs[0]["results"]
        else:
            print(
                f"WARNING: SARIF output not found at {sarif_output}",
                file=sys.stderr,
            )
    except (json.JSONDecodeError, OSError, KeyError) as exc:
        print(
            f"Failed to parse SARIF output for {language}: {exc}",
            file=sys.stderr,
        )

    if not ci:
        print(
            f"[PASS] Analysis complete: {len(findings)} findings",
            file=sys.stderr,
        )

    return {
        "language": language,
        "findings_count": len(findings),
        "findings": findings,
        "sarif_path": sarif_output,
        "timed_out": False,
    }


def format_results(results: list[dict], output_format: str) -> None:
    if output_format == "console":
        print("\n========================================", file=sys.stderr)
        print("CodeQL Scan Results", file=sys.stderr)
        print("========================================", file=sys.stderr)

        total_findings = 0
        for r in results:
            if r["timed_out"]:
                print(f"\n{r['language']}: TIMEOUT (not analyzed)", file=sys.stderr)
                continue

            total_findings += r["findings_count"]
            status = "0 findings" if r["findings_count"] == 0 else f"{r['findings_count']} findings"
            print(f"\n{r['language']}: {status}", file=sys.stderr)
            print(f"  SARIF: {r['sarif_path']}", file=sys.stderr)

        print("\n========================================", file=sys.stderr)
        print(f"Total Findings: {total_findings}", file=sys.stderr)
        print("========================================", file=sys.stderr)

    elif output_format == "json":
        total = sum(r["findings_count"] for r in results if not r["timed_out"])
        json_results = {
            "TotalFindings": total,
            "Languages": [
                {
                    "Language": r["language"],
                    "FindingsCount": r["findings_count"],
                    "SarifPath": r["sarif_path"],
                }
                for r in results
            ],
        }
        print(json.dumps(json_results, indent=2))

    elif output_format == "sarif":
        print("SARIF files available at:", file=sys.stderr)
        for r in results:
            print(f"  {r['sarif_path']}", file=sys.stderr)


def validate_path_containment(repo_path: str) -> None:
    script_dir = Path(__file__).resolve().parent
    result = subprocess.run(
        ["git", "-C", str(script_dir), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode != 0:
        print(
            "Failed to determine project root using git.",
            file=sys.stderr,
        )
        sys.exit(2)

    project_root = os.path.realpath(result.stdout.strip())
    resolved_repo = os.path.realpath(repo_path)
    if not (resolved_repo == project_root or resolved_repo.startswith(project_root + os.sep)):
        print(
            "Path traversal attempt detected. RepoPath must be within the project directory.",
            file=sys.stderr,
        )
        sys.exit(2)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    repo_path = os.path.realpath(args.repo_path)
    validate_path_containment(repo_path)

    config_path = args.config_path
    if args.quick_scan and config_path == ".github/codeql/codeql-config.yml":
        config_path = ".github/codeql/codeql-config-quick.yml"
        if not args.ci:
            print("Quick scan mode enabled (targeted queries)", file=sys.stderr)

    config_path = os.path.join(repo_path, config_path) if not os.path.isabs(config_path) else config_path
    database_path = os.path.join(repo_path, args.database_path) if not os.path.isabs(args.database_path) else args.database_path
    results_path = os.path.join(repo_path, args.results_path) if not os.path.isabs(args.results_path) else args.results_path

    if not os.path.isdir(repo_path):
        print(f"Repository path not found: {repo_path}", file=sys.stderr)
        return 2

    if not os.path.isfile(config_path):
        print(
            f"WARNING: Config file not found at {config_path}. "
            "Proceeding without custom configuration.",
            file=sys.stderr,
        )

    codeql_path = find_codeql_executable()

    if not args.ci:
        print(f"CodeQL CLI: {codeql_path}", file=sys.stderr)
        print(f"Repository: {repo_path}", file=sys.stderr)

    languages = args.languages
    if not languages:
        languages = detect_languages(repo_path)
        if not languages:
            print("WARNING: No languages detected for scanning", file=sys.stderr)
            return 0

    if not args.ci:
        print(f"Languages to scan: {', '.join(languages)}", file=sys.stderr)

    use_cached = False
    if args.use_cache:
        use_cached = check_database_cache(database_path, config_path, repo_path)
        if use_cached and not args.ci:
            print("Using cached databases (validated)", file=sys.stderr)

    try:
        if not use_cached:
            for lang in languages:
                create_database(
                    codeql_path, lang, repo_path,
                    database_path, config_path, repo_path, args.ci,
                )

        analysis_results: list[dict] = []
        for lang in languages:
            result = analyze_database(
                codeql_path, lang, database_path,
                results_path, config_path, args.ci,
            )
            analysis_results.append(result)

        format_results(analysis_results, args.output_format)

        if args.ci:
            total_findings = sum(r["findings_count"] for r in analysis_results)
            if total_findings > 0:
                print(
                    f"CodeQL scan detected {total_findings} findings",
                    file=sys.stderr,
                )
                return 1

        return 0

    except RuntimeError as exc:
        print(f"CodeQL scan failed: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
