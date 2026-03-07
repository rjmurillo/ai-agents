#!/usr/bin/env python3
"""Check if staged files qualify for investigation-only QA skip.

Tests whether the currently staged git files are all within the
investigation-only allowlist defined in ADR-034. This allows agents
to check eligibility before committing with "SKIPPED: investigation-only".

Exit codes follow ADR-035:
    0 - Success (always returns 0, eligibility is in JSON output)
"""

from __future__ import annotations

import json
import re
import subprocess

# Investigation allowlist patterns (single source of truth per Issue #840)
# Matches InvestigationAllowlist.psm1 patterns
_ALLOWLIST_PATTERNS = [
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

_ALLOWLIST_DISPLAY = [
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


def _file_matches_allowlist(file_path: str) -> bool:
    """Test whether a file path matches the investigation allowlist."""
    normalized = file_path.replace("\\", "/")
    return any(re.search(p, normalized) for p in _ALLOWLIST_PATTERNS)


def main(argv: list[str] | None = None) -> int:
    # Get staged files
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, timeout=10, check=False,
    )

    if result.returncode != 0:
        output = {
            "Eligible": False,
            "StagedFiles": [],
            "Violations": [],
            "AllowedPaths": _ALLOWLIST_DISPLAY,
            "Error": "Not in a git repository or git command failed",
        }
        print(json.dumps(output, indent=2))
        return 0

    staged_files = [
        line.strip() for line in result.stdout.splitlines()
        if line.strip()
    ]

    violations = [f for f in staged_files if not _file_matches_allowlist(f)]

    output = {
        "Eligible": len(violations) == 0,
        "StagedFiles": staged_files,
        "Violations": violations,
        "AllowedPaths": _ALLOWLIST_DISPLAY,
    }

    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
