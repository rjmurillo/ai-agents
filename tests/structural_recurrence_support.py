"""Helpers shared by the issue #5410 contract tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def flat(path: Path) -> str:
    """Return a repository file's text with whitespace folded to single spaces."""
    return " ".join((REPO_ROOT / path).read_text(encoding="utf-8").split())


def missing(text: str, clauses: dict[str, str]) -> list[str]:
    """Return ids of clauses absent from ``text`` after whitespace folding."""
    folded = " ".join(text.split())
    return [key for key, clause in clauses.items() if " ".join(clause.split()) not in folded]
