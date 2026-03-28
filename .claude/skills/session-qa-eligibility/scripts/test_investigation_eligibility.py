#!/usr/bin/env python3
"""Check if staged files qualify for investigation-only QA skip.

Tests whether the currently staged git files are all within the
investigation-only allowlist defined in ADR-034.

Exit Codes:
    0 - Success (always returns 0, eligibility is in JSON output)

See: ADR-034 Investigation Session QA Exemption
See: ADR-035 Exit Code Standardization
"""

import json
import re
import subprocess
import sys


ALLOWLIST_PATTERNS: list[str] = [
    r"^\.agents/sessions/",
    r"^\.agents/analysis/",
    r"^\.agents/retrospective/",
    r"^\.serena/memories($|/)",
    r"^\.agents/security/",
    r"^\.agents/memory/",
    r"^\.agents/architecture/REVIEW-",
    r"^\.agents/critique/",
    r"^\.agents/memory/episodes/",
]

DISPLAY_PATHS: list[str] = [
    ".agents/sessions/",
    ".agents/analysis/",
    ".agents/retrospective/",
    ".serena/memories/",
    ".agents/security/",
    ".agents/memory/",
    ".agents/architecture/REVIEW-*",
    ".agents/critique/",
    ".agents/memory/episodes/",
]


def file_matches_allowlist(file_path: str) -> bool:
    """Test whether a file path matches any allowlist pattern."""
    normalized = file_path.replace("\\", "/")
    for pattern in ALLOWLIST_PATTERNS:
        if re.search(pattern, normalized):
            return True
    return False


def get_staged_files() -> tuple[list[str], bool]:
    """Get staged file paths from git.

    Returns:
        Tuple of (file_list, git_ok).
        If git fails, returns ([], False).
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return [], False
        files = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        ]
        return files, True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return [], False


def main() -> None:
    staged_files, git_ok = get_staged_files()

    if not git_ok:
        result = {
            "Eligible": False,
            "StagedFiles": [],
            "Violations": [],
            "AllowedPaths": DISPLAY_PATHS,
            "Error": "Not in a git repository or git command failed",
        }
        print(json.dumps(result, indent=2))
        sys.exit(0)

    violations = [f for f in staged_files if not file_matches_allowlist(f)]

    result = {
        "Eligible": len(violations) == 0,
        "StagedFiles": staged_files,
        "Violations": violations,
        "AllowedPaths": DISPLAY_PATHS,
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
