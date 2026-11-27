"""Regression guards for the documented CodeQL alert fetch.

The retired pre-commit wrapper derived the repository from the checkout's
origin and filtered alerts to the current branch. The replacement shell
snippet must preserve the origin scope, select pull request and detached-HEAD
refs explicitly, and read every open alert rather than one unfiltered page.
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

    assert "get_repo_info" in block
    assert "repos/$repo/code-scanning/alerts" in block
    assert "repos/{owner}/{repo}/code-scanning/alerts" not in block


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_codeql_fetch_selects_branch_pr_and_detached_refs(relative: str) -> None:
    block = _codeql_block(relative)

    assert "--method GET" in block
    assert "refs/pull/<number>/merge" in block
    assert "git branch --show-current" in block
    assert '-f "ref=$scan_ref"' in block
    assert "exit 2" in block


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_codeql_fetch_reads_every_open_alert(relative: str) -> None:
    block = _codeql_block(relative)

    assert "-f state=open" in block
    assert "--paginate" in block
    assert "--jq '.[]'" in block
    assert 'select(.state=="open")' not in block
