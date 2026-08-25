"""Import-graph test selection wired into the pre-push pytest runner."""

from __future__ import annotations

import subprocess
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


def test_the_notice_states_every_probed_miss_not_just_the_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The developer-facing text must not under-list what collection misses.

    `_pytest_collection_command`'s docstring says the same three-catch,
    two-miss claim is printed here, and that a wrong one tells developers they
    are covered when they are not. Nothing checked that, and it drifted: the
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

    for catches in ("broken\nimport", "syntax error", "same-basename module collision"):
        assert " ".join(catches.split()) in err, f"notice no longer claims to catch {catches!r}"

    for misses in ("does NOT catch a missing fixture", "same-named test functions in one module"):
        assert misses in err, (
            f"notice omits {misses!r}. Both misses were probed and collect "
            "clean with exit 0; see _pytest_collection_command's docstring and "
            "ADR-104 rule 5. A notice that lists fewer misses than were probed "
            "tells the reader they are covered when they are not."
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
    "a same-basename module collision": ("same-basename", "share a basename"),
}
COLLECTION_MISSES = {
    "a missing fixture": ("missing fixture", "fixture no fixture satisfies"),
    "two same-named test functions in one module": ("same-named test functions in one module",),
}

_ADR_104 = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "architecture"
    / "ADR-104-gate-tier-placement-and-budgets.md"
)


def _collection_contract_surfaces(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> dict[str, str]:
    """The three in-repo places the contract is stated, whitespace-normalized."""
    git_hook_policy._resolve_pytest_commands(tmp_path, None)
    return {
        "the _pytest_collection_command docstring": " ".join(
            (git_hook_policy._pytest_collection_command.__doc__ or "").split()
        ),
        "the notice printed to the developer": " ".join(capsys.readouterr().err.split()),
        "ADR-104 rule 5": " ".join(_ADR_104.read_text(encoding="utf-8").split()),
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

    for surface, text in _collection_contract_surfaces(capsys, tmp_path).items():
        assert any(s in text for s in spellings), (
            f"{surface} does not state {label!r} (accepted spellings: {spellings}). "
            "All three must name the same set of probed classes. If a class was "
            "added or removed, probe it and update every surface plus this table; "
            "if only the wording changed, add the new spelling here."
        )


def test_the_contract_check_can_fail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Negative control: a class no surface states must be reported missing.

    Without this the parametrized test above passes for every row and nobody
    can tell whether it discriminates or whether the substrings are simply so
    short that they match anything.
    """
    monkeypatch.delenv(git_hook_policy.PYTEST_FULL_SUITE_LOCALLY_ENV, raising=False)
    monkeypatch.setattr(git_hook_policy.select_tests, "changed_from_git", lambda *_: None)

    surfaces = _collection_contract_surfaces(capsys, tmp_path)
    assert surfaces, "no surfaces were collected, so the check above is vacuous"
    for surface, text in surfaces.items():
        assert "a deadlock in a conftest fixture" not in text, (
            f"{surface} states a class this control assumed nobody probed. "
            "Pick a different sentinel."
        )


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
