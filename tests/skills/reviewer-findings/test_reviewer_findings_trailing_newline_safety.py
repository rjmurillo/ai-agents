"""Trailing-newline command-substitution safety tests (PR #5178, ninth review round).

Split into its own file rather than appended to
``test_reviewer_findings_premise_verification.py``, which sat at 449 of the
repository's 500-line file-size ceiling
(``scripts/ci/taste_count_ratchet.py``) before this file existed; adding
these tests there would have pushed it over. Shares the ``plugin_root``
fixture (``conftest.py``) and the parsing/lookup helpers (``_helpers.py``)
with the sibling test files in this directory.

Covers a distinct correctness gap from the CWE-78/CWE-20 git-invocation
tests in the sibling files: plain command substitution (``$(cat <file>)``)
strips every trailing newline the file has, so loading either the needle or
the cited path this way silently changes the value being compared, rather
than merely risking shell reinterpretation or git pathspec-magic
reinterpretation of the value's *content*. Verified empirically before
these tests were written: on a file ending in two newlines, ``X=$(cat f)``
in bash returns a value with both trailing newlines stripped, while
``X=$(cat f; printf x); X=${X%x}`` (append a non-newline sentinel, then
strip it back off with parameter expansion) round-trips the file's bytes
exactly.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# pytest here runs under --import-mode=importlib (pyproject.toml), which never
# inserts a test file's own directory onto sys.path, so a plain
# `import _helpers` cannot resolve. Load the sibling module by file path,
# matching every other file in this directory.
_HELPERS_PATH = Path(__file__).resolve().parent / "_helpers.py"
_helpers_spec = importlib.util.spec_from_file_location(
    "reviewer_findings_test_helpers", _HELPERS_PATH
)
assert _helpers_spec is not None and _helpers_spec.loader is not None
_helpers = importlib.util.module_from_spec(_helpers_spec)
_helpers_spec.loader.exec_module(_helpers)

ROUTER_SKILL = _helpers.ROUTER_SKILL
SKILL_NAME = _helpers.SKILL_NAME
_read = _helpers._read
_read_reference = _helpers._read_reference

# The prescribed recipe, once markdown's ~72-column prose wrap is collapsed.
# Matching this way (rather than a per-line substring, as the sibling files
# use for shorter tokens) is required here: the real text wraps
# "NEEDLE=$(cat <needle-file>;" and "printf x); NEEDLE=${NEEDLE%x}" onto two
# separate lines, so a same-line substring check would never match the real
# recipe and the test would either false-fail on the fix or (worse) pass
# without ever having looked at the sentinel bytes.
_NEEDLE_SENTINEL_RECIPE = "NEEDLE=$(cat <needle-file>; printf x); NEEDLE=${NEEDLE%x}"
_PATH_SENTINEL_RECIPE = "PATH_SPEC=$(cat <path-file>; printf x); PATH_SPEC=${PATH_SPEC%x}"


def _collapsed(text: str) -> str:
    """Collapse markdown prose wrapping to one space per whitespace run.

    A recipe split across a hard-wrapped line pair reads identically to the
    same recipe on one line once whitespace is normalized; the SKILL.md and
    workflow.md prose wraps at different columns, but both files feed
    through the same collapse before comparison.
    """
    return " ".join(text.split())


def _has_sentinel_recipe(text: str, recipe: str) -> bool:
    """Return whether ``recipe`` appears in ``text`` after wrap-collapsing.

    The single contract check shared by every positive assertion in this
    file and by the negative control below (Copilot on PR #5178: an
    earlier draft had the negative control reimplement this membership
    test inline instead of calling the same predicate the positive tests
    use, so a future change to how positive assertions match could drift
    from what the negative control still checks, silently weakening the
    guard without either test failing to signal it).
    """
    return recipe in _collapsed(text)


class TestTrailingNewlineCommandSubstitutionSafety:
    def test_reviewer_findings_needle_load_survives_a_trailing_newline(
        self, plugin_root: Path
    ) -> None:
        """Positive: bare `$(cat <needle-file>)` silently drops trailing
        newlines from the needle (this session, PR #5178 ninth review
        round).

        Verified empirically: `X=$(cat f)` on a file ending in `\\n\\n`
        returns a string with both trailing newlines stripped, while
        `X=$(cat f; printf x); X=${X%x}` (append a non-newline sentinel,
        then strip it back off with parameter expansion) round-trips the
        file's bytes exactly. A quoted finding whose last line is blank
        would otherwise be compared as a shorter string than what the
        finding actually quoted, understating a match that should have
        confirmed the premise.
        """
        text = _read(plugin_root, SKILL_NAME)
        assert _has_sentinel_recipe(text, _NEEDLE_SENTINEL_RECIPE), (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer prescribes "
            f"the sentinel round-trip ({_NEEDLE_SENTINEL_RECIPE!r}) for "
            f"loading the needle file; a plain $(cat <needle-file>) "
            f"silently drops trailing newlines from the needle"
        )

    def test_reviewer_findings_path_load_survives_a_trailing_newline(
        self, plugin_root: Path
    ) -> None:
        """Positive: bare `$(cat <path-file>)` silently truncates a path
        ending in a newline to a different, possibly pre-existing path
        (CWE-20; this session, PR #5178 ninth review round).

        Verified empirically with the same reproduction as the needle case
        above, applied to a path file instead of a needle file. Checked at
        every place the skill names the path-loading recipe (the Process
        step and MUST 5 both carry their own copy).
        """
        text = _collapsed(_read(plugin_root, SKILL_NAME))
        occurrences = text.count(_PATH_SENTINEL_RECIPE)
        assert occurrences >= 2, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} prescribes the path "
            f"sentinel round-trip ({_PATH_SENTINEL_RECIPE!r}) only "
            f"{occurrences} time(s); expected at least 2 (the Process step "
            f"and MUST 5 each name the recipe independently, and a "
            f"regression to a bare $(cat <path-file>) in either would "
            f"silently truncate a path ending in a newline to a different, "
            f"possibly pre-existing path)"
        )

    def test_responder_workflow_path_load_survives_a_trailing_newline(
        self, plugin_root: Path
    ) -> None:
        """Positive: the pr-comment-responder workflow reference must carry
        the same sentinel fix, not just reviewer-findings/SKILL.md itself.

        Parametrized over both plugin roots (via the shared ``plugin_root``
        fixture), matching every other reference-file check in this
        directory: the copilot-cli mirror is a separately generated file,
        not merely a passthrough copy, so it needs its own check.
        """
        text = _read_reference(plugin_root, ROUTER_SKILL, "workflow.md")
        assert _has_sentinel_recipe(text, _PATH_SENTINEL_RECIPE), (
            f"{ROUTER_SKILL}/references/workflow.md in {plugin_root} no "
            f"longer prescribes the sentinel round-trip "
            f"({_PATH_SENTINEL_RECIPE!r}) for loading the path file; a "
            f"plain $(cat <path-file>) silently truncates a path ending in "
            f"a newline to a different, possibly pre-existing path (CWE-20)"
        )

    def test_a_bare_cat_load_is_what_the_sentinel_guard_would_catch(self) -> None:
        """Negative control: the exact same ``_has_sentinel_recipe`` predicate
        the positive tests call must flag the pre-fix, lossy recipe rather
        than pass on any `$(cat ...)` mention.

        Calling the shared predicate here, instead of a second, independent
        substring check, is the point (Copilot on PR #5178: an earlier draft
        reimplemented the membership test inline, so a future change to how
        the positive tests match could drift from what this control still
        checks without either test failing to signal it). This also guards
        against the check degenerating into "the text mentions $(cat"
        (trivially true even in the un-fixed form, since the fix prose
        itself names the bad pattern as a warning) by requiring the *exact*
        sentinel recipe, not merely a substring of it.
        """
        unfixed_needle = "load the needle with `NEEDLE=$(cat <needle-file>)` and reference it"
        unfixed_path = "load the path with `PATH_SPEC=$(cat <path-file>)` and reference it"
        assert not _has_sentinel_recipe(unfixed_needle, _NEEDLE_SENTINEL_RECIPE), (
            "the sentinel guard did not distinguish the lossy bare $(cat "
            "<needle-file>) recipe from the fixed sentinel form, so it "
            "would not catch a real regression back to the lossy form"
        )
        assert not _has_sentinel_recipe(unfixed_path, _PATH_SENTINEL_RECIPE), (
            "the sentinel guard did not distinguish the lossy bare $(cat "
            "<path-file>) recipe from the fixed sentinel form, so it would "
            "not catch a real regression back to the lossy form"
        )
