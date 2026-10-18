"""Base-ref ceiling for the NL structural debt ratchet (issue #6506).

The baseline JSON lives in the branch, so a branch could raise its own ceiling by
editing it in the commit that adds the debt. With ``--base-ref`` the allowance is the
baseline recorded at the fork point, and the working-tree baseline can only tighten it.
Each case builds a real git repository, so the comparison reads git, not a stub.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_nl_structural_debt as gate
import nl_debt_ceiling as debt_ceiling

_POLICY = "\n".join(
    f"Every reviewer must confirm that policy line number {n} holds before merging."
    for n in range(6)
)
_PAIR = "templates/rules/a.md|templates/rules/b.md"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, errors="replace"
    )


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _write(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: x\n---\n{body}\n", encoding="utf-8")


def _baseline(repo: Path, dup: dict | None = None, count: dict | None = None) -> None:
    path = repo / gate.BASELINE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"duplicate_blocks": dup or {}, "cardinality": count or {}}), encoding="utf-8"
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A clean tree with an empty baseline, committed on ``main``."""
    for subdir in ("templates/skills", "templates/agents", "templates/rules"):
        (tmp_path / subdir).mkdir(parents=True)
    _write(tmp_path, "templates/rules/a.md", "Alpha intro.\n" + _POLICY)
    _baseline(tmp_path)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, "base")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    return tmp_path


def _add_duplicate(repo: Path) -> None:
    _write(repo, "templates/rules/b.md", "Beta intro.\n" + _POLICY)


def test_hand_raised_baseline_covers_the_debt_without_a_base_ref(repo: Path) -> None:
    """Control: the hole. With no base ref the branch's own baseline is trusted."""
    _add_duplicate(repo)
    _baseline(repo, dup={_PAIR: gate.measure(repo)["duplicate_blocks"][_PAIR]})
    _commit(repo, "add debt and raise the ceiling")

    assert gate.run(repo, update=False) == 0


def test_hand_raised_baseline_is_refused_against_the_base_ref(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_duplicate(repo)
    _baseline(repo, dup={_PAIR: gate.measure(repo)["duplicate_blocks"][_PAIR]})
    _commit(repo, "add debt and raise the ceiling")

    assert gate.run(repo, update=False, base_ref="main") == 1
    err = capsys.readouterr().err
    assert f"duplicate block {_PAIR}" in err
    assert "base-ref ceiling 0" in err


def test_new_stale_count_listed_in_the_working_baseline_is_refused(repo: Path) -> None:
    _write(repo, "templates/rules/c.md", "Run the three filters: a, b, c, d.")
    key = next(iter(gate.measure(repo)["cardinality"]))
    _baseline(repo, count={key: gate.measure(repo)["cardinality"][key]})
    _commit(repo, "add a stale count and record it")

    assert gate.run(repo, update=False) == 0
    assert gate.run(repo, update=False, base_ref="main") == 1


def test_unchanged_debt_recorded_at_the_base_passes(repo: Path) -> None:
    _add_duplicate(repo)
    _baseline(repo, dup={_PAIR: gate.measure(repo)["duplicate_blocks"][_PAIR]})
    _commit(repo, "main carries the debt")
    _git(repo, "branch", "-f", "main", "HEAD")
    _write(repo, "templates/rules/unrelated.md", "Unrelated text.")
    _commit(repo, "unrelated change")

    assert gate.run(repo, update=False, base_ref="main") == 0


def test_burn_down_recorded_in_the_branch_passes(repo: Path) -> None:
    _add_duplicate(repo)
    _baseline(repo, dup={_PAIR: gate.measure(repo)["duplicate_blocks"][_PAIR]})
    _commit(repo, "main carries the debt")
    _git(repo, "branch", "-f", "main", "HEAD")
    (repo / "templates/rules/b.md").unlink()
    _baseline(repo)
    _commit(repo, "pay the debt down and record it")

    assert gate.run(repo, update=False, base_ref="main") == 0


def test_burn_down_not_recorded_still_demands_a_baseline_update(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ceiling tightens growth only. Shrink is still read from the working baseline."""
    _add_duplicate(repo)
    _baseline(repo, dup={_PAIR: gate.measure(repo)["duplicate_blocks"][_PAIR]})
    _commit(repo, "main carries the debt")
    _git(repo, "branch", "-f", "main", "HEAD")
    (repo / "templates/rules/b.md").unlink()
    _commit(repo, "pay the debt down, leave the baseline")

    assert gate.run(repo, update=False, base_ref="main") == 1
    assert "stale" in capsys.readouterr().err


def test_update_baseline_cannot_launder_a_raise_against_the_base_ref(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)
    _add_duplicate(repo)
    _baseline(repo, dup={_PAIR: gate.measure(repo)["duplicate_blocks"][_PAIR]})
    _commit(repo, "add debt and raise the ceiling")

    assert gate.run(repo, update=True, base_ref="main") == 1


def test_stale_branch_is_not_blamed_for_a_baseline_main_lowered_later(repo: Path) -> None:
    """The fork point is the ceiling, so a main that burned debt down after the fork is moot."""
    _git(repo, "checkout", "-q", "main")
    _add_duplicate(repo)
    _baseline(repo, dup={_PAIR: gate.measure(repo)["duplicate_blocks"][_PAIR]})
    _commit(repo, "main carries the debt")
    _git(repo, "checkout", "-q", "-b", "stale")
    _git(repo, "checkout", "-q", "main")
    (repo / "templates/rules/b.md").unlink()
    _baseline(repo)
    _commit(repo, "main pays the debt down after the fork")
    _git(repo, "checkout", "-q", "stale")
    _write(repo, "templates/rules/unrelated.md", "Unrelated text.")
    _commit(repo, "stale branch change")

    assert gate.run(repo, update=False, base_ref="main") == 0


def test_baseline_absent_at_the_base_ref_is_the_bootstrap_run(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "checkout", "-q", "main")
    _git(repo, "rm", "-q", gate.BASELINE_PATH)
    _git(repo, "commit", "-q", "-m", "main predates the ratchet")
    _git(repo, "checkout", "-q", "feature")
    _git(repo, "merge", "-q", "main")
    _baseline(repo)
    _commit(repo, "introduce the baseline")

    assert gate.run(repo, update=False, base_ref="main") == 0
    assert "bootstrap" in capsys.readouterr().err


def test_unresolvable_base_ref_is_an_external_failure_not_a_pass(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.run(repo, update=False, base_ref="origin/does-not-exist") == 3
    assert "no merge base" in capsys.readouterr().err


def test_unrelated_history_has_no_fork_point(repo: Path) -> None:
    _git(repo, "checkout", "-q", "--orphan", "other")
    _git(repo, "commit", "-q", "-m", "unrelated root", "--allow-empty")
    _git(repo, "checkout", "-q", "feature")

    assert gate.run(repo, update=False, base_ref="other") == 3


def test_unparseable_baseline_at_the_base_ref_is_a_config_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "checkout", "-q", "main")
    (repo / gate.BASELINE_PATH).write_text("{not json", encoding="utf-8")
    _commit(repo, "corrupt the base baseline")
    _git(repo, "checkout", "-q", "feature")
    _git(repo, "merge", "-q", "main")
    _baseline(repo)
    _commit(repo, "repair on the branch")

    assert gate.run(repo, update=False, base_ref="main") == 2
    assert "at main (fork " in capsys.readouterr().err


def test_cli_returns_nonzero_for_a_raise_and_zero_for_a_clean_branch(repo: Path) -> None:
    assert gate.main([str(repo), "--base-ref", "main"]) == 0

    _add_duplicate(repo)
    _baseline(repo, dup={_PAIR: gate.measure(repo)["duplicate_blocks"][_PAIR]})
    _commit(repo, "add debt and raise the ceiling")

    assert gate.main([str(repo), "--base-ref", "main"]) == 1


def test_git_dir_of_another_checkout_does_not_redirect_the_fork_point(
    repo: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path_factory.mktemp("other")
    _git(other, "init", "-q", "-b", "main")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))

    assert gate.run(repo, update=False, base_ref="main") == 0


def test_no_base_ref_says_so_instead_of_claiming_a_ratchet(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.run(repo, update=False) == 0
    assert "no base ref" in capsys.readouterr().err


def test_pre_pr_entry_resolves_a_base_ref(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str | None] = []
    monkeypatch.setattr(gate, "default_base_ref", lambda root: "main")
    real_run = gate.run

    def spy(root: Path, update: bool, report: bool = False, base_ref: str | None = None) -> int:
        seen.append(base_ref)
        return real_run(root, update, report, base_ref)

    monkeypatch.setattr(gate, "run", spy)

    assert gate.validate_nl_structural_debt(repo) is True
    assert seen == ["main"]


def test_tighten_keeps_only_keys_both_baselines_hold_at_the_lower_count() -> None:
    working = {
        "duplicate_blocks": {"a|b": 5, "c|d": 2},
        "cardinality": {"k1": "x", "k2": "y"},
        "cohesion": {"r": 7, "s": 3},
    }
    ceiling = {
        "duplicate_blocks": {"a|b": 2},
        "cardinality": {"k1": "x"},
        "cohesion": {"r": 9},
    }

    assert debt_ceiling.tighten(working, ceiling) == {
        "duplicate_blocks": {"a|b": 2},
        "cardinality": {"k1": "x"},
        "cohesion": {"r": 7},
    }


def test_ceiling_read_is_logged_with_the_fork_point(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.run(repo, update=False, base_ref="main") == 0
    assert "[NOTE] ceiling read from" in capsys.readouterr().err


def test_ls_tree_failure_is_an_external_failure_not_a_bootstrap_pass(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real = debt_ceiling._git

    def failing_ls_tree(root: Path, *argv: str) -> subprocess.CompletedProcess[str]:
        if argv[0] == "ls-tree":
            return subprocess.CompletedProcess(argv, 128, "", "fatal: not a tree object")
        return real(root, *argv)

    monkeypatch.setattr(debt_ceiling, "_git", failing_ls_tree)

    assert gate.run(repo, update=False, base_ref="main") == 3
    assert "fatal: not a tree object" in capsys.readouterr().err


def test_every_git_read_carries_the_timeout(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spy = MagicMock(wraps=subprocess.run)
    monkeypatch.setattr(debt_ceiling.subprocess, "run", spy)

    assert gate.run(repo, update=False, base_ref="main") == 0
    timeouts = [call.kwargs["timeout"] for call in spy.call_args_list]
    assert len(timeouts) == 3  # merge-base, ls-tree, show
    assert set(timeouts) == {debt_ceiling.GIT_TIMEOUT_SECONDS}


def test_growth_line_names_the_base_ref_as_the_source_of_the_cap(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_duplicate(repo)
    _baseline(repo, dup={_PAIR: gate.measure(repo)["duplicate_blocks"][_PAIR]})
    _commit(repo, "add debt and raise the ceiling")

    assert gate.run(repo, update=False, base_ref="main") == 1
    err = capsys.readouterr().err
    assert "base-ref ceiling 0 (working-tree baseline says " in err
    assert "cannot be raised on the branch" in err


def test_growth_without_a_base_ref_keeps_the_plain_baseline_wording(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add_duplicate(repo)

    assert gate.run(repo, update=False) == 1
    err = capsys.readouterr().err
    assert "baseline 0" in err
    assert "base-ref ceiling" not in err
    assert "cannot be raised on the branch" not in err


def test_cardinality_raise_is_labelled_as_absent_at_the_base_ref(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(repo, "templates/rules/c.md", "Run the three filters: a, b, c, d.")
    key = next(iter(gate.measure(repo)["cardinality"]))
    _baseline(repo, count={key: gate.measure(repo)["cardinality"][key]})
    _commit(repo, "add a stale count and record it")

    assert gate.run(repo, update=False, base_ref="main") == 1
    assert "absent at the base ref" in capsys.readouterr().err


def test_mistyped_ref_reports_git_stderr_not_only_the_unshallow_hint(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.run(repo, update=False, base_ref="origin/does-not-exist") == 3
    err = capsys.readouterr().err
    assert "origin/does-not-exist" in err
    assert "mistyped ref" in err


def test_ref_starting_with_a_dash_is_not_read_as_a_git_option(repo: Path) -> None:
    assert gate.run(repo, update=False, base_ref="--all") == 3


def test_fork_sha_is_named_when_the_baseline_cannot_be_read(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(repo, "checkout", "-q", "main")
    (repo / gate.BASELINE_PATH).write_text("{not json", encoding="utf-8")
    _commit(repo, "corrupt the base baseline")
    _git(repo, "checkout", "-q", "feature")
    _git(repo, "merge", "-q", "main")
    _baseline(repo)
    _commit(repo, "repair on the branch")
    sha = subprocess.run(
        ["git", "rev-parse", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    ).stdout.strip()

    assert gate.run(repo, update=False, base_ref="main") == 2
    assert f"fork {sha[:12]}" in capsys.readouterr().err


def test_git_show_failure_after_the_fork_point_resolves_is_an_external_failure(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real = debt_ceiling._git

    def failing_show(root: Path, *argv: str) -> subprocess.CompletedProcess[str]:
        if argv[0] == "show":
            return subprocess.CompletedProcess(argv, 128, "", "fatal: bad object")
        return real(root, *argv)

    monkeypatch.setattr(debt_ceiling, "_git", failing_show)

    assert gate.run(repo, update=False, base_ref="main") == 3
    err = capsys.readouterr().err
    assert "could not read" in err
    assert "fatal: bad object" in err


def test_git_that_cannot_launch_is_an_external_failure(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_git(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    monkeypatch.setattr(debt_ceiling.subprocess, "run", no_git)

    assert gate.run(repo, update=False, base_ref="main") == 3
    assert "git could not be launched" in capsys.readouterr().err


def test_hung_git_is_bounded_and_fails_external_not_hung(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[object] = []

    def hung(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired("git", 30)

    monkeypatch.setattr(debt_ceiling.subprocess, "run", hung)

    assert gate.run(repo, update=False, base_ref="main") == 3
    assert seen == [debt_ceiling.GIT_TIMEOUT_SECONDS]
    assert "did not finish" in capsys.readouterr().err


def test_failed_local_refresh_warns_instead_of_trusting_a_stale_ref(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import checks_common

    monkeypatch.setattr(checks_common, "_resolve_default_base_ref", lambda root: "origin/main")
    monkeypatch.setattr(checks_common, "_refresh_remote_base", lambda ref, root: "network down")

    assert debt_ceiling.default_base_ref(repo) == "origin/main"
    err = capsys.readouterr().err
    assert "[WARN] could not refresh origin/main (network down)" in err


def test_successful_local_refresh_is_silent(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import checks_common

    monkeypatch.setattr(checks_common, "_resolve_default_base_ref", lambda root: "origin/main")
    monkeypatch.setattr(checks_common, "_refresh_remote_base", lambda ref, root: "")

    assert debt_ceiling.default_base_ref(repo) == "origin/main"
    assert capsys.readouterr().err == ""


def test_no_resolvable_default_ref_returns_none(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import checks_common

    monkeypatch.setattr(checks_common, "_resolve_default_base_ref", lambda root: None)

    assert debt_ceiling.default_base_ref(repo) is None


def _cohesion_rule(repo: Path) -> str:
    """Write a rule claiming five unrelated top-level roots, and return its cohesion key."""
    roots = ["src/**", "docs/**", "tests/**", "build/**", "scripts/**"]
    frontmatter = "paths:\n" + "".join(f"  - {r!r}\n" for r in roots)
    path = repo / "templates/rules/wide.md"
    path.write_text(f"---\nname: x\n{frontmatter}---\nWide rule.\n", encoding="utf-8")
    return next(iter(gate.measure(repo)["cohesion"]))


def test_hand_raised_cohesion_entry_is_refused_against_the_base_ref(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    key = _cohesion_rule(repo)
    spread = gate.measure(repo)["cohesion"][key]
    (repo / gate.BASELINE_PATH).write_text(
        json.dumps({"duplicate_blocks": {}, "cardinality": {}, "cohesion": {key: spread}}),
        encoding="utf-8",
    )
    _commit(repo, "add a wide rule and record its spread")

    assert gate.run(repo, update=False) == 0
    assert gate.run(repo, update=False, base_ref="main") == 1
    assert f"low cohesion {key}" in capsys.readouterr().err
