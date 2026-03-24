#!/usr/bin/env python3
"""Detect infrastructure and security-critical file changes.

Analyzes changed files to identify those requiring security agent review.
Returns risk level and matching patterns.

EXIT CODES (ADR-035):
    0 - Success: Detection completed (always)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

# Critical patterns - security review REQUIRED
CRITICAL_PATTERNS = [
    r"^\.github/workflows/.*\.(yml|yaml)$",
    r"^\.github/actions/",
    r"^\.githooks/",
    r"^\.husky/",
    r".*/Auth/",
    r".*/Authentication/",
    r".*/Authorization/",
    r".*/Security/",
    r".*/Identity/",
    r".*Auth.*\.(cs|ts|js|py)$",
    r"\.env.*$",
    r".*\.(pem|key|p12|pfx|jks)$",
    r".*secret.*",
    r".*credential.*",
    r".*password.*",
]

# High patterns - security review RECOMMENDED
HIGH_PATTERNS = [
    r"^build/.*\.(ps1|sh|cmd|bat)$",
    r"^scripts/.*\.(ps1|sh)$",
    r"^Makefile$",
    r"^Dockerfile.*$",
    r"^docker-compose.*\.(yml|yaml)$",
    r".*/Controllers/",
    r".*/Endpoints/",
    r".*/Handlers/",
    r".*/Middleware/",
    r"^appsettings.*\.json$",
    r"^web\.config$",
    r"^app\.config$",
    r"^config/.*\.(json|yml|yaml)$",
    r".*\.tf$",
    r".*\.tfvars$",
    r".*\.bicep$",
    r"^nuget\.config$",
    r"^\.npmrc$",
]


def matches_pattern(file_path: str, patterns: list[str]) -> bool:
    """Check if a file path matches any of the given regex patterns."""
    for pattern in patterns:
        if re.search(pattern, file_path):
            return True
    return False


def get_security_risk_level(file_path: str) -> str:
    """Determine security risk level for a file path."""
    normalized = file_path.replace("\\", "/")
    if matches_pattern(normalized, CRITICAL_PATTERNS):
        return "critical"
    if matches_pattern(normalized, HIGH_PATTERNS):
        return "high"
    return "none"


def get_staged_files() -> list[str]:
    """Get list of staged files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def detect_infrastructure(
    changed_files: list[str] | None = None,
    use_git_staged: bool = False,
) -> dict:
    """Analyze files and return security risk findings."""
    if use_git_staged:
        changed_files = get_staged_files()

    if not changed_files:
        return {
            "findings": [],
            "highest_risk": "none",
            "file_count": 0,
        }

    findings = []
    highest_risk = "none"

    for file_path in changed_files:
        risk = get_security_risk_level(file_path)
        if risk != "none":
            findings.append({"File": file_path, "RiskLevel": risk})
            if risk == "critical":
                highest_risk = "critical"
            elif risk == "high" and highest_risk != "critical":
                highest_risk = "high"

    return {
        "findings": findings,
        "highest_risk": highest_risk,
        "file_count": len(changed_files),
    }


def main() -> int:
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect infrastructure and security-critical"
        " file changes",
    )
    parser.add_argument(
        "--files", nargs="*",
        help="Changed file paths to analyze",
    )
    parser.add_argument(
        "--use-git-staged", action="store_true",
        help="Analyze staged files from git",
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    result = detect_infrastructure(
        changed_files=args.files,
        use_git_staged=args.use_git_staged,
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if not result["findings"]:
        print("No infrastructure/security files detected.")
        return 0

    print("")
    print("=== Security Review Detection ===")
    print("")

    if result["highest_risk"] == "critical":
        print("CRITICAL: Security agent review REQUIRED")
    else:
        print("HIGH: Security agent review RECOMMENDED")

    print("")
    print("Matching files:")

    for finding in result["findings"]:
        level = finding["RiskLevel"].upper()
        print(f"  [{level}] {finding['File']}")

    print("")
    print("Run security agent before implementation:")
    print('  Task(subagent_type="security", prompt="Review infrastructure changes")')
    print("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
