"""Tests for the whole-repo taste-lint error-count ratchet (issue #3779)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.ci import count_ratchet
from scripts.ci import taste_count_ratchet as ratchet
from tests.ci.ratchet_test_helpers import make_baseline_writer


def _report(error_count: int) -> str:
    return json.dumps(
        {
            "files_scanned": 1,
            "files_by_category": {"authored": 1},
            "error_count": error_count,
            "warning_count": 0,
            "violations": [],
        }
    )


def _fake_scan(
    returncode: int,
    error_count: int,
    *,
    tracked: tuple[str, ...] = ("pkg/mod.py",),
    git_returncode: int = 0,
    base_baseline: str | None = None,
    lint_stdout: str | None = None,
    base_baseline_absent: bool = False,
    base_ref_resolves: bool = True,
    base_path_refused: bool = False,
):
    """subprocess.run stand-in for every leg of the scan.

    ``git ls-files -z`` returns ``tracked`` NUL-joined; ``git show`` returns
    ``base_baseline``; every linter invocation returns a report carrying
    ``error_count`` unless ``lint_stdout`` overrides it. The report is emitted
    once per linter call, so a multi-batch expectation must size ``tracked``
    accordingly.

    ``base_ref_resolves``, ``base_baseline_absent``, and ``base_path_refused``
    drive the two probes that separate the bootstrap case from a real failure:
    ``git rev-parse`` proves the ref exists and ``git ls-tree`` proves whether
    it carries a baseline. The ``ls-tree`` returns mirror what git 2.43.0
    actually does, which is exit 0 with empty output for a path that is merely
    absent and exit 128 for a path it refuses to look up at all.
    """

    def _run(cmd, **kwargs):
        if cmd[0] == "git" and "rev-parse" in cmd:
            rc = 0 if base_ref_resolves else 128
            return subprocess.CompletedProcess(cmd, rc, stdout="", stderr="")
        if cmd[0] == "git" and "ls-tree" in cmd:
            if base_path_refused:
                return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="")
            stdout = "" if base_baseline_absent else "100644 blob abc\tbaseline.txt\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
        if cmd[0] == "git" and "show" in cmd:
            rc = 0 if base_baseline is not None else 128
            return subprocess.CompletedProcess(cmd, rc, stdout=(base_baseline or ""), stderr="")
        if cmd[0] == "git":
            stdout = "\0".join(tracked) + ("\0" if tracked else "")
            return subprocess.CompletedProcess(cmd, git_returncode, stdout=stdout, stderr="")
        stdout = lint_stdout if lint_stdout is not None else _report(error_count)
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return _run


_write_baseline = make_baseline_writer("taste_count_baseline.txt")


def test_count_equal_to_baseline_passes(tmp_path, monkeypatch, capsys):
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 615))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK
    # Holding steady is not an improvement. Reporting "improved 615 -> 615
    # (-0)" would read as progress on a run that made none.
    out = capsys.readouterr().out
    assert "OK (count == baseline 615)" in out
    assert "improved" not in out


def test_count_above_baseline_is_a_regression(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 616))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_REGRESSION


def test_count_below_baseline_passes_without_update(tmp_path, monkeypatch):
    # Issue #4171: a small improvement is safe against the ceiling and must not
    # force every cleanup PR to rewrite the same baseline line.
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 612))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK
    assert baseline.read_text(encoding="utf-8").strip() == "615"  # baseline unchanged


def test_update_lowers_the_baseline(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 600))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path), "--update"])
    assert rc == ratchet.EXIT_OK
    assert baseline.read_text(encoding="utf-8").strip() == "600"


def test_update_cannot_raise_the_baseline(tmp_path, monkeypatch):
    # --update only ever lowers. A run that found more violations is a
    # regression, and writing the higher number would launder the debt.
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 700))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path), "--update"])
    assert rc == ratchet.EXIT_REGRESSION
    assert baseline.read_text(encoding="utf-8").strip() == "615"


def test_a_raised_baseline_fails_against_the_base_ref(tmp_path, monkeypatch):
    # The gate a PR would otherwise walk around: bump the baseline in the same
    # commit that adds the violations and the count check passes.
    baseline = _write_baseline(tmp_path, "700")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 700, base_baseline="615"))
    rc = ratchet.main(
        [
            "--baseline",
            str(baseline),
            "--repo-root",
            str(tmp_path),
            "--base-ref",
            "FETCH_HEAD",
        ]
    )
    assert rc == ratchet.EXIT_REGRESSION


def test_a_stale_branch_is_told_what_the_base_ref_already_allows(
    tmp_path, monkeypatch, capsys
):
    """Baseline 700, base 615, count 600: nothing here added a violation.

    The verdict must not accuse this author of raising an allowance. It does
    not name a cause it cannot measure either (issue #4066), so it reports the
    count, states that the base ref already allows it, and leads with the sync
    remedy.
    """
    baseline = _write_baseline(tmp_path, "700")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 600, base_baseline="615"))
    rc = ratchet.main(_base_ref_argv(baseline, tmp_path))
    captured = capsys.readouterr()
    assert rc == ratchet.EXIT_REGRESSION
    assert "BASELINE ABOVE BASE" in captured.err
    assert "The measured count is 600" in captured.err
    assert "nothing in this tree added a violation" in captured.err
    assert captured.err.index("merge or rebase") < captured.err.index(
        "fix the violations"
    )


def test_a_count_the_base_ref_does_not_allow_is_not_excused(
    tmp_path, monkeypatch, capsys
):
    """Baseline 700, base 615, count 650: the base ref does not allow 650.

    The exoneration in the test above must not be handed out here, or the two
    cases read alike and the message stops discriminating.
    """
    baseline = _write_baseline(tmp_path, "700")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 650, base_baseline="615"))
    rc = ratchet.main(_base_ref_argv(baseline, tmp_path))
    captured = capsys.readouterr()
    assert rc == ratchet.EXIT_REGRESSION
    assert "BASELINE ABOVE BASE" in captured.err
    assert "The measured count is 650" in captured.err
    assert "nothing in this tree added a violation" not in captured.err


def test_a_lowered_baseline_passes_against_the_base_ref(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "600")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 600, base_baseline="615"))
    rc = ratchet.main(
        [
            "--baseline",
            str(baseline),
            "--repo-root",
            str(tmp_path),
            "--base-ref",
            "FETCH_HEAD",
        ]
    )
    assert rc == ratchet.EXIT_OK


def test_unreadable_base_ref_is_an_external_error(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 615, base_baseline=None))
    rc = ratchet.main(
        [
            "--baseline",
            str(baseline),
            "--repo-root",
            str(tmp_path),
            "--base-ref",
            "FETCH_HEAD",
        ]
    )
    assert rc == ratchet.EXIT_EXTERNAL


def _base_ref_argv(baseline: Path, tmp_path: Path) -> list[str]:
    return [
        "--baseline",
        str(baseline),
        "--repo-root",
        str(tmp_path),
        "--base-ref",
        "FETCH_HEAD",
    ]


def test_a_stale_branch_is_named_as_behind_at_the_cli(tmp_path, monkeypatch, capsys):
    """The CLI, not just ``run``, must carry the corrected verdict.

    Baseline file 700, base ref 615, measured count 615: the base ref already
    allows what this tree measures, so nothing here added a violation and the
    sync remedy leads (issue #4066).
    """
    baseline = _write_baseline(tmp_path, "700")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 615, base_baseline="615"))
    rc = ratchet.main(_base_ref_argv(baseline, tmp_path))
    assert rc == ratchet.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert "BASELINE ABOVE BASE" in err
    assert "nothing in this tree added a violation" in err
    assert err.index("merge or rebase") < err.index("fix the violations")


def test_a_base_ref_without_a_baseline_yet_is_the_bootstrap_case(
    tmp_path, monkeypatch, capsys
):
    """The PR that introduces a ratchet is the PR that adds its baseline.

    Its base branch therefore has no baseline file, so the one-directional
    check has no earlier value to compare against. Reading that as an external
    error made the introducing PR red on arrival: `pr-validation` failed with
    "could not read the baseline at FETCH_HEAD" and exit 3 even though the
    count was exactly at baseline. There is nothing to raise on a first run.
    """
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_scan(10, 615, base_baseline=None, base_baseline_absent=True),
    )
    rc = ratchet.main(_base_ref_argv(baseline, tmp_path))
    assert rc == ratchet.EXIT_OK
    assert "bootstrap" in capsys.readouterr().out


def test_bootstrap_still_enforces_the_count_check(tmp_path, monkeypatch):
    """Bootstrap waives the baseline comparison, never the regression check.

    Waiving both would make the gate inert on the one run where its baseline is
    established, so a PR could introduce the ratchet and blow past it at once.
    """
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_scan(10, 700, base_baseline=None, base_baseline_absent=True),
    )
    rc = ratchet.main(_base_ref_argv(baseline, tmp_path))
    assert rc == ratchet.EXIT_REGRESSION


def test_an_unresolvable_base_ref_is_not_read_as_bootstrap(tmp_path, monkeypatch):
    """Fail closed. Only a resolvable ref that lacks the file is a first run.

    A typo'd ref, a missing fetch, or an absent git binary all make the read
    fail. Treating any of them as "nothing to compare against" would disarm the
    one-directional guard silently, which is the single outcome a ratchet must
    never produce.
    """
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_scan(
            10,
            615,
            base_baseline=None,
            base_baseline_absent=True,
            base_ref_resolves=False,
        ),
    )
    rc = ratchet.main(_base_ref_argv(baseline, tmp_path))
    assert rc == ratchet.EXIT_EXTERNAL


def test_missing_baseline_is_a_config_error(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 615))
    rc = ratchet.main(["--baseline", str(tmp_path / "absent.txt"), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_CONFIG


def test_malformed_baseline_is_a_config_error(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "six hundred")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 615))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_CONFIG


def test_git_failure_is_an_external_error(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 615, git_returncode=128))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_EXTERNAL


def test_a_crashed_linter_is_not_a_clean_tree(tmp_path, monkeypatch):
    """The failure mode that would disarm this gate permanently.

    taste_lints.py exits 1 on a script error. If that were read as a count of
    zero, the ratchet would report a 615-violation improvement, and a run with
    --update would write 0 into the baseline. Nothing after that could ever
    fail. So a non-scan exit code must be an external error, not a count.
    """
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 0, lint_stdout=""))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_EXTERNAL


def test_a_crashed_linter_that_still_printed_a_report_is_rejected(tmp_path, monkeypatch):
    """Isolating control for the exit-code guard specifically.

    The JSON guard alone is not enough. A linter that crashed partway can still
    have printed a well-formed report covering the files it managed to read,
    and that report's count is not the tree's count. Only the exit code says
    whether the scan finished, so it has to be checked on its own.
    """
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(1, 0, lint_stdout=_report(0)))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_EXTERNAL


def test_a_clean_exit_is_a_real_zero(tmp_path, monkeypatch):
    # Exit 0 means the lint ran and found nothing. Unlike exit 1 it is a
    # trustworthy count and must be accepted, or a genuinely clean tree could
    # never lower the baseline.
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(0, 0))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path), "--update"])
    assert rc == ratchet.EXIT_OK
    assert baseline.read_text(encoding="utf-8").strip() == "0"


def test_unparseable_report_is_an_external_error(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 0, lint_stdout="not json"))
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_EXTERNAL


def test_a_non_mapping_report_is_an_external_error(tmp_path, monkeypatch):
    """A report that parsed as JSON but is not an object (review of #4284).

    ``report.get("error_count")`` raised AttributeError on a list, a string, or
    a bare null, and the traceback left the process exiting 1: the ratchet's
    own code for a REGRESSION. An unreadable report is an external error and
    must exit 3, or a broken linter reads as new violations a contributor
    cannot find.
    """
    baseline = _write_baseline(tmp_path, "615")
    for payload in ("null", "7", '"hello"', '[{"error_count": 3}]'):
        monkeypatch.setattr(subprocess, "run", _fake_scan(10, 0, lint_stdout=payload))
        rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
        assert rc == ratchet.EXIT_EXTERNAL, payload


def test_report_without_an_integer_count_is_an_external_error(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(
        subprocess, "run", _fake_scan(10, 0, lint_stdout=json.dumps({"violations": []}))
    )
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_EXTERNAL


def test_counts_are_summed_across_batches(tmp_path, monkeypatch):
    # 7,500 tracked paths do not fit one argv, so the scan is chunked and each
    # batch reports its own count. Reading only the last would undercount.
    tracked = tuple(f"{'p' * 200}/{index}.py" for index in range(400))
    batches = len(count_ratchet.chunk(list(tracked)))
    assert batches > 1, "fixture must span more than one batch to test summing"
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 1, tracked=tracked))
    assert ratchet.current_count(tmp_path) == batches


def test_an_empty_tracked_set_counts_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_scan(10, 5, tracked=()))
    assert ratchet.current_count(tmp_path) == 0


def test_every_tracked_path_is_offered_to_the_linter(tmp_path, monkeypatch):
    """Scope is the whole tracked set, not a suffix-filtered subset.

    ``run_lint`` already skips anything outside its scannable-extension set.
    Filtering here would duplicate that list and let the two drift, so a PR
    adding a new scannable extension to the linter would silently stay
    unratcheted.
    """
    seen: list[list[str]] = []

    def _run(cmd, **kwargs):
        seen.append(list(cmd))
        if cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 0, stdout="a.md\0b.py\0", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout=_report(0), stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    ratchet.current_count(tmp_path)
    assert seen[0][seen[0].index("--") + 1 :] == ["*"]
    assert seen[1][-2:] == ["a.md", "b.py"]


def test_a_baseline_path_git_refuses_is_not_read_as_bootstrap(tmp_path, monkeypatch):
    """A path git will not look up is an error, never a first run.

    This is the case the old `cat-file -e` probe could not see. Measured on git
    2.43.0, `git cat-file -e <ref>:<path>` exits 128 both for a path that is
    merely absent from the tree and for a path git refuses outright, such as
    one that escapes the worktree. Reading rc != 0 as "no baseline yet"
    therefore waived the one-directional check for a misconfigured baseline
    path, which is the exact fail-open a ratchet must never produce.
    """
    baseline = _write_baseline(tmp_path, "615")
    monkeypatch.setattr(
        subprocess,
        "run",
        _fake_scan(10, 615, base_baseline=None, base_path_refused=True),
    )
    rc = ratchet.main(_base_ref_argv(baseline, tmp_path))
    assert rc == ratchet.EXIT_EXTERNAL


def test_a_git_that_cannot_be_launched_is_not_bootstrap(tmp_path, monkeypatch):
    """An unlaunchable git is an error on both probes, not a first run.

    The ref probe and the path probe fail independently. A fake that only
    covers the ref probe leaves the path probe free to read its own launch
    failure as "no baseline yet", which disarms the one-directional check on
    any runner whose git disappears mid-run.
    """
    real_run = subprocess.run

    def _run(cmd, **kwargs):
        if cmd[0] == "git" and "ls-tree" in cmd:
            raise FileNotFoundError("git: not found")
        if cmd[0] == "git" and "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        kwargs.pop("encoding", None)
        kwargs.pop("errors", None)
        return real_run(cmd, encoding="utf-8", errors="replace", **kwargs)

    monkeypatch.setattr(subprocess, "run", _run)
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("615\n", encoding="utf-8")
    assert count_ratchet.baseline_absent_at_ref(tmp_path, "HEAD", baseline) is False
