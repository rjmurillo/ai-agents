"""The collection contract, as stated to humans, kept in step across surfaces.

Split out of `test_pytest_import_selection.py`, which crossed the 500-line
taste threshold when these arrived. The seam is real rather than convenient:
that module tests what the selector and the stand-in *do*, and this one tests
what the repository *says* they do, in the three places it says it. The two
fail for different reasons and are read by different people. A reader chasing
why a push collected instead of executing wants the sibling module; a reader
who changed the set of probed defect classes wants this one.

Nothing here executes pytest. The claims these surfaces make are proved by
behavior tests in the sibling module (`test_a_broken_import_...` and
`test_the_other_probed_catch_also_blocks_the_push`), because three
surfaces agreeing is a different property from any of them being true.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import git_hook_policy


def test_the_notice_states_every_probed_miss_not_just_the_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The developer-facing text must not under-list what collection misses.

    `_pytest_collection_command`'s docstring says the same two-catch,
    three-miss claim is printed here, and that a wrong one tells developers
    they are covered when they are not. Nothing checked that, and it drifted: the
    notice named the missing fixture and omitted two same-named test functions
    in one module, so it under-listed the misses in the direction that reads as
    more coverage than exists. Found by the PR's spec validator, which compared
    the code, the ADR, and this string and noticed one disagreed.

    Under-listing is the failure worth pinning. Over-listing a miss costs a
    developer an unnecessary CI round trip; omitting one costs a defect that
    reaches CI believing it was gated locally.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    git_hook_policy._resolve_pytest_commands(tmp_path, None)
    # Whitespace-normalized: the notice hard-wraps, so a phrase can straddle a
    # newline and a plain substring check would pass or fail on wrap position.
    err = " ".join(capsys.readouterr().err.split())

    # Phrased as "blocks on X", so it fails if a catch is demoted to a miss
    # without the wording moving with it. An earlier revision looped a variable
    # named `catches` over a bare class name and asserted only that the string
    # appeared somewhere, which stopped discriminating the moment the
    # same-basename collision moved into the misses: "does NOT catch a
    # same-basename module collision" satisfies a bare substring check for
    # "same-basename module collision" perfectly well. A check that passes
    # whichever side of the contract a class lands on is not checking the
    # contract. Caught by the spec validator on PR #5319.
    for catch in ("blocks on a broken import", "on a syntax error"):
        assert catch in err, (
            f"notice no longer claims to catch {catch!r}. Both were probed "
            "under production configuration and exit 2; see "
            "_pytest_collection_command's docstring and ADR-104 rule 5."
        )

    for miss in (
        "does NOT catch a missing fixture",
        "does NOT catch two same-named test functions in one module",
        "does NOT catch a same-basename module collision",
    ):
        assert miss in err, (
            f"notice omits {miss!r}. All three were probed and collect clean "
            "with exit 0 under this repository's --import-mode=importlib; see "
            "_pytest_collection_command's docstring and ADR-104 rule 5. A "
            "notice that lists fewer misses than were probed tells the reader "
            "they are covered when they are not."
        )


# The collection contract, as concepts rather than sentences. Each entry is the
# set of spellings that count as stating that class, because the three surfaces
# below word it differently on purpose: a docstring explains, a notice is read
# under time pressure by someone whose push just went a different way than they
# expected, and an ADR rule is cited by number. Pinning one exact sentence
# across all three would force the worst wording of the three onto the other two.
#
# What must not drift is the SET. A surface that stops naming a class is the
# defect: the notice already did exactly that, listing one miss where the
# docstring beside it listed two, and nothing caught it (see the notice test
# above). The issue body is deliberately absent from this check, because it
# lives on GitHub and no repository test can read it; it is kept in step by
# hand, and that is a weaker guarantee stated as one rather than implied.
COLLECTION_CATCHES = {
    "a broken import": ("broken import",),
    "a syntax error": ("syntax error",),
}

# Misses carry their negation. An earlier revision listed the bare class name,
# which a surface satisfies whether it says the class is caught or missed, so
# the check could not detect a polarity inversion: exactly the failure that put
# the basename collision in CATCHES for three commits. The deletion control
# cannot find that either, because inverting a claim deletes nothing.
COLLECTION_MISSES = {
    "a missing fixture": (
        "does not catch a missing fixture",
        "does not catch a test whose fixture no fixture satisfies",
    ),
    "two same-named test functions in one module": (
        "does not catch two same-named test functions in one module",
    ),
    # Moved here from CATCHES in review (PR #5319). A basename collision raises
    # under pytest's default `prepend` import mode and collects clean under
    # `--import-mode=importlib`, which `pyproject.toml` sets. The probe behind
    # the old claim ran without that config. This table agreeing with three
    # surfaces never made the claim true: agreement and truth are different
    # properties, which is why the behavior tests live next door.
    "a same-basename module collision": (
        "does not catch a same-basename module collision",
        "does not catch two test modules sharing a basename",
    ),
}

_ADR_104 = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "architecture"
    / "ADR-104-gate-tier-placement-and-budgets.md"
)


def _surface_not_stating(spellings: tuple[str, ...], surfaces: dict[str, str]) -> str | None:
    """Name the first surface stating none of `spellings`, or None if all do."""
    for surface, text in surfaces.items():
        if not any(s in text for s in spellings):
            return surface
    return None


def _collection_contract_surfaces(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> dict[str, str]:
    """The three in-repo places the contract is stated, normalized for matching.

    Lowercased as well as whitespace-collapsed. The notice shouts `does NOT
    catch` and the ADR writes `does not catch`; both are the same claim, and a
    spelling table that has to carry each surface's capitalization stops being
    about the contract and starts being about typography.
    """
    git_hook_policy._resolve_pytest_commands(tmp_path, None)

    def normalize(text: str) -> str:
        return " ".join(text.split()).lower()

    return {
        "the _pytest_collection_command docstring": normalize(
            git_hook_policy._pytest_collection_command.__doc__ or ""
        ),
        "the notice printed to the developer": normalize(capsys.readouterr().err),
        "ADR-104 rule 5": normalize(_ADR_104.read_text(encoding="utf-8")),
    }


@pytest.mark.parametrize(
    ("label", "spellings"),
    [*COLLECTION_CATCHES.items(), *COLLECTION_MISSES.items()],
)
def test_every_in_repo_surface_states_the_whole_collection_contract(
    label: str,
    spellings: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Code, notice, and ADR must all name every probed class.

    ADR-104 rule 5 says to state only the classes you probed. Three in-repo
    surfaces state them, and a spec-validation pass observed that nothing kept
    them in step: the guard that existed covered the notice alone, so the ADR
    could drop a class, or gain one nobody probed, without any test noticing.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)

    absent = _surface_not_stating(spellings, _collection_contract_surfaces(capsys, tmp_path))
    assert absent is None, (
        f"{absent} does not state {label!r} (accepted spellings: {spellings}). "
        "All three must name the same set of probed classes. If a class was "
        "added or removed, probe it and update every surface plus this table; "
        "if only the wording changed, add the new spelling here."
    )


@pytest.mark.parametrize(("label", "terms"), sorted(COLLECTION_CATCHES.items()))
def test_no_surface_disclaims_a_class_it_is_supposed_to_catch(
    label: str,
    terms: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The inversion the presence check cannot see.

    The check above asks whether each class is named. Naming is not polarity: a
    surface that said "does not catch a broken import" would satisfy a search
    for "broken import" and quietly halve the local gate's advertised value.
    The misses carry their negation in the spelling table, so this is the
    matching guard for the other column.

    Raised in review on PR #5319 alongside the polarity hole in the misses.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)

    for surface, text in _collection_contract_surfaces(capsys, tmp_path).items():
        for term in terms:
            assert f"does not catch {term}" not in text, (
                f"{surface} says it does not catch {term!r}, but {label!r} is "
                "in COLLECTION_CATCHES. Either the surface is wrong, or the "
                "class was demoted and the table was not moved with it. Probe "
                "it under production configuration before deciding which."
            )


def test_the_contract_check_can_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Negative control: strike a class from one surface and the check names it.

    An earlier version of this control asserted only that an invented sentinel
    was absent from every surface, which is true of any string nobody wrote and
    proves nothing about whether the check above discriminates. It was written
    after verifying discrimination by hand, and it did not encode what the hand
    check did, so the committed test was weaker than the work behind it. A
    spec-validation pass said so. That is the same vacuous-control defect this
    branch already found once in the filter-root test, which is why the fix is
    a real mutation rather than a better-worded assertion.

    Mutating the string rather than the file on disk: the surfaces are read
    into a dict, so doctoring the dict exercises the same predicate the real
    check uses without a test that edits a tracked ADR and has to put it back.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)

    surfaces = _collection_contract_surfaces(capsys, tmp_path)
    assert len(surfaces) == 3, f"expected three surfaces, got {sorted(surfaces)}"

    spellings = COLLECTION_MISSES["two same-named test functions in one module"]
    assert _surface_not_stating(spellings, surfaces) is None, (
        "precondition failed: some surface already omits this class, so the "
        "mutation below would not be what makes the check fire."
    )

    for target, text in surfaces.items():
        struck = dict(surfaces)
        struck[target] = text
        for spelling in spellings:
            struck[target] = struck[target].replace(spelling, "")
        assert _surface_not_stating(spellings, struck) == target, (
            f"striking {spellings} from {target} did not make the check report "
            f"{target}. The check does not discriminate, so every row of the "
            "parametrized test above passes for a reason other than the "
            "surfaces actually stating the contract."
        )
