"""One line, several shell statements (issues #4635, #4366).

The gate used to read a raw line with a separate regex per purpose, so its
readers disagreed about what the line held: only the first ``flock`` was
parsed, a ``.lock`` literal was taken from a statement no ``flock`` ran, and
an argument with the next statement's terminator stuck to it stopped looking
like a variable. Every test here pins one of those shapes against the single
statement tokenizer that replaced them, plus the quoting and comment
boundaries that tokenizer has to respect.
"""

from __future__ import annotations

from scripts.validation import check_push_lock_paths as checker
from tests.validation._push_lock_fixtures import _fence


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
