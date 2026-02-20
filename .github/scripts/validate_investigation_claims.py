#!/usr/bin/env python3
"""CI backstop for investigation-only QA skip claims per ADR-034.

Validates commits claiming "SKIPPED: investigation-only" have only allowed files.

Exit codes per ADR-035:
    0 - Validation passed (all claims valid)
    1 - Validation failed (claim violations found)

Input:
    --session-dir: Directory containing session log JSON files
    --commits: Comma-separated commit SHAs to validate (optional)

Output:
    JSON report with violations to stdout
    GitHub Actions outputs: verdict, violation_count, violations
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

workspace = os.environ.get(
    "GITHUB_WORKSPACE",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)
sys.path.insert(0, workspace)

from scripts.ai_review_common import write_log, write_output  # noqa: E402

# Investigation allowlist patterns per ADR-034 + authorized extensions
# Must match .claude/skills/session/scripts/test_investigation_eligibility.py
_ALLOWLIST_PATTERNS = [
    r"^\.agents/sessions/",
    r"^\.agents/analysis/",
    r"^\.agents/retrospective/",
    r"^\.serena/memories($|/)",
    r"^\.agents/security/",
    r"^\.agents/memory/",  # Added in PR #926
    r"^\.agents/architecture/REVIEW-",  # Review documents
    r"^\.agents/critique/",  # Critic debate logs
    r"^\.agents/memory/episodes/",  # Memory episodes
]

# Pattern to detect investigation-only claims in session logs
_INVESTIGATION_CLAIM_PATTERN = re.compile(
    r"SKIPPED:\s*investigation-only", re.IGNORECASE
)


@dataclass
class ClaimViolation:
    """A violation of an investigation-only claim."""

    session_file: str
    commit_sha: str
    disallowed_files: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of investigation claim validation."""

    valid: bool
    violations: list[ClaimViolation] = field(default_factory=list)
    sessions_checked: int = 0
    claims_found: int = 0


def file_matches_allowlist(file_path: str) -> bool:
    """Check if a file path matches the investigation allowlist."""
    normalized = file_path.replace("\\", "/")
    return any(re.search(p, normalized) for p in _ALLOWLIST_PATTERNS)


def get_files_in_commit(commit_sha: str) -> list[str]:
    """Get list of files changed in a commit."""
    result = subprocess.run(
        ["git", "show", "--name-only", "--format=", commit_sha],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        write_log(f"WARNING: Could not get files for commit {commit_sha}")
        return []

    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def session_claims_investigation_only(session_path: Path) -> bool:
    """Check if a session log claims investigation-only skip."""
    try:
        data = json.loads(session_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        write_log(f"WARNING: Could not parse session file {session_path}: {e}")
        return False

    # Check protocolCompliance.sessionEnd for QA skip evidence
    protocol = data.get("protocolCompliance", {})
    session_end = protocol.get("sessionEnd", {})

    # Look for qaValidation or related fields with SKIPPED evidence
    for key in ("qaValidation", "checklistComplete"):
        item = session_end.get(key, {})
        evidence = item.get("evidence", "")
        if _INVESTIGATION_CLAIM_PATTERN.search(str(evidence)):
            return True

    # Also check the raw JSON for the pattern
    raw_text = session_path.read_text(encoding="utf-8")
    return bool(_INVESTIGATION_CLAIM_PATTERN.search(raw_text))


def get_commit_for_session(session_path: Path) -> str | None:
    """Get the commit SHA that introduced or last modified a session file."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", str(session_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()[:7]  # Short SHA


def validate_investigation_claims(
    session_dir: Path, commit_shas: list[str] | None = None
) -> ValidationResult:
    """Validate all investigation-only claims in session logs.

    Args:
        session_dir: Directory containing session log JSON files
        commit_shas: Optional list of specific commits to check

    Returns:
        ValidationResult with violations if any
    """
    result = ValidationResult(valid=True)

    # Find all session files
    session_files = list(session_dir.glob("*.json"))
    result.sessions_checked = len(session_files)

    for session_file in session_files:
        if not session_claims_investigation_only(session_file):
            continue

        result.claims_found += 1

        # Get the commit for this session
        commit_sha = get_commit_for_session(session_file)
        if not commit_sha:
            write_log(f"WARNING: Could not find commit for {session_file.name}")
            continue

        # If specific commits provided, skip if not in list
        if commit_shas and commit_sha not in commit_shas:
            continue

        # Get files in that commit
        files = get_files_in_commit(commit_sha)

        # Check for violations
        disallowed = [f for f in files if not file_matches_allowlist(f)]

        if disallowed:
            result.valid = False
            result.violations.append(
                ClaimViolation(
                    session_file=session_file.name,
                    commit_sha=commit_sha,
                    disallowed_files=disallowed,
                )
            )

    return result


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Validate investigation-only QA skip claims per ADR-034.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--session-dir",
        type=Path,
        default=Path(".agents/sessions"),
        help="Directory containing session log JSON files",
    )
    parser.add_argument(
        "--commits",
        type=str,
        default="",
        help="Comma-separated commit SHAs to validate (empty=all)",
    )
    parser.add_argument(
        "--output-format",
        choices=["json", "text"],
        default="text",
        help="Output format",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    args = build_parser().parse_args(argv)

    if not args.session_dir.exists():
        write_log(f"Session directory not found: {args.session_dir}")
        print(f"ERROR: Session directory not found: {args.session_dir}")
        return 1

    commits = [c.strip() for c in args.commits.split(",") if c.strip()] or None

    result = validate_investigation_claims(args.session_dir, commits)

    # Write GitHub Actions outputs
    write_output("verdict", "PASS" if result.valid else "FAIL")
    write_output("violation_count", str(len(result.violations)))

    if result.violations:
        violations_json = json.dumps(
            [
                {
                    "session": v.session_file,
                    "commit": v.commit_sha,
                    "files": v.disallowed_files,
                }
                for v in result.violations
            ]
        )
        write_output("violations", violations_json)

    # Output report
    if args.output_format == "json":
        report = {
            "valid": result.valid,
            "sessions_checked": result.sessions_checked,
            "claims_found": result.claims_found,
            "violations": [
                {
                    "session_file": v.session_file,
                    "commit_sha": v.commit_sha,
                    "disallowed_files": v.disallowed_files,
                }
                for v in result.violations
            ],
        }
        print(json.dumps(report, indent=2))
    else:
        print("Investigation-Only Claim Validation")
        print(f"Sessions checked: {result.sessions_checked}")
        print(f"Claims found: {result.claims_found}")
        print(f"Violations: {len(result.violations)}")

        if result.violations:
            print()
            print("VIOLATIONS DETECTED:")
            for v in result.violations:
                print(f"  Session: {v.session_file} (commit {v.commit_sha})")
                for f in v.disallowed_files:
                    print(f"    - {f}")

    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
