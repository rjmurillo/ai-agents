"""One push-lock path, enforced over tracked prescriptions (issue #4366).

``flock`` excludes only processes that open the same path, so a second lock name
is not a second lock. Three schemes were live at once and only a ``ps`` census
found them.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.validation import check_push_lock_paths as checker
from tests.validation._push_lock_fixtures import CANONICAL_LINE, _fence, _init_repo


def test_canonical_path_is_accepted() -> None:
    assert checker.scan_text(CANONICAL_LINE) == []


def test_braced_home_is_accepted() -> None:
    line = 'flock "${HOME}/src/scratch/locks/push-lock-fix-foo.lock" git push'

    assert checker.scan_text(line) == []


def test_tmp_path_is_rejected() -> None:
    findings = checker.scan_text('flock "/tmp/push-lock-$SLUG.lock" git push')

    assert findings == [(1, "/tmp/push-lock-$SLUG.lock")]


def test_hashed_slot_scheme_is_rejected() -> None:
    findings = checker.scan_text("flock /tmp/aiagents-push-$SLOT.lock git push")

    assert [path for _line, path in findings] == ["/tmp/aiagents-push-$SLOT.lock"]


def test_literal_home_directory_is_rejected() -> None:
    findings = checker.scan_text(
        'flock "/home/richard/src/GitHub/rjmurillo/ai-agents-pushpol2-push-${SLUG}.lock" git push'
    )

    assert len(findings) == 1


def test_unquoted_canonical_path_is_accepted() -> None:
    assert checker.scan_text("flock $HOME/src/scratch/locks/push-lock-x.lock git push") == []


def test_variable_reassignment_uses_the_last_value_before_flock() -> None:
    text = "\n".join(
        [
            "```bash",
            "LOCK=/tmp/bad.lock",
            'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock"',
            'flock "$LOCK" git push',
            "```",
        ]
    )

    assert checker.scan_text(text) == []


def test_a_reassignment_after_the_flock_does_not_clean_the_recipe() -> None:
    """The `flock` opened the path live at its own line, not the block's last.

    Reading the block's final value let a bad path be laundered by a canonical
    reassignment placed below the `flock` that already used it, which is the
    exact fourth-scheme shape this gate exists to catch (issue #4366).
    """
    text = _fence(
        "LOCK=/tmp/bad.lock",
        'flock "$LOCK" git push',
        'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock"',
    )

    assert checker.scan_text(text) == [(2, "/tmp/bad.lock")]


def test_a_bad_reassignment_after_a_canonical_flock_is_not_a_violation() -> None:
    """The inverse: a later rebind cannot reach backwards to dirty the call.

    Same defect, opposite sign. Reading the block's final value reported a
    violation against a `flock` that opened the canonical path.
    """
    text = _fence(
        'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock"',
        'flock "$LOCK" git push',
        "LOCK=/tmp/bad.lock",
    )

    assert checker.scan_text(text) == []


def test_each_flock_resolves_against_its_own_live_assignment() -> None:
    """Two `flock` calls, one variable, two different locks. Both are read."""
    text = _fence(
        "LOCK=/tmp/first.lock",
        'flock "$LOCK" git push',
        "LOCK=/tmp/second.lock",
        'flock "$LOCK" git push',
    )

    assert checker.scan_text(text) == [(2, "/tmp/first.lock"), (4, "/tmp/second.lock")]


def test_an_assignment_sharing_the_flock_line_still_resolves() -> None:
    """The sanctioned one-liner sets and uses the name on the same line."""
    text = _fence('LOCK=/tmp/bad.lock ; flock "$LOCK" git push')

    assert [path for _line, path in checker.scan_text(text)] == ["/tmp/bad.lock"]


def test_an_assignment_after_the_flock_on_one_line_does_not_resolve_backwards() -> None:
    """Ordering is by position, not by line, so a shared line is not a loophole.

    Comparing line numbers alone let `flock "$LOCK" ; LOCK=...` resolve forward
    to an assignment that runs after the call, the same defect the multi-line
    case had, one granularity down. The lock is written without the `.lock`
    suffix so no bare token can satisfy the assertion by accident: the variable
    is the only route to a path here, it no longer resolves, and the fence is
    reported for naming no canonical path rather than reading the wrong one.
    """
    text = _fence('flock "$LOCK" git push ; LOCK=/tmp/aiagents-push')

    assert checker.scan_text(text) == [(2, "")]


def test_a_commented_out_assignment_does_not_launder_the_live_one() -> None:
    """A comment binds nothing, so it cannot make a bad recipe read as clean.

    Reading the commented line as the later binding let anyone park a
    canonical-looking value in a comment above the `flock` and pass the gate
    while `/tmp/bad.lock` stayed live. The accidental version is the
    half-finished edit that comments a line out and leaves it there.
    """
    text = _fence(
        "LOCK=/tmp/bad.lock",
        '# LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock"',
        'flock "$LOCK" git push',
    )

    assert checker.scan_text(text) == [(2, "/tmp/bad.lock")]


def test_a_hash_inside_quotes_is_not_treated_as_a_comment() -> None:
    """The stripper is quote-aware, so a `#` in a path stays part of the value."""
    text = _fence('LOCK="/tmp/bad#1.lock"', 'flock "$LOCK" git push')

    assert checker.scan_text(text) == [(2, "/tmp/bad#1.lock")]


# ---------------------------------------------------------------------------
# One line, several statements. Each shape below defeated a different raw-line
# regex before the statement tokenizer replaced them.
# ---------------------------------------------------------------------------


def test_a_terminator_attached_to_the_argument_still_resolves() -> None:
    """No space before the `;`, so the raw token was `$LOCK";` and never matched."""
    text = _fence("LOCK=/tmp/bad.lock", 'flock "$LOCK"; git push')

    assert checker.scan_text(text) == [(2, "/tmp/bad.lock")]


def test_a_same_line_rebind_after_the_flock_is_not_read_as_its_lock() -> None:
    """The raw `.lock` scan used to contradict the resolver from the same line.

    The `flock` opens the canonical path. The trailing rebind is a different
    statement that no `flock` reads, so it is not a lock this recipe opens.
    """
    text = _fence(
        'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock" ; '
        'flock "$LOCK" git push ; LOCK=/tmp/bad.lock'
    )

    assert checker.scan_text(text) == []


def test_every_flock_on_one_line_is_inspected_not_only_the_first() -> None:
    """Two calls, one line. The second opens the rogue path and was never read."""
    text = _fence(
        'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock" ; '
        'flock "$LOCK" git push ; LOCK=/tmp/rogue ; flock "$LOCK" git push'
    )

    assert [path for _line, path in checker.scan_text(text)] == ["/tmp/rogue"]


def test_a_separator_inside_quotes_does_not_split_a_statement() -> None:
    """The tokenizer is quote-aware, so a `;` in a path stays in its value."""
    text = _fence('LOCK="/tmp/a;b.lock"', 'flock "$LOCK" git push')

    assert checker.scan_text(text) == [(2, "/tmp/a;b.lock")]


def test_an_unresolvable_variable_beside_a_canonical_lock_in_one_fence() -> None:
    """A non-empty target list used to swallow the second call entirely.

    `_scan_block`'s no-targets fallback fires only when the block names nothing
    at all, so the canonical lock on line 2 hid the unreadable one on line 3.
    This is the coexistence shape issue #4366 recorded, for the variable form.
    """
    text = _fence(
        'flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push',
        'flock "$OTHER" git push',
    )

    assert checker.scan_text(text) == [(3, "")]


def test_a_lock_path_outside_the_canonical_directory_is_rejected() -> None:
    findings = checker.scan_text('flock "$HOME/locks/push-lock-x.lock" git push')

    assert len(findings) == 1


def test_a_line_without_flock_is_not_scanned() -> None:
    assert checker.scan_text("the old global lock lived at /tmp/aiagents-push.lock") == []


def test_a_fenced_block_marked_historical_is_skipped() -> None:
    text = "\n".join(
        [
            "```bash",
            "# push-lock-historical: the superseded scheme",
            "flock /tmp/aiagents-push.lock git push origin main",
            "```",
        ]
    )

    assert checker.scan_text(text) == []


def test_the_historical_marker_does_not_leak_past_its_block() -> None:
    text = "\n".join(
        [
            "```bash",
            "# push-lock-historical",
            "flock /tmp/aiagents-push.lock git push",
            "```",
            "",
            "```bash",
            "flock /tmp/push-lock-other.lock git push",
            "```",
        ]
    )

    findings = checker.scan_text(text)

    assert [path for _line, path in findings] == ["/tmp/push-lock-other.lock"]


def test_line_numbers_point_at_the_offending_line() -> None:
    text = "\n".join(["intro", "more prose", "flock /tmp/bad.lock git push"])

    assert checker.scan_text(text)[0][0] == 3


def test_main_exits_1_and_names_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, {"docs/push.md": "flock /tmp/push-lock-a.lock git push\n"})

    assert checker.main(["--repo-root", str(repo)]) == 1

    captured = capsys.readouterr()
    assert "docs/push.md:1" in captured.err
    assert "1 violation(s) in 1 tracked Markdown file(s)" in captured.out


def test_main_exits_0_and_reports_the_examined_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, {"docs/push.md": CANONICAL_LINE + "\n"})

    assert checker.main(["--repo-root", str(repo)]) == 0
    assert "0 violation(s) in 1 tracked Markdown file(s)" in capsys.readouterr().out


def test_retrospectives_are_out_of_scope(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(
        repo,
        {".agents/retrospective/old.md": "flock /tmp/aiagents-push.lock git push\n"},
    )

    assert checker.main(["--repo-root", str(repo)]) == 0


def test_main_exits_2_outside_a_git_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert checker.main(["--repo-root", str(tmp_path)]) == 2
    assert "ERROR" in capsys.readouterr().err


def test_pre_pr_runs_the_push_lock_check() -> None:
    """Wiring: drive the real sequence, do not grep its source.

    A substring assertion over ``pre_pr_sequence.py`` passes when the call has
    become unreachable, when it sits inside a dead branch, and when the name
    survives only in a comment (testing MUST 9). Driving
    ``run_all_validations`` with a recording callback fails the moment the
    consumer stops reaching the gate. Mirrors
    ``tests/validation/test_pre_pr_model_pin_wiring.py``.
    """
    validation_dir = Path(__file__).resolve().parents[2] / "scripts" / "validation"
    if str(validation_dir) not in sys.path:
        sys.path.insert(0, str(validation_dir))
    import pre_pr_sequence  # bare-name import, see #2223

    recorded: list[str] = []

    def fake_run_validation(
        name: str, _state: object, _callback: object, skip: bool = False
    ) -> bool:
        recorded.append(name)
        return True

    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    args = SimpleNamespace(quick=True, skip_tests=False, verbose=False)
    pre_pr_sequence.run_all_validations(
        Path(__file__).resolve().parents[2], args, state, fake_run_validation
    )

    assert "Push Lock Path Agreement" in recorded


def test_pre_pr_push_lock_gate_calls_the_real_validator() -> None:
    """The recorded step must invoke this module, not merely carry its name."""
    validation_dir = Path(__file__).resolve().parents[2] / "scripts" / "validation"
    if str(validation_dir) not in sys.path:
        sys.path.insert(0, str(validation_dir))
    import pre_pr_sequence  # bare-name import, see #2223

    callbacks: dict[str, Callable[[], bool]] = {}

    def capture(
        name: str,
        _state: object,
        callback: Callable[[], bool],
        skip: bool = False,
    ) -> bool:
        callbacks[name] = callback
        return True

    state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
    args = SimpleNamespace(quick=True, skip_tests=False, verbose=False)
    repo_root = Path(__file__).resolve().parents[2]
    pre_pr_sequence.run_all_validations(repo_root, args, state, capture)

    seen: list[Path] = []
    original = checker.validate_push_lock_paths

    def fake_validate_push_lock_paths(root: Path) -> bool:
        seen.append(root)
        return True

    pre_pr_sequence.validate_push_lock_paths = fake_validate_push_lock_paths
    try:
        callbacks["Push Lock Path Agreement"]()
    finally:
        pre_pr_sequence.validate_push_lock_paths = original

    assert seen == [repo_root]


# ---------------------------------------------------------------------------
# The four ways a recipe reaches its lock path (issue #4366 refutation)
# ---------------------------------------------------------------------------


def test_a_lock_path_held_in_a_variable_is_caught() -> None:
    text = _fence('LOCK="/tmp/push-lock-$SLUG.lock"', 'flock "$LOCK" git push')

    assert checker.scan_text(text) == [(2, "/tmp/push-lock-$SLUG.lock")]


def test_the_file_descriptor_form_is_caught() -> None:
    text = _fence("exec 9>/tmp/aiagents-push.lock", "flock -n 9", "git push")

    assert checker.scan_text(text) == [(2, "/tmp/aiagents-push.lock")]


def test_a_path_on_a_continuation_line_is_caught() -> None:
    text = _fence("flock \\", "  /tmp/push-lock.lock \\", "  git push")

    assert checker.scan_text(text) == [(3, "/tmp/push-lock.lock")]


def test_an_extensionless_lock_is_named_not_merely_flagged() -> None:
    """No `.lock` token exists, so the `flock` argument is the lock target.

    This used to report `(2, "")`, meaning "this block names no canonical
    path". Reading the argument names the offender, and it is what lets the
    coexistence cases below be seen at all.
    """
    text = _fence("flock /tmp/aiagents-push git push")

    assert checker.scan_text(text) == [(2, "/tmp/aiagents-push")]


def test_a_second_scheme_sharing_a_fence_with_the_canonical_one_is_caught() -> None:
    """Issue #4366's evidence shape: the canonical recipe next to a dead one."""
    text = _fence(
        'flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push',
        "flock /tmp/aiagents-push git push origin br",
    )

    assert checker.scan_text(text) == [(3, "/tmp/aiagents-push")]


def test_a_second_scheme_reached_by_file_descriptor_is_caught() -> None:
    text = _fence(
        'flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push',
        "exec 9>/tmp/aiagents-push",
        "flock -n 9",
    )

    assert checker.scan_text(text) == [(3, "/tmp/aiagents-push")]


def test_a_second_scheme_reached_by_variable_is_caught() -> None:
    text = _fence(
        'flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push',
        "LOCK=/tmp/aiagents-push",
        'flock "$LOCK" git push',
    )

    assert checker.scan_text(text) == [(3, "/tmp/aiagents-push")]


def test_an_option_value_is_not_mistaken_for_the_lock_path() -> None:
    text = _fence('flock -w 5 "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push')

    assert checker.scan_text(text) == []


def test_the_canonical_recipe_across_two_lines_is_accepted() -> None:
    text = _fence(
        'LOCK="$HOME/src/scratch/locks/push-lock-$SLUG.lock"',
        'mkdir -p "$(dirname "$LOCK")"',
        'flock "$LOCK" git push origin "$BR"',
    )

    assert checker.scan_text(text) == []


def test_a_fence_without_flock_is_left_alone() -> None:
    """A lock path in unrelated prose is not a push-lock prescription."""
    text = _fence("cat /var/lib/apt/lists/lock.lock")

    assert checker.scan_text(text) == []


def test_a_historical_fence_is_still_skipped_under_the_block_scan() -> None:
    text = _fence(
        "# push-lock-historical: the census scheme, evidence not a recipe",
        "flock /tmp/aiagents-push.lock git push",
    )

    assert checker.scan_text(text) == []


def test_prose_naming_flock_without_a_path_is_not_a_violation() -> None:
    text = "`flock` excludes only processes that open the same path.\n"

    assert checker.scan_text(text) == []


def test_a_staged_but_uncommitted_file_is_examined(tmp_path: Path) -> None:
    """The inventory reads the index, so a new staged file cannot slip through.

    Reading it from ``HEAD`` made a staged Markdown file invisible to the gate,
    which is the whole window a pre-commit check exists to close.
    """
    repo = tmp_path / "repo"
    _init_repo(repo, {"docs/push.md": CANONICAL_LINE + "\n"})
    new_file = repo / "docs" / "rogue.md"
    new_file.write_text("flock /tmp/push-lock-rogue.lock git push\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/rogue.md"], cwd=repo, check=True)

    assert "docs/rogue.md" in checker.tracked_markdown(repo)
    assert checker.validate_push_lock_paths(repo) is False


def test_validate_entry_point_returns_false_on_a_violation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, {"docs/push.md": "flock /tmp/push-lock-a.lock git push\n"})

    assert checker.validate_push_lock_paths(repo) is False


def test_validate_entry_point_returns_true_on_a_clean_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, {"docs/push.md": CANONICAL_LINE + "\n"})

    assert checker.validate_push_lock_paths(repo) is True


def test_the_shipped_corpus_has_no_violation() -> None:
    """The gate must be green against the whole tree before it can block a push."""
    repo_root = Path(__file__).resolve().parents[2]

    violations, examined = checker.check_paths(repo_root, checker.tracked_markdown(repo_root))

    assert violations == []
    assert examined > 0
