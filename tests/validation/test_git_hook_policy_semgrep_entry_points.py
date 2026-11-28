"""The Semgrep allow path gives one verdict at staged, push, and CI diff (issue #7591).

Covers the three entry points, the remove-the-entry negative control, the
rename-promotion and notebook scan sites, and removal credit when the base
already holds the directive.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy
from tests.validation._suppression_gate_repo import (
    BASE_BODY,
    DIRECTIVE,
    ENTRY_IDS,
    ENTRY_POINTS,
    EXEC_RULE,
    NOQA,
    NOSEC,
    SOURCE,
    SUBPROCESS_RULE,
    allowed,
    body,
    git,
    init_repo,
    repo_with_change,
    write,
)


@pytest.mark.parametrize("entry_point", ENTRY_POINTS, ids=ENTRY_IDS)
@pytest.mark.parametrize(
    ("path", "directive_line", "expected"),
    [
        pytest.param(SOURCE, allowed(EXEC_RULE), 0, id="listed"),
        pytest.param(SOURCE, allowed(EXEC_RULE) + f"  {NOQA}: E501", 0, id="listed-noqa-e501"),
        pytest.param("src/muse/lib/ptk_run.py", allowed(SUBPROCESS_RULE), 0, id="listed-copy"),
        pytest.param(SOURCE, f"    {DIRECTIVE}", 1, id="bare"),
        pytest.param(SOURCE, f"    {DIRECTIVE}: other.rule", 1, id="unlisted-rule"),
        pytest.param("src/claude/lib/paths.py", allowed(EXEC_RULE), 1, id="unlisted-path"),
        pytest.param(SOURCE, allowed(EXEC_RULE) + f"  {NOSEC}", 1, id="nosec-after"),
        pytest.param(SOURCE, f"    x = 1  {NOSEC}", 1, id="nosec"),
    ],
)
def test_entry_points_agree(
    tmp_path: Path,
    entry_point: Callable[[Path, str], int],
    path: str,
    directive_line: str,
    expected: int,
) -> None:
    repo, base = repo_with_change(tmp_path, path, directive_line)
    assert entry_point(repo, base) == expected


@pytest.mark.parametrize("entry_point", ENTRY_POINTS, ids=ENTRY_IDS)
def test_negative_control_removing_the_entry_blocks_again(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry_point: Callable[[Path, str], int],
) -> None:
    kept = tuple(
        entry
        for entry in policy.ALLOWED_SEMGREP_SUPPRESSIONS
        if (entry.path, entry.rule_id) != (SOURCE, EXEC_RULE)
    )
    assert len(kept) == len(policy.ALLOWED_SEMGREP_SUPPRESSIONS) - 1
    monkeypatch.setattr(policy, "ALLOWED_SEMGREP_SUPPRESSIONS", kept)
    repo, base = repo_with_change(tmp_path, SOURCE, allowed(EXEC_RULE))
    assert entry_point(repo, base) == 1


# --- the rename-promotion and notebook sites ---------------------------------


def test_full_content_scan_applies_the_same_rule() -> None:
    text = body(allowed(EXEC_RULE))
    assert policy._full_content_suppression_violations("HEAD", SOURCE, text) == []
    assert policy._full_content_suppression_violations("HEAD", "src/claude/lib/paths.py", text) == [
        "HEAD:src/claude/lib/paths.py:5"
    ]


def test_notebook_scan_applies_the_same_exact_entry_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Notebook cells are decoded, so only an exact notebook entry would pass."""

    def notebook(source: list[str]) -> str:
        return json.dumps({"cells": [{"cell_type": "code", "source": source}]})

    base = notebook(["x = 1\n"])
    head = notebook(["x = 1\n", allowed(EXEC_RULE, indent="") + "\n"])
    check = policy._notebook_suppression_violations_for_text
    assert check("HEAD", "n.ipynb", base, head) == ["HEAD:n.ipynb:2"]
    entry = policy.AllowedSemgrepSuppression("n.ipynb", EXEC_RULE, "test")
    monkeypatch.setattr(policy, "ALLOWED_SEMGREP_SUPPRESSIONS", (entry,))
    assert check("HEAD", "n.ipynb", base, head) == []


# --- removal credit after merge, when the base already holds the directive ---


def _repo_with_directive_base(tmp_path: Path, head_line: str) -> tuple[Path, str]:
    repo = init_repo(tmp_path)
    write(repo, SOURCE, body(allowed(EXEC_RULE)))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    write(repo, SOURCE, BASE_BODY.replace("    os.execv", head_line + "\n    os.execv"))
    git(repo, "add", "-A")
    return repo, base


@pytest.mark.parametrize("entry_point", ENTRY_POINTS, ids=ENTRY_IDS)
@pytest.mark.parametrize(
    ("head_line", "expected"),
    [
        pytest.param("    x = 1", 0, id="directive-removed"),
        pytest.param("    " + allowed(EXEC_RULE), 0, id="directive-reindented"),
        pytest.param(f"    os.getpid()  {DIRECTIVE}: {EXEC_RULE}", 1, id="moved-onto-code"),
        pytest.param(f"    #{DIRECTIVE[2:]}:{EXEC_RULE}", 1, id="rewritten-without-spaces"),
        pytest.param(f"    {DIRECTIVE}", 1, id="swapped-for-bare"),
    ],
)
def test_removing_an_allowed_line_earns_no_credit(
    tmp_path: Path,
    entry_point: Callable[[Path, str], int],
    head_line: str,
    expected: int,
) -> None:
    repo, base = _repo_with_directive_base(tmp_path, head_line)
    assert entry_point(repo, base) == expected
