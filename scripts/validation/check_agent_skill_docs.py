#!/usr/bin/env python3
"""Gate: every agent and skill has a reference page and a README row.

Stub. The checks land in the next commit; this one only pins the tests.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks_common import _resolve_default_base_ref
from evidence import CheckOutcome


@dataclass(frozen=True, slots=True)
class Finding:
    """One problem with one file, as a repo-relative path and a message."""

    path: str
    message: str


@dataclass(frozen=True, slots=True)
class Report:
    """What a check examined and what it found."""

    examined: int
    findings: list[Finding] = field(default_factory=list)


def find_page_findings(repo_root: Path) -> Report:
    """Return missing, orphaned, unlisted, and misshapen pages."""
    del repo_root
    return Report(examined=0)


def find_stale_pages(repo_root: Path, base_ref: str) -> Report | None:
    """Return skills whose facts changed since ``base_ref`` with no page edit."""
    del repo_root, base_ref
    return Report(examined=0)


def validate_agent_skill_docs(repo_root: Path) -> CheckOutcome:
    """Blocking pre-PR gate."""
    del repo_root
    return CheckOutcome.passed("validate_agent_skill_docs", revision="stub", scope="stub")


def validate_skill_page_freshness(repo_root: Path) -> CheckOutcome:
    """Advisory pre-PR gate."""
    _resolve_default_base_ref(repo_root)
    return CheckOutcome.passed("validate_skill_page_freshness", revision="stub", scope="stub")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    del argv
    return 0


if __name__ == "__main__":
    sys.exit(main())
