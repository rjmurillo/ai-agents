"""Tests for the bot-cascade warning Phase 5c in .githooks/pre-push (REQ-011).

Pattern: structural verification of the bash hook (string-presence and
syntax). Same pattern as test_drift_check.py for Phase 5b. Bash hooks are
thin delegates; static verification is sufficient.

Acceptance criteria pinned:

- REQ-011-01: unresolved threads emit warn (not block).
- REQ-011-02: incomplete pagination emits skip, not pass.
- REQ-011-03: recent bot review under 120s emits warn.
- REQ-011-04: gh api auth failures emit skip, not swallow as pass.
- REQ-011-05: each recorder outcome (skip/warn/pass) has a call site;
  reviews query and bot filter are matched on non-comment lines so a
  test cannot pass on comment text alone.

Refs:
- REQ-011 (acceptance criteria)
- DESIGN-011 (architecture, test strategy)
- PR #1989 retrospective (highest-leverage bot-cascade intervention)
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PRE_PUSH_HOOK = REPO_ROOT / ".githooks" / "pre-push"


def _hook_text() -> str:
    return PRE_PUSH_HOOK.read_text(encoding="utf-8")


def _phase_5c_block() -> str:
    """Return only the Phase 5c block of the hook for scoped grep.

    Phase 5c starts at the header comment and ends at the next phase header
    or end of file. This scopes assertions so we do not accidentally match
    other phases.
    """
    text = _hook_text()
    # Match from "Phase 5c" header to next phase or end of file.
    pattern = re.compile(
        r"# Phase 5c.*?(?=# Phase \d|\Z)",
        re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(0) if match else ""


def _phase_5c_code_lines() -> list[str]:
    """Return Phase 5c lines that are not pure comments.

    Used by tests that pin the *behavior* (an actual command invocation,
    a jq filter) rather than mere documentation. A comment that mentions
    `/reviews` or `Bot` must not satisfy these assertions.
    """
    return [
        line
        for line in _phase_5c_block().splitlines()
        if not line.lstrip().startswith("#")
    ]


def test_phase_5c_header_present() -> None:
    """REQ-011-01: Phase 5c block exists after Phase 5b.

    Guards the ordering invariant from DESIGN-011: Phase 5c must follow
    Phase 5b. The `find` calls return -1 on miss; assert non-negative
    positions explicitly so a missing Phase 5b cannot satisfy the
    "5b < 5c" check by accident (copilot finding on PR #2011).
    """
    text = _hook_text()
    assert "Phase 5c" in text, (
        "REQ-011-01: pre-push hook must include a Phase 5c block"
    )
    phase_5b_pos = text.find("Phase 5b")
    phase_5c_pos = text.find("Phase 5c")
    assert phase_5b_pos >= 0, "Phase 5b header must exist before Phase 5c"
    assert phase_5c_pos >= 0, "Phase 5c header must exist"
    assert phase_5b_pos < phase_5c_pos, "Phase 5c must follow Phase 5b"


def test_phase_5c_calls_unresolved_threads_script() -> None:
    """REQ-011-01: hook queries unresolved threads via canonical script."""
    block = _phase_5c_block()
    assert "get_unresolved_review_threads.py" in block, (
        "REQ-011-01: hook must invoke get_unresolved_review_threads.py"
    )


def test_phase_5c_parses_fetched_pages_complete() -> None:
    """REQ-011-02: hook parses fetched_pages_complete BEFORE trusting count."""
    block = _phase_5c_block()
    assert "fetched_pages_complete" in block, (
        "REQ-011-02: hook must check fetched_pages_complete; "
        "incomplete pagination cannot be trusted"
    )


def test_phase_5c_emits_warn_on_unresolved() -> None:
    """REQ-011-01: a non-comment record_warn line names unresolved threads.

    Bare `record_warn` is too weak (the recent-bot-review path also calls
    it) and bare `unresolved` is too weak (comments say "zero unresolved").
    Assert a non-comment line invokes `record_warn` AND mentions
    "unresolved thread" so removing the unresolved-thread branch fails the
    test (copilot finding on PR #2011).
    """
    code = _phase_5c_code_lines()
    assert any(
        "record_warn" in line and "unresolved thread" in line for line in code
    ), (
        "REQ-011-01: a non-comment line must call `record_warn` with a "
        "message referencing 'unresolved thread(s)'"
    )


def test_phase_5c_emits_skip_on_incomplete() -> None:
    """REQ-011-02: a non-comment record_skip line names the incomplete snapshot.

    Bare `record_skip` is too weak (many branches call it: gh missing, no
    PR, JSON parse failed). Assert a non-comment line invokes `record_skip`
    with a message naming the incomplete-snapshot condition
    ("fetched_pages_complete") so removing that specific SKIP branch fails
    the test (copilot finding on PR #2011).
    """
    code = _phase_5c_code_lines()
    assert any(
        "record_skip" in line and "fetched_pages_complete" in line
        for line in code
    ), (
        "REQ-011-02: a non-comment line must call `record_skip` with a "
        "message naming the incomplete-snapshot condition "
        "('fetched_pages_complete=false')"
    )


def test_phase_5c_queries_reviews_endpoint() -> None:
    """REQ-011-03: hook actually invokes gh api on the /reviews endpoint.

    Asserts on a non-comment line so a stray `/reviews` mention in a
    comment cannot satisfy this test if the real call were removed
    (copilot finding on PR #2011).
    """
    code = _phase_5c_code_lines()
    assert any(
        "gh api" in line and "pulls/" in line and "/reviews" in line
        for line in code
    ), (
        "REQ-011-03: a non-comment line must invoke `gh api ... pulls/.../reviews` "
        "to find bot review timestamps"
    )


def test_phase_5c_filters_bot_reviews() -> None:
    """REQ-011-03: hook filters reviews to user.type == "Bot".

    Asserts the literal jq filter expression appears on a non-comment
    line; the substring "Bot" alone is too weak (it also appears in the
    "Bot-cascade" phase title) and would not fail if the filter were
    removed (copilot finding on PR #2011).
    """
    code = _phase_5c_code_lines()
    assert any('.user.type == "Bot"' in line for line in code), (
        'REQ-011-03: a non-comment line must contain the jq filter '
        '`.user.type == "Bot"`'
    )


def test_phase_5c_120_second_threshold() -> None:
    """REQ-011-03: hook uses 120-second threshold for recent bot reviews."""
    block = _phase_5c_block()
    assert "120" in block, (
        "REQ-011-03: hook must reference the 120-second threshold from DESIGN-011"
    )


def test_phase_5c_no_fail_open_on_reviews() -> None:
    """REQ-011-04: no `|| true` fail-open in Phase 5c executable code.

    PR #1989's M5 had `gh api ... || true` that swallowed auth failures
    as a false PASS. Asserts `|| true` does not appear on any non-comment
    line of the Phase 5c block (stronger and robust to multiline `gh api`
    continuations than scanning only lines that mention `gh api`;
    coderabbit finding on PR #2011). The Phase 5c header comment quotes
    the historical anti-pattern verbatim, so comment lines are stripped
    before the check. Error fall-through in Phase 5c uses
    `|| echo '<sentinel>'`, never `|| true`.
    """
    for line in _phase_5c_code_lines():
        assert "|| true" not in line, (
            "REQ-011-04: Phase 5c must not use `|| true`; it swallows "
            "external-call failures as PASS. Use `|| echo '<sentinel>'` and "
            f"route the sentinel to record_skip. Offending line: {line.strip()}"
        )


def test_phase_5c_classifies_review_api_failure() -> None:
    """REQ-011-04: SKIP message names the failure mode, not just the exit code.

    REQ-011 line 164 requires the SKIP message to classify the failure
    (auth / rate-limit / network) and use the literal string "gh api auth
    failed" for the auth case. Asserts the hook contains the classifier
    strings and greps stderr for the auth signals (copilot finding on
    PR #2011).
    """
    block = _phase_5c_block()
    assert "gh api auth failed" in block, (
        "REQ-011-04: SKIP message must use the literal 'gh api auth failed' "
        "for auth-class failures"
    )
    assert "gh api rate-limited" in block, (
        "REQ-011-04: SKIP message must classify rate-limit failures"
    )
    assert "gh api network error" in block, (
        "REQ-011-04: SKIP message must classify network failures"
    )
    # The classifier must inspect captured stderr, not guess.
    code = _phase_5c_code_lines()
    assert any("REVIEW_STDERR" in line and "grep" in line for line in code), (
        "REQ-011-04: failure classification must grep the captured stderr"
    )


def test_phase_5c_warn_only_never_fails() -> None:
    """REQ-011-01..04: Phase 5c is warn-only; never INVOKES record_fail.

    Strips comment lines before matching so the design comment that says
    "Never calls record_fail" does not register as a call site.
    """
    for line in _phase_5c_code_lines():
        assert "record_fail" not in line, (
            f"Phase 5c is warn-only; record_fail must NOT be called. "
            f"Line: {line.strip()}"
        )


def test_pre_push_hook_bash_syntax_valid() -> None:
    """Hook must parse without syntax errors after Phase 5c additions."""
    bash_path = shutil.which("bash")
    if bash_path is None:
        pytest.skip("bash not available on this platform")
    # Invoke the resolved absolute path, not the bare name, so the test
    # exercises the same binary it checked for (coderabbit finding /
    # Ruff S607 on PR #2011).
    result = subprocess.run(
        [bash_path, "-n", str(PRE_PUSH_HOOK)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, (
        f"pre-push hook has bash syntax error:\n{result.stderr}"
    )


def test_phase_5c_emits_recorded_outcome_token() -> None:
    """REQ-011-05: Phase 5c contains a call site for every recorder outcome.

    Structural verification that the three recorder functions used by the
    contract (`record_skip`, `record_warn`, `record_pass`) each have at
    least one call site inside the Phase 5c block. If any of the three is
    absent, the corresponding REQ-011-01..04 acceptance branch is
    unreachable.

    End-to-end runtime evidence belongs to REQ-011-06 (self-apply gate),
    not this test. Invoking the full hook here would execute Phase 4 (the
    whole pytest suite, ~3 minutes per case), so the self-apply runtime
    evidence is captured in the PR description against the live PR.
    """
    block = _phase_5c_block()
    for fn in ("record_skip", "record_warn", "record_pass"):
        # Match the call form `fn "..."` (a string-literal first arg) so a
        # mere mention in a comment does not satisfy the assertion.
        pattern = re.compile(rf'(?m)^\s*{fn}\s+"', re.MULTILINE)
        assert pattern.search(block), (
            f"REQ-011-05: Phase 5c must contain at least one {fn} call site. "
            "If a branch is removed, document the deferral in DESIGN-011 first."
        )
