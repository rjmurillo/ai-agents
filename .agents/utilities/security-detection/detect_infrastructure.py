#!/usr/bin/env python3
"""
Detects infrastructure and security-critical file changes.

Analyzes changed files to identify those requiring security agent review.
Returns risk level and matching patterns.

Usage:
    python detect_infrastructure.py --git-staged
    python detect_infrastructure.py file1.yml file2.cs
"""

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Tuple


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


@dataclass
class Finding:
    """Represents a file matching security patterns."""

    file: str
    risk_level: str


def matches_patterns(file_path: str, patterns: List[str]) -> bool:
    """Check if file path matches any pattern."""
    # Normalize path separators
    normalized = file_path.replace("\\", "/")
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns)


def get_risk_level(file_path: str) -> str:
    """Determine risk level for a file."""
    if matches_patterns(file_path, CRITICAL_PATTERNS):
        return "critical"
    elif matches_patterns(file_path, HIGH_PATTERNS):
        return "high"
    return "none"


def get_staged_files() -> List[str]:
    """Get list of staged files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.CalledProcessError:
        return []


def analyze_files(files: List[str]) -> Tuple[str, List[Finding]]:
    """Analyze files and return highest risk level and findings."""
    findings = []
    highest_risk = "none"

    for file_path in files:
        risk = get_risk_level(file_path)
        if risk != "none":
            findings.append(Finding(file=file_path, risk_level=risk))
            if risk == "critical":
                highest_risk = "critical"
            elif risk == "high" and highest_risk != "critical":
                highest_risk = "high"

    return highest_risk, findings


def print_results(highest_risk: str, findings: List[Finding]) -> None:
    """Print analysis results."""
    if not findings:
        print("\033[92mNo infrastructure/security files detected.\033[0m")
        return

    print()
    print("\033[93m=== Security Review Detection ===\033[0m")
    print()

    if highest_risk == "critical":
        print("\033[91mCRITICAL: Security agent review REQUIRED\033[0m")
    else:
        print("\033[93mHIGH: Security agent review RECOMMENDED\033[0m")

    print()
    print("\033[96mMatching files:\033[0m")

    for finding in findings:
        color = "\033[91m" if finding.risk_level == "critical" else "\033[93m"
        print(f"  {color}[{finding.risk_level.upper()}] {finding.file}\033[0m")

    print()
    print("\033[90mRun security agent before implementation:\033[0m")
    print(
        '\033[90m  Task(subagent_type="security", prompt="Review infrastructure changes")\033[0m'
    )
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Detect infrastructure and security-critical file changes"
    )
    parser.add_argument(
        "--git-staged",
        action="store_true",
        help="Analyze staged files from git",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to analyze",
    )

    args = parser.parse_args()

    # Get files to analyze
    if args.git_staged:
        files = get_staged_files()
    elif args.files:
        files = args.files
    else:
        print("\033[90mNo files to analyze.\033[0m")
        sys.exit(0)

    if not files:
        print("\033[90mNo files to analyze.\033[0m")
        sys.exit(0)

    # Analyze and print results
    highest_risk, findings = analyze_files(files)
    print_results(highest_risk, findings)

    # Exit 0 for non-blocking behavior
    sys.exit(0)


if __name__ == "__main__":
    main()
