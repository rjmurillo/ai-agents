"""The push-lock gate over unfenced prose (issue #4635).

A recipe does not become canonical by losing its fence.
``LOCK=/var/locks/branch.lock`` followed by ``flock "$LOCK" git push`` was
reported inside a fence and invisible outside one, because the unfenced path
read each line alone: the assignment line has no ``flock`` and the ``flock``
line has no path. Every test here is the unfenced mirror of a fenced test in
``test_check_push_lock_paths.py`` and must agree with it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import check_push_lock_paths as checker
from tests.validation._push_lock_fixtures import _fence, _init_repo, _prose


def test_an_unfenced_lock_path_held_in_a_variable_is_caught() -> None:
    """The reproduction from issue #4635, verbatim in shape."""
    text = _prose(
        "Use this recipe:",
        "LOCK=/var/locks/branch.lock",
        'flock "$LOCK" git push origin "$BR"',
    )

    assert checker.scan_text(text) == [(2, "/var/locks/branch.lock")]


def test_the_fenced_and_unfenced_variable_recipes_agree() -> None:
    """The gap was the disagreement, so pin the agreement, not just the fix."""
    recipe = ['LOCK="/tmp/push-lock-$SLUG.lock"', 'flock "$LOCK" git push']

    fenced = checker.scan_text(_fence(*recipe))
    unfenced = checker.scan_text(_prose(*recipe))

    assert [path for _line, path in fenced] == [path for _line, path in unfenced]


def test_an_unfenced_reassignment_after_the_flock_does_not_clean_the_recipe() -> None:
    """Unfenced mirror: a later canonical rebind cannot launder the bad path."""
    text = _prose(
        "LOCK=/tmp/bad.lock",
        'flock "$LOCK" git push',
        'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock"',
    )

    assert checker.scan_text(text) == [(1, "/tmp/bad.lock")]


def test_an_unfenced_bad_reassignment_after_a_canonical_flock_is_accepted() -> None:
    """Unfenced mirror of the opposite sign: no false positive either."""
    text = _prose(
        'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock"',
        'flock "$LOCK" git push',
        "LOCK=/tmp/bad.lock",
    )

    assert checker.scan_text(text) == []


def test_an_unfenced_commented_assignment_does_not_launder_the_live_one() -> None:
    """Unfenced mirror: a comment binds nothing here either."""
    text = _prose(
        "LOCK=/tmp/bad.lock",
        '# LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock"',
        'flock "$LOCK" git push',
    )

    assert checker.scan_text(text) == [(1, "/tmp/bad.lock")]


def test_an_unfenced_terminator_attached_to_the_argument_still_resolves() -> None:
    """Unfenced mirror of the attached-terminator shape."""
    text = _prose("LOCK=/tmp/bad.lock", 'flock "$LOCK"; git push')

    assert checker.scan_text(text) == [(1, "/tmp/bad.lock")]


def test_an_unfenced_same_line_rebind_is_not_read_as_the_lock() -> None:
    """Unfenced mirror: a trailing rebind is a statement no `flock` reads."""
    text = _prose(
        'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock" ; '
        'flock "$LOCK" git push ; LOCK=/tmp/bad.lock'
    )

    assert checker.scan_text(text) == []


def test_every_unfenced_flock_on_one_line_is_inspected() -> None:
    """Unfenced mirror: the second call on the line opens the rogue path."""
    text = _prose(
        'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock" ; '
        'flock "$LOCK" git push ; LOCK=/tmp/rogue ; flock "$LOCK" git push'
    )

    assert [path for _line, path in checker.scan_text(text)] == ["/tmp/rogue"]


def test_an_unfenced_file_descriptor_form_is_caught() -> None:
    text = _prose("exec 9>/tmp/aiagents-push.lock", "flock -n 9", "git push")

    assert checker.scan_text(text) == [(1, "/tmp/aiagents-push.lock")]


def test_an_unfenced_continuation_line_is_caught() -> None:
    text = _prose("flock \\", "  /tmp/push-lock.lock \\", "  git push")

    assert checker.scan_text(text) == [(2, "/tmp/push-lock.lock")]


def test_an_unfenced_extensionless_lock_is_named() -> None:
    text = _prose("LOCK=/tmp/aiagents-push", 'flock "$LOCK" git push')

    assert checker.scan_text(text) == [(1, "/tmp/aiagents-push")]


def test_the_unfenced_canonical_variable_recipe_is_accepted() -> None:
    text = _prose(
        'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock"',
        'mkdir -p "$(dirname "$LOCK")"',
        'flock "$LOCK" git push origin "$BR"',
    )

    assert checker.scan_text(text) == []


def test_an_unfenced_run_naming_flock_without_a_path_is_not_a_violation() -> None:
    """Prose discusses `flock`; only a fence is unambiguously a prescription.

    Reporting the empty "names no canonical path" finding over unfenced runs
    fired on 13 tracked files that merely mention the tool, this rule's own
    mirror among them. Measured before the fix landed.
    """
    text = _prose(
        "`flock` excludes only processes that open the same path, so a second",
        "lock name is not a second lock: it is no lock at all against the first.",
    )

    assert checker.scan_text(text) == []


def test_an_unfenced_run_marked_historical_is_skipped() -> None:
    """The fence's opt-out token works on a paragraph too.

    A census paragraph names the dead schemes next to the word `flock`. That
    is evidence, and rewriting it to match the rule would destroy the record.
    """
    text = _prose(
        "Measured 2026-08-02: three schemes were live at once, and `flock`",
        "only excludes processes that agree on the path, so /tmp/aiagents-push.lock",
        "and /tmp/aiagents-push-$SLOT.lock bought nothing.",
        "<!-- push-lock-historical: the census, evidence not a recipe. -->",
    )

    assert checker.scan_text(text) == []


def test_a_fence_naming_no_lock_target_is_still_reported() -> None:
    """The other half of the asymmetry: a fence IS unambiguously a recipe.

    Pins the branch that prose deliberately skips, so a later edit cannot
    silence both units at once.
    """
    text = _fence("flock -n 9", "git push")

    assert checker.scan_text(text) == [(2, "")]


def test_the_no_path_message_reaches_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, {"docs/push.md": _fence("flock -n 9", "git push")})

    assert checker.main(["--repo-root", str(repo)]) == 1
    assert "names no canonical lock path" in capsys.readouterr().err


def test_a_blank_line_bounds_the_unfenced_run() -> None:
    """A variable set in one paragraph must not resolve a `flock` in another.

    Without the blank-line boundary the whole file is one unit, so an unrelated
    assignment far above silently becomes the reported lock path. The `flock`
    is reported for naming no readable path rather than being passed clean:
    not resolving is a reason to speak up, not a reason to stay quiet.
    """
    text = _prose(
        "LOCK=/tmp/unrelated.lock",
        "",
        'flock "$LOCK" git push',
    )

    findings = checker.scan_text(text)

    assert findings == [(3, "")]
    assert "/tmp/unrelated.lock" not in [path for _line, path in findings]


def test_an_unfenced_flock_on_an_unassigned_variable_is_reported() -> None:
    """The narrow exception to the prose asymmetry.

    A recipe that takes its lock from an environment variable set elsewhere
    reads no path this checker can verify, and silently passing it is the same
    invisibility the three-scheme census of issue #4366 ran on. A fence already
    reports this; unfenced prose used to swallow it.
    """
    text = _prose("LOCK=$SOME_EXTERNAL_ENV", 'flock "$LOCK" git push')

    assert checker.scan_text(text) == [(2, "")]


def test_prose_about_flock_still_reports_nothing_after_that_exception() -> None:
    """The exception keys on a bare variable, which prose never hands `flock`.

    Guards the inverse: widening detection must not start firing on the 13
    tracked files that only discuss the tool.
    """
    text = _prose(
        "`flock` excludes only processes that open the same path, so naming it",
        "differently in two places buys nothing at all.",
    )

    assert checker.scan_text(text) == []


def test_the_historical_marker_does_not_leak_past_its_paragraph() -> None:
    text = _prose(
        "<!-- push-lock-historical -->",
        "LOCK=/tmp/dead.lock",
        'flock "$LOCK" git push',
        "",
        "LOCK=/tmp/live.lock",
        'flock "$LOCK" git push',
    )

    assert [path for _line, path in checker.scan_text(text)] == ["/tmp/live.lock"]


def test_an_unfenced_run_beside_a_fence_is_still_scanned() -> None:
    """Fenced and unfenced units coexist in one document without shadowing."""
    text = "".join(
        [
            _fence("flock /tmp/fenced.lock git push"),
            _prose("LOCK=/tmp/unfenced.lock", 'flock "$LOCK" git push'),
        ]
    )

    assert [path for _line, path in checker.scan_text(text)] == [
        "/tmp/fenced.lock",
        "/tmp/unfenced.lock",
    ]


def test_an_unfenced_violation_reaches_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End to end: the new unit reports through `main`, not only `scan_text`."""
    repo = tmp_path / "repo"
    _init_repo(
        repo,
        {"docs/push.md": 'LOCK=/tmp/rogue.lock\nflock "$LOCK" git push\n'},
    )

    assert checker.main(["--repo-root", str(repo)]) == 1
    # The file and the line are asserted together on purpose: split apart they
    # no longer pin that the report attributes the line to the file.
    # citation-freshness: ignore -- the fixture this test wrote into tmp_path
    assert "docs/push.md:1" in capsys.readouterr().err
