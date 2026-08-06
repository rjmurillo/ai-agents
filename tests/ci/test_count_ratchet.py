from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from scripts.ci import count_ratchet


def test_chunk_respects_argv_budget():
    paths = [f"{'x' * 99}{index}.py" for index in range(500)]
    batches = count_ratchet.chunk(paths, budget=1000)
    assert sum(len(batch) for batch in batches) == len(paths)
    assert all(sum(len(p.encode("utf-8")) + 1 for p in batch) <= 1000 for batch in batches)
    assert all(batch for batch in batches)


def test_chunk_measures_bytes_not_characters():
    # A non-ASCII path costs more argv than it has characters. Measuring
    # characters would pack batches over the ceiling the budget exists to
    # respect. Each name here is 13 characters but 22 UTF-8 bytes.
    stem = "\u00e9" * 9
    paths = [f"{stem}{index}.py" for index in range(10)]
    assert len(paths[0]) == 13
    assert len(paths[0].encode("utf-8")) == 22
    batches = count_ratchet.chunk(paths, budget=46)
    assert sum(len(batch) for batch in batches) == len(paths)
    assert all(sum(len(p.encode("utf-8")) + 1 for p in batch) <= 46 for batch in batches)
    # Two per batch fits the byte budget; a character measure would pack three.
    assert max(len(batch) for batch in batches) == 2


def test_single_path_longer_than_budget_still_scanned():
    # A path larger than the whole budget must not be silently dropped.
    oversized = "y" * 5000 + ".py"
    assert count_ratchet.chunk([oversized], budget=100) == [[oversized]]


def test_tracked_files_returns_none_when_git_fails(tmp_path, monkeypatch):
    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="not a repo\n")

    monkeypatch.setattr(subprocess, "run", _run)
    assert count_ratchet.tracked_files(tmp_path, ("*.py",)) is None


def test_tracked_files_drops_the_nul_terminator(tmp_path, monkeypatch):
    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="a.py\0b.py\0", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    assert count_ratchet.tracked_files(tmp_path, ("*.py",)) == ["a.py", "b.py"]


def test_read_baseline_rejects_a_non_integer(tmp_path):
    path = tmp_path / "b.txt"
    path.write_text("not a number\n", encoding="utf-8")
    assert count_ratchet.read_baseline(path) is None


def test_read_baseline_returns_none_when_missing(tmp_path):
    assert count_ratchet.read_baseline(tmp_path / "absent.txt") is None


# ---------------------------------------------------------------------------
# lister parameter behavior (issue #3902)
# ---------------------------------------------------------------------------


def _make_args(tmp_path: Path, baseline_value: int) -> argparse.Namespace:
    baseline_file = tmp_path / "baseline.txt"
    baseline_file.write_text(f"{baseline_value}\n", encoding="utf-8")
    return argparse.Namespace(
        baseline=baseline_file,
        repo_root=tmp_path,
        update=False,
        base_ref=None,
    )


def test_lister_called_and_printed_on_regression(tmp_path, capsys):
    """Violations are printed to stderr when lister is provided and a regression fires."""
    args = _make_args(tmp_path, baseline_value=5)
    violations = ["file1.py: use X", "file2.py: avoid Y"]

    rc = count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: 7,  # 7 > 5 => regression
        scan_error="scan failed",
        regression_advice="fix it",
        lister=lambda _root, _changed: violations,
    )

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "file1.py: use X" in err
    assert "file2.py: avoid Y" in err


def test_lister_not_called_on_ok(tmp_path, capsys):
    """Lister is never called when there is no regression (count <= baseline)."""
    args = _make_args(tmp_path, baseline_value=10)
    called: list[bool] = []

    def _recording_lister(_root: Path, _changed: frozenset[str]) -> list[str] | None:
        called.append(True)
        return ["oops"]

    rc = count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: 10,  # equal to baseline => ok
        scan_error="scan failed",
        regression_advice="fix it",
        lister=_recording_lister,
    )

    assert rc == count_ratchet.EXIT_OK
    assert called == [], "lister must not be invoked when there is no regression"


def test_run_blocks_a_baseline_with_too_much_slack(tmp_path, capsys):
    """Wiring: run() must reject a stale-high baseline, not only regressions."""
    actual = 10
    baseline = 17
    args = _make_args(tmp_path, baseline_value=baseline)

    rc = count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: actual,
        scan_error="scan failed",
        regression_advice="fix it",
        lister=None,
    )

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "STALE BASELINE" in err
    assert "write 10 into the baseline file" in err


def test_no_lister_regression_has_no_violation_list(tmp_path, capsys):
    """When lister is None, a regression message appears but no violation lines."""
    args = _make_args(tmp_path, baseline_value=5)

    rc = count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: 8,  # 8 > 5 => regression
        scan_error="scan failed",
        regression_advice="fix it",
        lister=None,
    )

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "REGRESSION" in err
    assert "Current violations" not in err


def test_lister_truncates_at_40_violations(tmp_path, capsys):
    """Only the first 40 violations are printed; the remainder is summarised."""
    args = _make_args(tmp_path, baseline_value=5)
    violations = [f"file{i}.py: issue" for i in range(50)]

    count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: 55,
        scan_error="scan failed",
        regression_advice="fix it",
        lister=lambda _root, _changed: violations,
    )

    err = capsys.readouterr().err
    assert "file0.py: issue" in err
    assert "file39.py: issue" in err
    assert "file40.py: issue" not in err
    assert "10 more" in err


def test_lister_returning_none_does_not_crash(tmp_path, capsys):
    """If lister returns None, no violation list is printed and the run still fails."""
    args = _make_args(tmp_path, baseline_value=5)

    rc = count_ratchet.run(
        args,
        label="test",
        counter=lambda _root: 7,
        scan_error="scan failed",
        regression_advice="fix it",
        lister=lambda _root, _changed: None,
    )

    assert rc == count_ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "REGRESSION" in err
    assert "Current violations" not in err


# changed_files: which paths the branch touched (adversarial review of #3902).
#
# The regression diagnostic caps at 40 lines against a tree carrying 601
# violations, so without an ordering signal the branch's own violation is
# statistically invisible. This is that signal, and it must fail soft: an
# unusable answer degrades the list order, it must never block a push.


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo_with_a_branch_commit(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "base.py").write_text("base\n", encoding="utf-8")
    # Committed on main so --base-ref can read a baseline there. An uncommitted
    # baseline makes baseline_at_ref fail and the run never reaches the lister.
    (repo / "baseline.txt").write_text("0\n", encoding="utf-8")
    _git(repo, "add", "base.py", "baseline.txt")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "topic")
    (repo / "touched.py").write_text("touched\n", encoding="utf-8")
    _git(repo, "add", "touched.py")
    _git(repo, "commit", "-qm", "topic")
    return repo


def test_changed_files_names_only_the_branch_commit(tmp_path):
    """Positive: the file the branch added, and not the one it inherited."""
    repo = _repo_with_a_branch_commit(tmp_path)
    assert count_ratchet.changed_files(repo, "main") == frozenset({"touched.py"})


def test_changed_files_ignores_what_the_base_moved_on_to(tmp_path):
    """Positive: three-dot semantics.

    A branch behind its base must not inherit every file the base changed
    meanwhile, or the priority set degenerates to "everything" and the
    ordering signal is worth nothing.
    """
    repo = _repo_with_a_branch_commit(tmp_path)
    _git(repo, "checkout", "-q", "main")
    (repo / "moved_on.py").write_text("later\n", encoding="utf-8")
    _git(repo, "add", "moved_on.py")
    _git(repo, "commit", "-qm", "main moves on")
    _git(repo, "checkout", "-q", "topic")
    assert count_ratchet.changed_files(repo, "main") == frozenset({"touched.py"})


def test_changed_files_is_empty_for_an_unknown_ref(tmp_path, capsys):
    """Negative: a ref git cannot resolve degrades, it does not raise.

    The tree is clean here, so the working-tree probe added by the review of
    #4284 contributes nothing and the whole set is still empty. The dirty case,
    where that probe carries the result alone, is pinned below.
    """
    repo = _repo_with_a_branch_commit(tmp_path)
    assert count_ratchet.changed_files(repo, "no/such/ref") == frozenset()
    assert "could not resolve no/such/ref" in capsys.readouterr().err


def test_changed_files_is_empty_without_a_base_ref(tmp_path):
    """Edge: --base-ref is optional, so None must short-circuit before git."""
    assert count_ratchet.changed_files(tmp_path, None) == frozenset()
    assert count_ratchet.changed_files(tmp_path, "") == frozenset()


def test_changed_files_is_empty_when_git_cannot_launch(tmp_path, monkeypatch, capsys):
    """Edge: no git binary degrades the order, it must not crash the gate.

    It must also say so (adversarial review of #4284). ``tracked_files`` writes
    its cause to stderr on both of its failure legs; this one shipped silent on
    both of its own, so an operator reading violations in scan order could not
    tell whether the branch touched nothing or git failed.
    """

    def _boom(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert count_ratchet.changed_files(tmp_path, "main") == frozenset()
    assert "git could not be launched" in capsys.readouterr().err


def test_the_lister_receives_the_changed_paths(tmp_path, capsys):
    """Positive: run() feeds the priority set through to the lister.

    Without this the lister could be prioritising against an empty set forever
    and every ordering test above would still pass.
    """
    repo = _repo_with_a_branch_commit(tmp_path)
    seen: list[frozenset[str]] = []

    def _recording_lister(_root: Path, changed: frozenset[str]) -> list[str]:
        seen.append(changed)
        return ["touched.py: [file-size] too long"]

    args = argparse.Namespace(
        repo_root=repo, baseline=repo / "baseline.txt", update=False, base_ref="main"
    )
    exit_code = count_ratchet.run(
        args,
        label="probe",
        counter=lambda _root: 1,
        scan_error="scan failed",
        regression_advice="fix it",
        lister=_recording_lister,
    )

    assert exit_code == count_ratchet.EXIT_REGRESSION
    assert seen == [frozenset({"touched.py"})]
    assert "touched.py: [file-size] too long" in capsys.readouterr().err


# The working tree is part of the scan surface (adversarial review of #4284).
#
# ``tracked_files`` lists the index and the linter reads each path off disk, so
# a staged or unstaged edit is counted like any other content. Detection that
# read ``base_ref...HEAD`` alone saw committed work only, so a violation
# introduced by a dirty file tripped the ratchet and then sorted in with the
# 601 historical entries it was supposed to lead: buried by the same 40-line
# cap this ordering exists to defeat. The inverse matters as much, and
# ``test_changed_files_names_only_the_branch_commit`` above pins it by
# asserting an exact one-element set on a clean tree.


def _dirty(repo: Path, name: str, *, stage: bool) -> None:
    (repo / name).write_text("changed\n", encoding="utf-8")
    if stage:
        _git(repo, "add", name)


def _one_failing_diff_leg(failing_spec: str):
    """Fail exactly one ``git diff`` spec and run every other command for real.

    The two legs cannot both be broken by a real repository: an unresolvable
    ``--base-ref`` is reachable with a bad ref, but ``git diff HEAD`` fails only
    on conditions a fixture cannot stage (an unreadable index, a corrupt
    object). Substituting one leg is the only way to prove the union survives
    losing either half.
    """
    real_run = subprocess.run

    def _run(cmd, **kwargs):
        if cmd[0] == "git" and "diff" in cmd and cmd[-1] == failing_spec:
            return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="fatal: bad object\n")
        return real_run(cmd, **kwargs)

    return _run


def test_changed_files_names_an_unstaged_edit(tmp_path):
    """Positive: an uncommitted edit is scanned, so it must be prioritised."""
    repo = _repo_with_a_branch_commit(tmp_path)
    _dirty(repo, "base.py", stage=False)
    assert count_ratchet.changed_files(repo, "main") == frozenset({"touched.py", "base.py"})


def test_changed_files_names_a_staged_edit(tmp_path):
    """Positive: staging is not committing, and the scan cannot tell them apart."""
    repo = _repo_with_a_branch_commit(tmp_path)
    _dirty(repo, "base.py", stage=True)
    assert count_ratchet.changed_files(repo, "main") == frozenset({"touched.py", "base.py"})


def test_changed_files_names_a_staged_addition(tmp_path):
    """Positive: `git add` of a new file puts it in the index, so it is scanned.

    ``git ls-files`` lists it from that moment, which is precisely when a new
    over-long file can trip the ratchet without ever having been committed.
    """
    repo = _repo_with_a_branch_commit(tmp_path)
    _dirty(repo, "added.py", stage=True)
    assert count_ratchet.changed_files(repo, "main") == frozenset({"touched.py", "added.py"})


def test_changed_files_ignores_an_untracked_file(tmp_path):
    """Negative: an untracked path is never scanned, so it must not be prioritised.

    ``tracked_files`` runs ``git ls-files``, which never offers it to the
    linter. Prioritising it would spend the 40-line budget on a path that
    cannot appear in the list at all.
    """
    repo = _repo_with_a_branch_commit(tmp_path)
    _dirty(repo, "scratch.py", stage=False)
    assert count_ratchet.changed_files(repo, "main") == frozenset({"touched.py"})


def test_changed_files_keeps_the_worktree_when_the_base_ref_is_unresolvable(tmp_path, capsys):
    """Edge: the committed leg can fail alone, and the other must survive it.

    A typo'd ``--base-ref`` used to erase the whole priority set. The dirty
    file is still the likeliest cause of the regression being diagnosed.
    """
    repo = _repo_with_a_branch_commit(tmp_path)
    _dirty(repo, "base.py", stage=False)
    assert count_ratchet.changed_files(repo, "no/such/ref") == frozenset({"base.py"})
    err = capsys.readouterr().err
    assert "ordering degraded" in err
    assert "no/such/ref" in err


def test_changed_files_keeps_committed_paths_when_the_worktree_probe_fails(
    tmp_path, monkeypatch, capsys
):
    """Edge: the mirror. The working-tree leg can fail alone too.

    Without this the union could be short-circuiting on the first probe and
    every test above would still pass. The committed paths are the ones a CI
    run has, where the working tree is clean and ``git diff HEAD`` is the leg
    with nothing to contribute, so losing them is the costlier direction.
    """
    repo = _repo_with_a_branch_commit(tmp_path)
    _dirty(repo, "base.py", stage=False)
    monkeypatch.setattr(subprocess, "run", _one_failing_diff_leg("HEAD"))
    assert count_ratchet.changed_files(repo, "main") == frozenset({"touched.py"})
    err = capsys.readouterr().err
    assert "ordering degraded" in err
    assert "could not resolve HEAD" in err


def test_changed_files_stays_a_silent_no_op_without_a_base_ref(tmp_path, capsys):
    """Inverse: the working-tree probe is gated on --base-ref like the other one.

    A caller that omits ``--base-ref`` asked for no ordering. Probing anyway
    would print a degradation note on every ratchet run outside a repository.
    """
    repo = _repo_with_a_branch_commit(tmp_path)
    _dirty(repo, "base.py", stage=False)
    assert count_ratchet.changed_files(repo, None) == frozenset()
    assert count_ratchet.changed_files(repo, "") == frozenset()
    assert capsys.readouterr().err == ""


def test_changed_files_is_silent_on_a_dirty_worktree(tmp_path, capsys):
    """Inverse: a dirty tree is the normal case and must not emit a note.

    These run on every pre-push. A note on a success path would train
    contributors to ignore the one that means something.
    """
    repo = _repo_with_a_branch_commit(tmp_path)
    _dirty(repo, "base.py", stage=False)
    assert count_ratchet.changed_files(repo, "main") == frozenset({"touched.py", "base.py"})
    assert capsys.readouterr().err == ""


def test_the_lister_receives_an_uncommitted_path(tmp_path, capsys):
    """Positive: run() carries the dirty file all the way to the lister.

    The unit tests above could pass while ``run`` still fed the lister a
    committed-only set, which is the shape the bug actually shipped in.
    """
    repo = _repo_with_a_branch_commit(tmp_path)
    _dirty(repo, "base.py", stage=False)
    seen: list[frozenset[str]] = []

    def _recording_lister(_root: Path, changed: frozenset[str]) -> list[str]:
        seen.append(changed)
        return ["base.py: [file-size] too long"]

    args = argparse.Namespace(
        repo_root=repo, baseline=repo / "baseline.txt", update=False, base_ref="main"
    )
    exit_code = count_ratchet.run(
        args,
        label="probe",
        counter=lambda _root: 1,
        scan_error="scan failed",
        regression_advice="fix it",
        lister=_recording_lister,
    )

    assert exit_code == count_ratchet.EXIT_REGRESSION
    assert seen == [frozenset({"touched.py", "base.py"})]
    assert "base.py: [file-size] too long" in capsys.readouterr().err
