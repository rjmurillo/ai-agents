"""Exact-entry Semgrep allow path in the security-suppression gate (issue #7591).

The owner ruled that the two Semgrep findings on ``_launch`` in ``ptk_run.py``
are suppressed inline. The gate allows a suppression line only when it is a
whole-line directive naming one rule id that is listed against that exact path.
Everything else stays blocked, and an emptied allowlist blocks again.

Directive tokens are assembled at runtime so this file does not trip the gate
it exercises.
"""

from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy

_ROOT = Path(__file__).resolve().parents[2]

DIRECTIVE = "# " + "nosem" + "grep"
NOSEC = "# " + "nos" + "ec"
NOQA = "# " + "no" + "qa"
EXEC_RULE = (
    "python.lang.security.audit.dangerous-os-exec-tainted-env-args."
    "dangerous-os-exec-tainted-env-args"
)
SUBPROCESS_RULE = (
    "python.lang.security.audit.dangerous-subprocess-use-tainted-env-args."
    "dangerous-subprocess-use-tainted-env-args"
)
SOURCE = "src/claude/lib/ptk_run.py"


def _allowed(rule: str, indent: str = "    ") -> str:
    return f"{indent}{DIRECTIVE}: {rule}"


# --- is_blocked_suppression_line: unit level --------------------------------


@pytest.mark.parametrize("path", [entry.path for entry in policy.ALLOWED_SEMGREP_SUPPRESSIONS])
@pytest.mark.parametrize("rule", [EXEC_RULE, SUBPROCESS_RULE])
def test_listed_rule_on_listed_path_passes(path: str, rule: str) -> None:
    assert policy.is_blocked_suppression_line(path, _allowed(rule)) is False


@pytest.mark.parametrize(
    "line",
    [
        _allowed(EXEC_RULE, indent=""),
        _allowed(EXEC_RULE, indent="\t"),
        _allowed(EXEC_RULE) + f"  {NOQA}: E501",
        _allowed(EXEC_RULE) + "  # owner ruling, issue 7591",
    ],
)
def test_allowed_forms_pass(line: str) -> None:
    assert policy.is_blocked_suppression_line(SOURCE, line) is False


def test_path_is_normalized_before_lookup() -> None:
    assert (
        policy.is_blocked_suppression_line("src/claude/./lib/ptk_run.py", _allowed(EXEC_RULE))
        is False
    )


def test_line_without_suppression_never_blocks() -> None:
    assert policy.is_blocked_suppression_line("anywhere.py", "os.execv(a, b)") is False


@pytest.mark.parametrize(
    ("path", "line"),
    [
        pytest.param(SOURCE, f"    {DIRECTIVE}", id="bare-directive"),
        pytest.param(SOURCE, f"    {DIRECTIVE}  # reason", id="bare-with-comment"),
        pytest.param(SOURCE, f"    #{DIRECTIVE[2:]}: {EXEC_RULE}", id="no-space-after-hash"),
        pytest.param(SOURCE, f"    {DIRECTIVE}:{EXEC_RULE}", id="no-space-after-colon"),
        pytest.param(SOURCE, f"    {DIRECTIVE}:  {EXEC_RULE}", id="two-spaces-after-colon"),
        pytest.param(SOURCE, f"    {DIRECTIVE.upper()}: {EXEC_RULE}", id="uppercase"),
        pytest.param(SOURCE, f"    {DIRECTIVE[:-4]}: {EXEC_RULE}", id="short-form"),
        pytest.param(SOURCE, f"    //{DIRECTIVE[1:]}: {EXEC_RULE}", id="slash-marker"),
        pytest.param(SOURCE, f"    {DIRECTIVE}: {EXEC_RULE}, {SUBPROCESS_RULE}", id="rule-list"),
        pytest.param(
            SOURCE, f"    {DIRECTIVE}: {EXEC_RULE},{SUBPROCESS_RULE}", id="rule-list-tight"
        ),
        pytest.param(
            SOURCE, f"    {DIRECTIVE}: dangerous-os-exec-tainted-env-args", id="short-rule-id"
        ),
        pytest.param(SOURCE, f"    {DIRECTIVE}: {EXEC_RULE}.extra", id="extended-rule-id"),
        pytest.param(SOURCE, f"    {DIRECTIVE}: {EXEC_RULE}x", id="rule-id-suffix"),
        pytest.param(SOURCE, f"    {DIRECTIVE}: python.lang.security.audit", id="rule-prefix"),
        pytest.param(SOURCE, f"    {DIRECTIVE}: other.rule.id", id="unlisted-rule"),
        pytest.param(
            SOURCE, f"    os.execv(a, b)  {DIRECTIVE}: {EXEC_RULE}", id="trailing-on-code"
        ),
        pytest.param(SOURCE, _allowed(EXEC_RULE) + f"  {NOSEC}", id="nosec-after"),
        pytest.param(SOURCE, _allowed(EXEC_RULE) + f"  {NOQA}: S603", id="noqa-s-after"),
        pytest.param(SOURCE, _allowed(EXEC_RULE) + f"  {NOQA}", id="bare-noqa-after"),
        pytest.param(SOURCE, _allowed(EXEC_RULE) + f"  {DIRECTIVE}", id="second-bare-directive"),
        pytest.param(SOURCE, _allowed(EXEC_RULE) + " trailing", id="trailing-text"),
        pytest.param("src/claude/lib/paths.py", _allowed(EXEC_RULE), id="unlisted-file"),
        pytest.param(".claude/lib/ptk_run.py", _allowed(EXEC_RULE), id="symlink-path"),
        pytest.param("ptk_run.py", _allowed(EXEC_RULE), id="basename-only"),
        pytest.param("x/src/claude/lib/ptk_run.py", _allowed(EXEC_RULE), id="nested-path"),
        pytest.param("src/claude/lib/ptk_run.ipynb", _allowed(EXEC_RULE), id="other-suffix"),
    ],
)
def test_everything_else_stays_blocked(path: str, line: str) -> None:
    assert policy.is_blocked_suppression_line(path, line) is True


@pytest.mark.parametrize(
    "token",
    [
        "# " + "nos" + "ec",
        "# " + "no" + "qa: S603",
        "# " + "ruff: no" + "qa: S603",
        "// " + "lg" + "tm[js/x]",
        "// " + "code" + "ql[py/x]",
        "# " + "cwe-" + "suppress",
    ],
)
def test_other_suppression_forms_stay_blocked_on_listed_path(token: str) -> None:
    assert policy.is_blocked_suppression_line(SOURCE, f"x = 1  {token}") is True


def test_empty_allowlist_blocks_listed_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy, "ALLOWED_SEMGREP_SUPPRESSIONS", ())
    assert policy.is_blocked_suppression_line(SOURCE, _allowed(EXEC_RULE)) is True


# --- the allowlist itself ----------------------------------------------------


def _tracked_ptk_run_copies() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-s", "--", "*lib/ptk_run.py"],
        cwd=_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    copies = set()
    for row in result.stdout.splitlines():
        meta, path = row.split("\t", 1)
        if meta.split(" ", 1)[0] == "100644":
            copies.add(path)
    return copies


def test_allowlist_names_every_tracked_copy_and_nothing_else() -> None:
    paths = {entry.path for entry in policy.ALLOWED_SEMGREP_SUPPRESSIONS}
    assert paths == _tracked_ptk_run_copies()


def test_every_entry_is_exact_and_carries_a_reason() -> None:
    entries = policy.ALLOWED_SEMGREP_SUPPRESSIONS
    assert len(entries) == len({(entry.path, entry.rule_id) for entry in entries})
    for entry in entries:
        assert entry.rule_id in {EXEC_RULE, SUBPROCESS_RULE}
        assert entry.reason.strip()
        assert not any(char in entry.path for char in "*?[]")
        assert not entry.path.endswith("/")


def test_real_copies_pass_and_fail_closed_without_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = sorted(_tracked_ptk_run_copies())
    assert policy.check_security_suppressions(paths, _ROOT) == 0
    monkeypatch.setattr(policy, "ALLOWED_SEMGREP_SUPPRESSIONS", ())
    assert policy.check_security_suppressions(paths, _ROOT) == 1


def test_real_source_carries_both_rule_ids() -> None:
    text = (_ROOT / SOURCE).read_text(encoding="utf-8")
    assert f"{DIRECTIVE}: {EXEC_RULE}" in text
    assert f"{DIRECTIVE}: {SUBPROCESS_RULE}" in text


# --- staged, push, and CI diff: end to end -----------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


BASE_BODY = "import os\n\n\ndef launch(command):\n    os.execv(command[0], command)\n"


def _body(directive_line: str) -> str:
    return (
        "import os\n\n\ndef launch(command):\n"
        f"{directive_line}\n"
        "    os.execv(command[0], command)\n"
    )


def _repo_with_change(tmp_path: Path, path: str, directive_line: str) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(BASE_BODY, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    target.write_text(_body(directive_line), encoding="utf-8")
    _git(repo, "add", "-A")
    return repo, base


def _staged(repo: Path, _base: str) -> int:
    return policy.check_staged_suppressions(repo)


def _pushed(repo: Path, base: str) -> int:
    _git(repo, "commit", "-q", "-m", "head")
    head = _git(repo, "rev-parse", "HEAD")
    stream = io.StringIO(f"refs/heads/feature {head} refs/heads/feature {base}\n")
    return policy.check_pushed_suppressions(stream, repo)


def _ci_diff(repo: Path, base: str) -> int:
    _git(repo, "commit", "-q", "-m", "head")
    return policy.check_suppression_diff(base, repo)


ENTRY_POINTS: list[Callable[[Path, str], int]] = [_staged, _pushed, _ci_diff]
ENTRY_IDS = ["staged", "push", "ci-diff"]


@pytest.mark.parametrize("entry_point", ENTRY_POINTS, ids=ENTRY_IDS)
@pytest.mark.parametrize(
    ("path", "directive_line", "expected"),
    [
        pytest.param(SOURCE, _allowed(EXEC_RULE), 0, id="listed"),
        pytest.param(SOURCE, _allowed(EXEC_RULE) + f"  {NOQA}: E501", 0, id="listed-noqa-e501"),
        pytest.param("src/muse/lib/ptk_run.py", _allowed(SUBPROCESS_RULE), 0, id="listed-copy"),
        pytest.param(SOURCE, f"    {DIRECTIVE}", 1, id="bare"),
        pytest.param(SOURCE, f"    {DIRECTIVE}: other.rule", 1, id="unlisted-rule"),
        pytest.param("src/claude/lib/paths.py", _allowed(EXEC_RULE), 1, id="unlisted-path"),
        pytest.param(SOURCE, _allowed(EXEC_RULE) + f"  {NOSEC}", 1, id="nosec-after"),
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
    repo, base = _repo_with_change(tmp_path, path, directive_line)
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
    repo, base = _repo_with_change(tmp_path, SOURCE, _allowed(EXEC_RULE))
    assert entry_point(repo, base) == 1


# --- the rename-promotion and notebook sites ---------------------------------


def test_full_content_scan_applies_the_same_rule() -> None:
    text = _body(_allowed(EXEC_RULE))
    assert policy._full_content_suppression_violations("HEAD", SOURCE, text) == []
    assert policy._full_content_suppression_violations("HEAD", "src/claude/lib/paths.py", text) == [
        "HEAD:src/claude/lib/paths.py:5"
    ]


def test_notebook_scan_never_allows_a_listed_line() -> None:
    def notebook(source: list[str]) -> str:
        return json.dumps({"cells": [{"cell_type": "code", "source": source}]})

    base = notebook(["x = 1\n"])
    head = notebook(["x = 1\n", _allowed(EXEC_RULE, indent="") + "\n"])
    assert policy._notebook_suppression_violations_for_text("HEAD", "n.ipynb", base, head) == [
        "HEAD:n.ipynb:2"
    ]
