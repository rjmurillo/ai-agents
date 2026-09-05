#!/usr/bin/env python3
"""Detect command-style references to removed tracked scripts."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DOC_GLOBS = ("*.md", "*.yml", "*.yaml")
HISTORICAL_ROOTS = (
    ".agents/archive/",
    ".agents/sessions/",
    ".agents/retrospective/",
    ".agents/critique/",
    ".agents/planning/",
    ".agents/analysis/",
    ".agents/qa/",
    ".agents/devops/",
    ".agents/projects/",
    ".agents/audits/",
    ".serena/",
    ".claude-mem/",
)
DEFAULT_ALLOWLIST = Path("scripts/validation/stale_script_refs_allowlist.txt")

PWSH_REF = re.compile(r"\bpwsh\s+(?P<ref>(?:\.?[\\/])?[\w./\\-]+\.psm?1)\b", re.IGNORECASE)
RUN_REF = re.compile(
    r"\brun:\s*(?:pwsh\s+)?(?P<ref>(?:\.?[\\/])?[\w./\\-]+\.psm?1)\b",
    re.IGNORECASE,
)
BARE_REF = re.compile(
    r"^\s*(?:[-*]\s+|\d+\.\s+|[$>]\s*)?"
    r"`?(?P<ref>(?:\.?[\\/])?[\w./\\-]+\.psm?1)`?"
    r"(?:\s|$)",
    re.IGNORECASE,
)
FENCE = re.compile(r"^\s*```")


@dataclass(frozen=True)
class Finding:
    """A missing script reference in a tracked document."""

    file: str
    line: int
    ref: str

    def format(self) -> str:
        """Return the required finding format."""
        return f"{self.file}:{self.line}:{self.ref}"


def normalize_ref(ref: str) -> str:
    """Normalize a script reference for tracked-file comparison."""
    normalized = ref.strip().strip("`'\"")
    normalized = normalized.rstrip(".,);]")
    normalized = normalized.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def is_historical_path(path: str) -> bool:
    """Return whether path is in a history-only root."""
    return path.startswith(HISTORICAL_ROOTS)


def git_ls_files(repo_root: Path, patterns: tuple[str, ...] | None = None) -> set[str]:
    """Return tracked files for the given git pathspecs."""
    command = ["git", "ls-files"]
    if patterns:
        command.extend(patterns)
    result = subprocess.run(
        command,
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
        encoding="utf-8",
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def load_allowlist(path: Path) -> set[str]:
    """Load allowlisted files or references."""
    if not path.exists():
        return set()

    entries: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.split("#", 1)[0].strip()
        if clean:
            entries.add(clean.replace("\\", "/"))
    return entries


def is_allowed(finding: Finding, allowlist: set[str]) -> bool:
    """Return whether a finding is intentionally allowed."""
    return (
        finding.file in allowlist
        or finding.ref in allowlist
        or f"{finding.file}:{finding.ref}" in allowlist
        or finding.format() in allowlist
    )


def extract_refs(line: str, *, in_fence: bool) -> list[str]:
    """Extract command-style script references from one line."""
    refs = [match.group("ref") for match in PWSH_REF.finditer(line)]
    refs.extend(match.group("ref") for match in RUN_REF.finditer(line))

    if in_fence or line.lstrip().startswith(("./", ".\\", "scripts/", "build/")):
        bare = BARE_REF.search(line)
        if bare:
            refs.append(bare.group("ref"))

    return [normalize_ref(ref) for ref in refs]


def find_stale_refs(
    repo_root: Path,
    *,
    docs: set[str] | None = None,
    tracked: set[str] | None = None,
    allowlist: set[str] | None = None,
) -> list[Finding]:
    """Find command-style script refs that point to untracked files."""
    doc_files = docs if docs is not None else git_ls_files(repo_root, DOC_GLOBS)
    tracked_files = tracked if tracked is not None else git_ls_files(repo_root)
    allowed = allowlist if allowlist is not None else load_allowlist(repo_root / DEFAULT_ALLOWLIST)

    findings: list[Finding] = []
    for file in sorted(doc_files):
        normalized_file = file.replace("\\", "/")
        if is_historical_path(normalized_file):
            continue

        path = repo_root / normalized_file
        if not path.is_file():
            continue

        in_fence = False
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE.match(line):
                in_fence = not in_fence
                continue

            for ref in extract_refs(line, in_fence=in_fence):
                if ref in tracked_files:
                    continue
                finding = Finding(normalized_file, line_number, ref)
                if not is_allowed(finding, allowed):
                    findings.append(finding)

    return findings


def validate_stale_script_refs(repo_root: Path) -> bool:
    """Print stale script refs and return True when none are found."""
    findings = find_stale_refs(repo_root)
    for finding in findings:
        print(finding.format())
    return not findings


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Detect stale command-style script refs.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument(
        "--allowlist",
        default=str(DEFAULT_ALLOWLIST),
        help="Allowlist file, relative to repo root unless absolute.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the stale script reference check."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repo_root = Path(args.repo_root).resolve()
        allowlist_path = Path(args.allowlist)
        if not allowlist_path.is_absolute():
            allowlist_path = repo_root / allowlist_path

        findings = find_stale_refs(repo_root, allowlist=load_allowlist(allowlist_path))
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"stale_script_refs: {exc}", file=sys.stderr)
        return 2

    for finding in findings:
        print(finding.format())

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
