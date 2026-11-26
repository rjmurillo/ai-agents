"""Regression guards for the documented CodeQL alert fetch.

The retired pre-commit wrapper derived the repository from the checkout's
origin and filtered alerts to the current branch. The replacement shell
snippet must preserve both scopes: ``GH_REPO`` can otherwise redirect the
placeholders to another checkout, and a request without ``ref`` reads the
default branch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    ".agents/governance/SECURITY-REVIEW-PROTOCOL.md",
    ".project-toolkit/security/benchmarks/README.md",
)


def _codeql_block(relative: str) -> str:
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    match = re.search(r"```bash\n(?P<body>[^`]*code-scanning/alerts[^`]*)```", text)
    assert match is not None, f"{relative} has no CodeQL fetch block"
    return match.group("body")


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_codeql_fetch_stays_in_the_current_checkout(relative: str) -> None:
    block = _codeql_block(relative)

    assert "env -u GH_REPO gh api" in block
    assert "repos/{owner}/{repo}/code-scanning/alerts" in block


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_codeql_fetch_queries_the_current_branch(relative: str) -> None:
    block = _codeql_block(relative)

    assert "--method GET" in block
    assert '-f "ref=refs/heads/$(git branch --show-current)"' in block
    assert "--jq '.[] | select(.state==\"open\")'" in block
