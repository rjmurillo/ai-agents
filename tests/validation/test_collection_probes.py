"""What pre-push collection actually does, executed against real trees.

Split out of `test_pytest_import_selection.py`, which crossed the 500-line
taste threshold when the last two probes arrived. The seam is the one the
contract module already draws: that module tests how the runner is wired, and
this one runs the real command against a tree built to carry one defect and
reads the exit code. They fail for different reasons. A wiring failure means
someone changed which commands get built; a failure here means pytest, or this
repository's `addopts`, changed what collection sees.

Every fixture copies `addopts` out of the real `pyproject.toml` rather than
naming flags by hand. That is not tidiness: the claim these probes correct was
produced by a probe in a config-less `tmp_path`, which silently ran pytest's
default `prepend` import mode instead of the `--import-mode=importlib` this
repository sets, and so measured a pytest that is never run here.

Coverage:

- positive: each probed catch blocks the push, and the repaired tree proceeds.
- negative: each probed miss collects clean, with a syntax error appended to
  the same tree as the control proving collection reached it at all.
- edge: the basename collision, which is a catch under `prepend` and a miss
  under `importlib`, is pinned as a miss and says so if `addopts` changes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy


def test_a_broken_import_makes_the_collection_stand_in_block_the_push(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The load-bearing claim of the whole stand-in, executed rather than argued.

    ADR-104 gives up local assertion results on the fallback path and keeps the
    push blocked on a broken import. Every other test here asserts on the argv
    list; this one runs the real command against a real tree and drives the
    result through `run_pytest`, because the claim is about an exit code and an
    argv assertion cannot reach one (testing.md MUST 8).

    Negative control is the second half: the same tree with the bad import
    removed collects clean and the push proceeds. Without it, a command that
    failed for any reason at all would satisfy the first half.
    """
    _mirror_production_pytest_config(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    broken = tests_dir / "test_broken.py"
    broken.write_text(
        "import definitely_not_a_real_module_xyz\n\n\ndef test_ok():\n    assert True\n",
        encoding="utf-8",
    )
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)

    assert git_hook_policy.run_pytest(tmp_path) != 0

    broken.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    assert git_hook_policy.run_pytest(tmp_path) == 0


def _break_with_a_syntax_error(tests_dir: Path) -> Callable[[], None]:
    """Write an unparseable test module; return the repair that makes it valid."""
    offender = tests_dir / "test_syntax.py"
    offender.write_text("def test_ok(:\n    assert True\n", encoding="utf-8")

    def repair() -> None:
        offender.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    return repair


_REPO_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _mirror_production_pytest_config(root: Path) -> None:
    """Give the fixture the addopts the real collection run gets.

    A bare `tmp_path` has no `pyproject.toml`, so pytest falls back to its
    default import mode. Production sets `--import-mode=importlib`, and the two
    modes disagree about whether two modules sharing a basename are a
    collection error: `prepend` raises, `importlib` does not. A fixture without
    this file measures a pytest this repository never runs, which is how a
    defect class that production does not catch came to be claimed as caught in
    four places and "proved" by a test that passed for the wrong reason.

    The addopts are copied out of the real `pyproject.toml` rather than
    restated, so the fixture cannot drift from production the way a
    hand-maintained duplicate would.
    """
    for line in _REPO_PYPROJECT.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("addopts"):
            root.joinpath("pyproject.toml").write_text(
                f"[tool.pytest.ini_options]\n{stripped}\n", encoding="utf-8"
            )
            return
    raise AssertionError(
        f"no addopts line in {_REPO_PYPROJECT}; the fixture can no longer "
        "mirror production and would silently test a different pytest."
    )


@pytest.mark.parametrize(
    ("label", "make_defect"),
    [("a syntax error", _break_with_a_syntax_error)],
)
def test_the_other_probed_catch_also_blocks_the_push(
    label: str,
    make_defect: Callable[[Path], Callable[[], None]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The stand-in's second catch, executed rather than argued.

    `test_a_broken_import_...` above proves the first. This proves the other
    one. There were briefly three: the same-basename collision was claimed and
    parametrized here, then removed when a probe under production
    configuration showed it collects clean, and it now has its own negative
    test below.

    Both halves of that history are worth keeping. The claims were held by
    three surfaces agreeing, which is a different property from any of them
    being true. And the first attempt to fix that by executing the real command
    still measured the wrong pytest, because the fixture had no config file and
    silently took a different import mode. Agreement is not truth, and
    execution is not fidelity.

    Asserts non-zero rather than a specific code: what matters is that git
    refuses the push, and lefthook treats any non-zero the same way.
    """
    _mirror_production_pytest_config(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    repair = make_defect(tests_dir)

    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)

    assert git_hook_policy.run_pytest(tmp_path) != 0, (
        f"collection did not block on {label}, which the docstring, the "
        "developer notice, and ADR-104 rule 5 all claim it catches. Either the "
        "claim is wrong in three places or the stand-in regressed."
    )

    repair()
    assert git_hook_policy.run_pytest(tmp_path) == 0, (
        f"the tree with {label} removed still fails, so the assertion above "
        "passes for some reason other than the defect it names."
    )


def test_a_same_basename_collision_goes_uncaught_under_production_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The claim this repository used to make, pinned as the miss it actually is.

    Two modules sharing a basename with no package IS a collection error under
    pytest's default `prepend` import mode, and is NOT one under
    `--import-mode=importlib`, which is what `pyproject.toml` sets. An earlier
    revision claimed this as a third catch in the docstring, the developer
    notice, ADR-104 rule 5, and the contract table, on the strength of a probe
    run in a config-less `tmp_path` that silently selected the other mode.
    Caught in review (PR #5319), not by any gate here.

    Pinned as a negative rather than deleted, because the reasoning that
    produced the wrong claim is easy to repeat: the collision is real, it is
    just invisible to the importer this repository chose. If someone drops
    `--import-mode=importlib` from addopts, this test fails and says to move
    the class back to the catches.
    """
    _mirror_production_pytest_config(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    for directory in ("a", "b"):
        sibling = tests_dir / directory
        sibling.mkdir()
        (sibling / "test_dup.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)

    assert git_hook_policy.run_pytest(tmp_path) == 0, (
        "a same-basename collision now blocks collection. If addopts no longer "
        "sets --import-mode=importlib, this class became a real catch: move it "
        "back into COLLECTION_CATCHES and every contract surface. If addopts is "
        "unchanged, something else regressed."
    )


@pytest.mark.parametrize(
    ("label", "module_source"),
    [
        (
            "a missing fixture",
            "def test_needs_a_fixture(no_conftest_defines_this):\n"
            "    assert no_conftest_defines_this\n",
        ),
        (
            "two same-named test functions in one module",
            "def test_same_name():\n    assert True\n\n\n"
            "def test_same_name():\n    assert False\n",
        ),
    ],
)
def test_a_claimed_miss_really_does_collect_clean(
    label: str, module_source: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other two misses, executed rather than asserted about as strings.

    Three surfaces and a contract table say collection does not catch these.
    Nothing ran them. Review on PR #5319 pointed out that the whole set of
    claims was held up by string comparisons between surfaces that agree with
    each other, which is the same shape as the basename collision that was
    published as a catch for three commits and was never true here.

    The control is the second half: the same tree with a syntax error appended
    must block. Without it, a zero exit could mean the fixture never reached
    collection at all, and the test would pass for a tree pytest declined to
    look at.
    """
    _mirror_production_pytest_config(tmp_path)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    case = tests_dir / "test_case.py"
    case.write_text(module_source, encoding="utf-8")

    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)

    assert git_hook_policy.run_pytest(tmp_path) == 0, (
        f"collection now blocks on {label!r}. It is listed as a miss in "
        "_pytest_collection_command's docstring, in the developer notice, and "
        "in ADR-104 rule 5. If pytest or this repository's addopts changed so "
        "that collection catches it, move the class into COLLECTION_CATCHES "
        "and update every surface."
    )

    case.write_text(module_source + "\ndef broken(:\n", encoding="utf-8")
    assert git_hook_policy.run_pytest(tmp_path) != 0, (
        "the control failed: a syntax error in the same tree did not block the "
        f"push, so the clean exit above is not evidence about {label!r}. "
        "Collection is not reaching this fixture at all."
    )
