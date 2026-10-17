#!/usr/bin/env python3
"""Fail when a doc or docstring repeats an ownership claim ADR-109 retired.

ADR-109 B1 made ``templates/agents/`` the source of every agent copy:
``agent_templates.py`` renders ``src/claude/agents/``, the binplace step copies
that onto ``.claude/agents/``, and the ``github`` platform renders
``.github/agents/``. B2 did the same for rules. No agent copy is
hand-maintained any more, yet the sibling docs, rule text, and generator
docstrings kept saying so for weeks (issue #5788), and a reader who trusts one
of them edits a rendered file that the next ``build_all.py`` run overwrites.

Nothing else reports that kind of rot: the generated-artifact gates compare
output to source, and no gate reads prose. This guard holds a short table of
retired claims, each with the files it applies to, and fails when one comes
back. A claim belongs in the table only when its text is wrong on every line it
matches. Add a row when a migration retires another ownership claim.

Exit codes follow ADR-035: ``0`` no retired claim found, ``1`` at least one
found, ``2`` a configuration error (repo root is not a directory, or git
could not list the tracked files).

The scan reads tracked files at ``HEAD`` plus the index, per
``.claude/rules/ci-scripts.md`` MUST 9: an untracked scratch file is not
shipped, while a staged one must fail because the next commit ships it.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_CONFIG = 2

# An agent tree that ADR-109 B1 made generated output. A path below a
# subdirectory is not an agent file: ``.github/agents/security/references/`` is
# a hand-maintained byte copy that ``surface-parity.yaml`` maps by identity.
_AGENT_TREE = r"(?:src/claude/agents|\.claude/agents|\.github/agents)(?!/[^\s`/]+/)"

# Source files whose prose describes the agent and rule pipeline. Rendered
# copies (``.claude/rules``, ``src/claude/rules``, ``.github/instructions``,
# ``src/copilot-cli/instructions``) are excluded: they repeat a template
# verbatim, so scanning the template covers them once.
_PIPELINE_DOCS: tuple[str, ...] = (
    "templates/rules/*.md",
    "templates/README.md",
    "docs/*.md",
    ".agents/AGENT-SYSTEM.md",
    ".agents/governance/GENERATOR-FILES.md",
    "build/*.py",
    "build/scripts/*.py",
)


@dataclass(frozen=True)
class RetiredClaim:
    """One ownership claim that is wrong on every line it matches."""

    name: str
    pattern: re.Pattern[str]
    scope: tuple[str, ...]
    fix: str
    # A line matching this is a correction, not the retired claim.
    except_when: re.Pattern[str] | None = None


RETIRED_CLAIMS: tuple[RetiredClaim, ...] = (
    RetiredClaim(
        name="hand-maintained agent tree",
        pattern=re.compile(
            rf"hand-maintained[^\n]*{_AGENT_TREE}|{_AGENT_TREE}[^\n]*hand-maintained"
        ),
        scope=_PIPELINE_DOCS,
        fix=(
            "Every agent tree is generated (ADR-109 B1). "
            "Say generated or binplaced, and point at the template."
        ),
        except_when=re.compile(r"\b(?:no|not|never)\b[^\n]{0,80}hand-maintained", re.IGNORECASE),
    ),
    RetiredClaim(
        name="no generator writes the agent trees",
        pattern=re.compile(r"no generator writes (?:them|`?src/claude)"),
        scope=_PIPELINE_DOCS,
        fix=(
            "agent_templates.py renders src/claude/agents and "
            "binplace_manifest.py copies it onto .claude/agents."
        ),
    ),
    RetiredClaim(
        name="flat agent path",
        pattern=re.compile(r"src/claude/(?:[<{\[][a-z-]+[>}\]]|[a-z]+(?:-[a-z]+)*)\.md\b"),
        scope=_PIPELINE_DOCS,
        fix="Agents render to src/claude/agents/<stem>.md since ADR-109 B1.",
    ),
    RetiredClaim(
        name="rule source is the install copy",
        pattern=re.compile(r"\| `build/scripts/generate_rules\.py` \| `\.claude/rules/"),
        scope=(".agents/governance/GENERATOR-FILES.md",),
        fix=(
            "generate_rules.py reads src/claude/rules; "
            ".claude/rules is the binplaced install copy (ADR-109 B2)."
        ),
    ),
    RetiredClaim(
        name="drift allowlist size as a count",
        pattern=re.compile(r"\b\d+-(?:section|entry) allowlist\b"),
        scope=("templates/rules/*.md",),
        fix="Name SECTIONS_TO_COMPARE; a number goes stale on the next edit.",
    ),
    RetiredClaim(
        name="PowerShell scripts README",
        pattern=re.compile(r"PowerShell scripts for the AI Agents|Invoke-Pester|\bPester\b"),
        scope=("scripts/README.md",),
        fix="Every script is Python (ADR-042) and tests run under pytest.",
    ),
    RetiredClaim(
        name="untracked claude-mem tooling",
        pattern=re.compile(r"Import-ClaudeMemMemories\.ps1|(?:export|import|search)-memories\.ts"),
        scope=(".claude-mem/memories/README.md",),
        fix="Use the Python wrappers under .claude-mem/scripts/.",
    ),
)


@dataclass(frozen=True)
class Finding:
    """One retired claim at one line of one file."""

    path: str
    line: int
    claim: RetiredClaim
    text: str


def _tracked_paths(repo_root: Path) -> list[str]:
    """Return paths tracked at HEAD or staged in the index, POSIX-normalized."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    return [entry for entry in result.stdout.split("\0") if entry]


def _in_scope(path: str, scope: tuple[str, ...]) -> bool:
    """Match a tracked path against scope globs where ``*`` stays in one directory."""
    for glob in scope:
        if fnmatch.fnmatchcase(path, glob) and path.count("/") == glob.count("/"):
            return True
    return False


def _scan_file(repo_root: Path, path: str, claims: tuple[RetiredClaim, ...]) -> list[Finding]:
    """Return the findings for one file against the claims whose scope covers it."""
    applicable = [claim for claim in claims if _in_scope(path, claim.scope)]
    if not applicable:
        return []
    try:
        lines = (repo_root / path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    return [
        Finding(path, number, claim, line.strip())
        for number, line in enumerate(lines, start=1)
        for claim in applicable
        if claim.pattern.search(line) and not (claim.except_when and claim.except_when.search(line))
    ]


def find_retired_claims(
    repo_root: Path, claims: tuple[RetiredClaim, ...] = RETIRED_CLAIMS
) -> list[Finding]:
    """Return every retired claim found in a tracked file its scope covers."""
    findings: list[Finding] = []
    for path in sorted(_tracked_paths(repo_root)):
        findings.extend(_scan_file(repo_root, path, claims))
    return findings


def _report(findings: list[Finding]) -> None:
    """Print each finding with its remediation, once per claim."""
    print(f"{len(findings)} retired ownership claim(s) found:", file=sys.stderr)
    for finding in findings:
        print(f"  {finding.path}:{finding.line}: {finding.claim.name}", file=sys.stderr)
        print(f"    {finding.text[:160]}", file=sys.stderr)
    for claim in sorted({finding.claim for finding in findings}, key=lambda c: c.name):
        print(f"{claim.name}: {claim.fix}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to scan (default: current directory).",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root
    if not repo_root.is_dir():
        print(f"Not a directory: {repo_root}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        findings = find_retired_claims(repo_root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_CONFIG

    if findings:
        _report(findings)
        return EXIT_VIOLATION

    print(f"No retired ownership claims: {len(RETIRED_CLAIMS)} claim(s) checked (ADR-109).")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
