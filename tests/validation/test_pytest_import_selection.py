"""Import-graph test selection wired into the pre-push pytest runner."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.test_selection.select_tests import Selection
from scripts.validation import git_hook_policy


def _has_parallel_flag(command: list[str]) -> bool:
    return "-n" in command


def test_subset_splits_serial_and_parallel_partitions(tmp_path: Path) -> None:
    commands = git_hook_policy._pytest_commands_for_subset(
        tmp_path,
        [
            "tests/test_leaf.py",
            "tests/mutation/test_thing.py",
            "tests/test_safe_push_pr_branch.py",
            "tests/test_pr_autofix_late_live_state_gate.py",
        ],
    )
    assert len(commands) == 4
    bulk, mutation, safe_push, pr_autofix = commands
    assert _has_parallel_flag(bulk)
    assert _has_parallel_flag(mutation)
    assert not _has_parallel_flag(safe_push)
    assert not _has_parallel_flag(pr_autofix)
    assert str(tmp_path / "tests/test_leaf.py") in bulk
    assert "not integration and not safe_push_transport" in safe_push


def test_subset_emits_only_needed_partitions(tmp_path: Path) -> None:
    commands = git_hook_policy._pytest_commands_for_subset(tmp_path, ["tests/test_leaf.py"])
    assert len(commands) == 1
    assert str(tmp_path / "tests/test_leaf.py") in commands[0]


def _collection(tmp_path: Path) -> list[list[str]]:
    return [git_hook_policy._pytest_collection_command(tmp_path)]


def test_resolve_collects_when_diff_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, None)
    assert commands == _collection(tmp_path)


def test_resolve_collects_on_full_verdict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    assert commands == _collection(tmp_path)


def test_collection_command_runs_no_test_bodies(tmp_path: Path) -> None:
    command = git_hook_policy._pytest_collection_command(tmp_path)
    assert "--collect-only" in command
    assert "not integration" in command
    assert str(tmp_path / "tests") in command
    # A parallel flag would start workers for a run that never executes a test.
    assert not _has_parallel_flag(command)


def test_opt_in_env_restores_local_full_suite_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The escape hatch has to actually reach the executing partitions.

    Without this, the default could quietly become the only behavior and the
    documented override in `lefthook.yml` and ADR-104 would be a dead string.
    """
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "1")
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    assert commands == git_hook_policy._pytest_commands(tmp_path)


@pytest.mark.parametrize("value", ["0", "true", "TRUE", "yes", " 1 x"])
def test_opt_in_env_rejects_values_other_than_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    """Doing less than the caller asked for, silently, is the failure here.

    A developer who exports `...=true` wants local execution. Quietly
    collecting instead gives them a fast green push and no signal that the
    flag did nothing.
    """
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, value)
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    with pytest.raises(ValueError, match="must be '1' or unset"):
        git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])


@pytest.mark.parametrize("value", ["", "   ", "1", " 1 "])
def test_opt_in_env_accepts_unset_blank_and_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    """Blank is unset by another name; a padded '1' is still a '1'."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, value)
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="non-Python change"),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    expected = (
        git_hook_policy._pytest_commands(tmp_path)
        if value.strip() == "1"
        else _collection(tmp_path)
    )
    assert commands == expected


def test_a_rejected_opt_in_value_exits_config_error_not_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`run_pytest` must turn the raise into a non-zero exit, not a pass."""
    monkeypatch.setenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, "true")
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    assert git_hook_policy.run_pytest(tmp_path) == 2


def test_run_pytest_refuses_an_empty_command_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A push must never pass by running zero tests.

    The invariant that keeps `commands` non-empty lives in `select_tests`, a
    different module. `run_pytest` decides whether a push is allowed, so it
    carries its own guard rather than trusting that one.
    """
    monkeypatch.setattr(git_hook_policy, "_resolve_pytest_commands", lambda *_a, **_k: [])
    assert git_hook_policy.run_pytest(tmp_path) == 2
    assert "zero tests" in capsys.readouterr().err


def test_collection_command_silences_the_node_listing(tmp_path: Path) -> None:
    """`pyproject.toml` sets `addopts = "-v ..."`, so one `-q` nets to zero.

    Measured: 31765 lines of node listing into the hook output with one `-q`,
    878 with three. Hook output is a token cost this stand-in exists to cut.
    """
    command = git_hook_policy._pytest_collection_command(tmp_path)
    assert command.count("-q") == 3


def test_collection_gets_the_collection_budget_not_the_suite_budget(tmp_path: Path) -> None:
    """A collection hang must not be able to block a push for 29 minutes."""
    collection = _collection(tmp_path)
    assert (
        git_hook_policy._pytest_budget_seconds(collection)
        == git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS
    )
    assert (
        git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS < git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_executing_commands_keep_the_suite_budget(tmp_path: Path) -> None:
    executing = git_hook_policy._pytest_commands(tmp_path)
    assert (
        git_hook_policy._pytest_budget_seconds(executing)
        == git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_subset_of_one_file_is_not_mistaken_for_a_collection_run(tmp_path: Path) -> None:
    """The budget switch keys on `--collect-only`, not on the command count."""
    subset = git_hook_policy._pytest_commands_for_subset(tmp_path, ["tests/test_leaf.py"])
    assert len(subset) == 1
    assert (
        git_hook_policy._pytest_budget_seconds(subset) == git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS
    )


def test_resolve_uses_subset_on_narrowed_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(
            full=False, reason="import-graph subset", tests=("tests/test_leaf.py",)
        ),
    )
    commands = git_hook_policy._resolve_pytest_commands(tmp_path, ["pkg/leaf.py"])
    assert commands == git_hook_policy._pytest_commands_for_subset(
        tmp_path, ("tests/test_leaf.py",)
    )
    assert "import graph" in capsys.readouterr().err


def test_resolve_explains_why_it_collected_instead_of_executing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The narrowed path announced itself and the fallback stayed silent.

    That was fine while the fallback ran everything, because silence meant the
    strongest behavior. It now means the weaker one, so a reader who sees a
    fast pre-push has to be told the suite was collected rather than run, and
    where the execution went.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    git_hook_policy._resolve_pytest_commands(tmp_path, None)
    err = capsys.readouterr().err
    assert "Collecting every test" in err
    assert "pytest.yml" in err
    assert git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV in err


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
    """The stand-in claims three catches; only one of them was executed.

    `test_a_broken_import_...` above proves the first. The other two were
    probed by hand when the claim was written and the probes were never
    committed, so the repository held three claims and one proof. The contract
    test elsewhere in this module checks that the docstring, the notice, and
    ADR-104 rule 5 *agree* on the three, which is a different thing from any of
    them being true: three surfaces can agree and all be wrong. Raised by a
    spec-validation pass, which noticed the asymmetry between what is claimed
    and what runs.

    Exit codes differ by class (a syntax error exits 1, a collision exits 2), so
    these assert non-zero rather than a specific code. What matters to the push
    is that git refuses it, and lefthook treats any non-zero the same way.
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


def test_the_collection_notice_repeats_the_selector_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A selector regression and a legitimate non-Python change must read differently.

    Without the reason in the notice, a selector that silently started
    returning `full=True` for every diff would look identical to the ordinary
    Markdown case it is supposed to look different from.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(
        git_hook_policy.select_tests,
        "select",
        lambda *_a, **_k: Selection(full=True, reason="sentinel-reason-xyz"),
    )
    git_hook_policy._resolve_pytest_commands(tmp_path, ["README.md"])
    assert "sentinel-reason-xyz" in capsys.readouterr().err


def test_a_collection_timeout_names_the_collection_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A collection hang must name the collection ceiling, not the suite one.

    The timeout message is the only thing a developer whose push just died has
    to go on. Naming the wrong ceiling sends them hunting for a 29-minute run
    that never happened.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)
    monkeypatch.setattr(
        git_hook_policy,
        "_run_command",
        lambda *_a, **_k: subprocess.CompletedProcess(["pytest"], 3, "", ""),
    )
    monkeypatch.setattr(git_hook_policy, "_print_process_output", lambda _r: None)

    assert git_hook_policy.run_pytest(tmp_path) == 3

    err = capsys.readouterr().err
    assert str(git_hook_policy.TEST_COLLECTION_TIMEOUT_SECONDS) in err
    assert str(git_hook_policy.TEST_SUITE_TIMEOUT_SECONDS) not in err
