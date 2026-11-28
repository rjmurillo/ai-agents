"""Exact-entry Semgrep allow path in the security-suppression gate (issue #7591).

The owner ruled that the two Semgrep findings on ``_launch`` in ``ptk_run.py``
are suppressed inline. The gate allows a suppression line only when it is a
whole-line directive naming one rule id that is listed against that exact path.
Everything else stays blocked, and an emptied allowlist blocks again.

This file covers the line predicate and the allowlist itself. End-to-end entry
points and line separators have their own files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy
from tests.validation._suppression_gate_repo import (
    DIRECTIVE,
    EXEC_RULE,
    NOQA,
    NOSEC,
    SOURCE,
    SUBPROCESS_RULE,
    allowed,
)

_ROOT = Path(__file__).resolve().parents[2]


# --- is_blocked_suppression_line: unit level --------------------------------


@pytest.mark.parametrize("path", [entry.path for entry in policy.ALLOWED_SEMGREP_SUPPRESSIONS])
@pytest.mark.parametrize("rule", [EXEC_RULE, SUBPROCESS_RULE])
def test_listed_rule_on_listed_path_passes(path: str, rule: str) -> None:
    assert policy.is_blocked_suppression_line(path, allowed(rule)) is False


@pytest.mark.parametrize(
    "line",
    [
        allowed(EXEC_RULE, indent=""),
        allowed(EXEC_RULE, indent="\t"),
        allowed(EXEC_RULE) + f"  {NOQA}: E501",
    ],
)
def test_allowed_forms_pass(line: str) -> None:
    assert policy.is_blocked_suppression_line(SOURCE, line) is False


def test_path_is_normalized_before_lookup() -> None:
    assert (
        policy.is_blocked_suppression_line("src/claude/./lib/ptk_run.py", allowed(EXEC_RULE))
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
        pytest.param(SOURCE, allowed(EXEC_RULE) + f"  {NOSEC}", id="nosec-after"),
        pytest.param(SOURCE, allowed(EXEC_RULE) + f"  {NOQA}: S603", id="noqa-s-after"),
        pytest.param(SOURCE, allowed(EXEC_RULE) + f"  {NOQA}", id="bare-noqa-after"),
        pytest.param(SOURCE, allowed(EXEC_RULE) + f"  {DIRECTIVE}", id="second-bare-directive"),
        pytest.param(SOURCE, allowed(EXEC_RULE) + " trailing", id="trailing-text"),
        pytest.param(SOURCE, allowed(EXEC_RULE) + "  # reason", id="trailing-comment"),
        pytest.param(
            SOURCE,
            allowed(EXEC_RULE) + "  # see, python.lang.security.audit.other.other",
            id="trailing-extra-rule-id",
        ),
        pytest.param(SOURCE, allowed(EXEC_RULE) + f" {NOQA}: E501", id="waiver-one-space"),
        pytest.param(SOURCE, allowed(EXEC_RULE) + f"  {NOQA}: E501,S603", id="waiver-plus-s"),
        pytest.param(SOURCE, allowed(EXEC_RULE) + f"  {NOQA}: E501 ", id="waiver-trailing-space"),
        pytest.param("src/claude/lib/paths.py", allowed(EXEC_RULE), id="unlisted-file"),
        pytest.param(".claude/lib/ptk_run.py", allowed(EXEC_RULE), id="symlink-path"),
        pytest.param("ptk_run.py", allowed(EXEC_RULE), id="basename-only"),
        pytest.param("x/src/claude/lib/ptk_run.py", allowed(EXEC_RULE), id="nested-path"),
        pytest.param("src/claude/lib/ptk_run.ipynb", allowed(EXEC_RULE), id="other-suffix"),
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
    assert policy.is_blocked_suppression_line(SOURCE, allowed(EXEC_RULE)) is True


# --- the allowlist itself ----------------------------------------------------


def _tracked_ptk_run_copies() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-s", "--", "*lib/ptk_run.py"],
        cwd=_ROOT,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    copies = set()
    for row in result.stdout.splitlines():
        meta, path = row.split("\t", 1)
        if meta.split(" ", 1)[0] in {"100644", "100755"}:
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
