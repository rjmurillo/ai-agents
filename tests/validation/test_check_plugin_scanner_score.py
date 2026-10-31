"""Guards for the plugin scanner score gate.

The scanner itself is not run here (about 50s and a network install); every
test replaces the subprocess boundary or uses a throwaway git repository. The
subprocess helper and the time budget are covered in
``test_check_plugin_scanner_run.py``.

Coverage:

- positive: a report at or above the minimum exits 0 and prints the score,
  margin, examined package count, and the checks that lost points;
  ``export_ref`` writes the committed tree; ``_run`` returns a child's output.
- negative: a report below the minimum exits 1 and names each check that lost
  points; a missing report, a failed install, a scanner timeout, a git timeout
  or failed write while exporting, a missing ``uv``, a spent budget, a report
  with no integer score, and unreadable JSON exit 3; a bad ref, a git that
  cannot start, a cwd outside the resolved root, a directory outside git, and
  a bad argument exit 2; a timed-out child's process group is killed.
- edge: ``export_ref`` leaves untracked files out, keeps ``export-ignore``
  paths and symlinks a clone has, deletes repository scanner config, and reads
  a ref other than HEAD; a ref spelled like an option is not read as one; a
  score equal to the minimum passes; a nonzero scanner exit with a report is
  reported but scored; a report with no categories still summarizes;
  ``--help`` exits 0; a ``--min-score`` outside 1 to 100 exits 2.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_plugin_scanner_score as gate

_REAL_RUN = gate._run
Fake = Callable[[list[str]], subprocess.CompletedProcess[bytes] | None]


def _report(score: object, lost: int = 0) -> dict[str, object]:
    return {
        "score": score,
        "packages": [{"name": "a"}, {"name": "b"}],
        "categories": [
            {
                "name": "[claude:.] Security",
                "checks": [
                    {
                        "name": "SECURITY.md found",
                        "points": 3 - lost,
                        "maxPoints": 3,
                        "message": "m",
                    },
                    {"name": "LICENSE found", "points": 3, "maxPoints": 3, "message": "ok"},
                ],
            }
        ],
    }


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "tracked.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "init")
    (repo / "untracked.txt").write_text("y", encoding="utf-8")
    monkeypatch.chdir(repo)
    return repo


def _patch_run(monkeypatch: pytest.MonkeyPatch, fake: Fake) -> list[list[str]]:
    """Route ``gate._run`` through ``fake``; a ``None`` answer runs the real command."""
    seen: list[list[str]] = []

    def run(
        args: list[str], cwd: Path, timeout: float, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[bytes]:
        seen.append(args)
        answer = fake(args)
        return _REAL_RUN(args, cwd, timeout, env) if answer is None else answer

    monkeypatch.setattr(gate, "_run", run)
    return seen


def _done(args: list[str], code: int = 0, err: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args, code, b"", err)


def _raise(exc: BaseException) -> Fake:
    def fake(args: list[str]) -> None:
        raise exc

    return fake


def _deadline() -> gate.Deadline:
    return gate.Deadline(gate.TOTAL_BUDGET_SECONDS)


def _fake_scanner(monkeypatch: pytest.MonkeyPatch, report: object) -> None:
    def write_report(_root: Path, _tree: Path, path: Path, _deadline: gate.Deadline) -> None:
        path.write_text(json.dumps(report), encoding="utf-8")

    monkeypatch.setattr(gate, "run_scanner", write_report)


def test_score_at_minimum_passes_and_shows_what_costs_points(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_scanner(monkeypatch, _report(80, lost=3))
    assert gate.main([]) == 0
    out = capsys.readouterr().out
    assert "score=80 min=80 margin=0 ref=HEAD packages=2 elapsed=" in out
    assert "-3  [claude:.] Security: SECURITY.md found (m)" in out


def test_score_below_minimum_fails_and_names_lost_checks(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_scanner(monkeypatch, _report(54, lost=3))
    assert gate.main([]) == 1
    err = capsys.readouterr().err
    assert "-3  [claude:.] Security: SECURITY.md found (m)" in err
    assert "LICENSE found" not in err
    assert "score 54 is below 80" in err
    # The catalog bar (75) differs from this gate's default (80), so the
    # message must not claim the listing needs 80.
    assert "listing bar is 75" in err
    assert "requires 80" not in err


def test_min_score_flag_moves_the_bar(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_scanner(monkeypatch, _report(80))
    assert gate.main(["--min-score", "81"]) == 1


@pytest.mark.parametrize("report", [_report(None), _report("80"), ["not", "an", "object"]])
def test_malformed_report_is_external_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, report: object
) -> None:
    _fake_scanner(monkeypatch, report)
    assert gate.main([]) == 3


def test_unreadable_report_is_external_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def write_garbage(_root: Path, _tree: Path, path: Path, _deadline: gate.Deadline) -> None:
        path.write_text("{not json", encoding="utf-8")

    monkeypatch.setattr(gate, "run_scanner", write_garbage)
    assert gate.main([]) == 3


def test_scanner_without_report_is_external_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake(args: list[str]) -> subprocess.CompletedProcess[bytes] | None:
        if "scan" in args:
            return _done(args, 1, b"Traceback: boom")
        return _done(args) if args[0] == "uv" else None

    _patch_run(monkeypatch, fake)
    assert gate.main([]) == 3
    assert "wrote no report (exit 1): Traceback: boom" in capsys.readouterr().err


def test_failed_install_is_external_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_run(monkeypatch, lambda args: _done(args, 2, b"no network") if "sync" in args else None)
    assert gate.main([]) == 3
    assert "scanner install failed (exit 2): no network" in capsys.readouterr().err


def test_scanner_timeout_is_external_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake(args: list[str]) -> subprocess.CompletedProcess[bytes] | None:
        if "scan" in args:
            raise subprocess.TimeoutExpired(args, 1)
        return _done(args) if args[0] == "uv" else None

    _patch_run(monkeypatch, fake)
    assert gate.main([]) == 3
    assert f"scanner scan exceeded the {gate.TOTAL_BUDGET_SECONDS}s budget" in (
        capsys.readouterr().err
    )


def test_missing_uv_is_external_error(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(args: list[str]) -> None:
        if args[0] == "uv":
            raise FileNotFoundError("uv")

    _patch_run(monkeypatch, fake)
    assert gate.main([]) == 3


def test_scanner_that_cannot_start_is_external_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake(args: list[str]) -> None:
        if args[0] == "uv":
            raise PermissionError("uv is not executable")

    _patch_run(monkeypatch, fake)
    assert gate.main([]) == 3
    assert "cannot start scanner install: uv is not executable" in capsys.readouterr().err


def test_clean_pass_prints_no_empty_lost_header(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_scanner(monkeypatch, _report(100))
    assert gate.main([]) == 0
    assert "Checks that lost points" not in capsys.readouterr().out


def test_nonzero_scanner_exit_with_a_report_is_reported_and_scored(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = tmp_path / "r.json"

    def fake(args: list[str]) -> subprocess.CompletedProcess[bytes]:
        if "scan" in args:
            report.write_text("{}", encoding="utf-8")
            return _done(args, 5, b"partial crash")
        return _done(args)

    _patch_run(monkeypatch, fake)
    gate.run_scanner(git_repo, git_repo / "tree", report, _deadline())
    assert "scanner exited 5 but wrote a report: partial crash" in capsys.readouterr().err


def test_scanner_commands_use_the_pinned_project(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _patch_run(monkeypatch, lambda args: _done(args))
    report = git_repo / "r.json"
    report.write_text("{}", encoding="utf-8")
    gate.run_scanner(git_repo, git_repo / "tree", report, _deadline())
    install, scan = seen
    assert install[:2] == ["uv", "sync"]
    assert scan[:3] == ["uv", "run", "--no-sync"]
    for command in (install, scan):
        assert command[command.index("--project") + 1].endswith("build/plugin-scanner")
        assert "--frozen" in command
    assert scan[scan.index("--fail-on-severity") + 1] == "none"
    assert "--config" not in scan


def test_bad_ref_is_config_error(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main(["--ref", "no-such-ref"]) == 2
    assert "cannot export ref 'no-such-ref'" in capsys.readouterr().err


def test_option_shaped_ref_is_not_read_as_an_option(
    git_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.main(["--ref=--help"]) == 2
    assert "cannot export ref '--help'" in capsys.readouterr().err


def test_git_that_cannot_start_is_config_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_run(monkeypatch, _raise(OSError("no git")))
    assert gate.main([]) == 2


def test_cwd_outside_resolved_root_is_config_error(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _patch_run(
        monkeypatch,
        lambda args: subprocess.CompletedProcess(args, 0, f"{elsewhere}\n".encode(), b""),
    )
    assert gate.main([]) == 2


def test_outside_git_is_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert gate.main([]) == 2


def test_bad_argument_is_config_error() -> None:
    assert gate.main(["--min-score", "eighty"]) == 2


@pytest.mark.parametrize("value", ["0", "-5", "101"])
def test_min_score_out_of_range_is_config_error(value: str) -> None:
    assert gate.main(["--min-score", value]) == 2


def test_help_exits_zero() -> None:
    assert gate.main(["--help"]) == 0


def test_export_ref_writes_only_the_committed_tree(git_repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    gate.export_ref(git_repo, "HEAD", out, _deadline())
    assert (out / "tracked.txt").read_text(encoding="utf-8") == "x"
    assert not (out / "untracked.txt").exists()


def test_export_ref_keeps_what_a_clone_keeps(git_repo: Path, tmp_path: Path) -> None:
    """``git archive`` would drop export-ignore paths; a clone does not."""
    (git_repo / ".gitattributes").write_text(".gitattributes export-ignore\n", encoding="utf-8")
    (git_repo / "link").symlink_to("tracked.txt")
    _git(git_repo, "add", ".gitattributes", "link")
    _git(git_repo, "commit", "-q", "-m", "attrs")
    out = tmp_path / "out"
    gate.export_ref(git_repo, "HEAD", out, _deadline())
    assert (out / ".gitattributes").is_file()
    assert (out / "link").is_symlink()
    assert (out / "link").read_text(encoding="utf-8") == "x"


def test_export_ref_deletes_repository_scanner_config(git_repo: Path, tmp_path: Path) -> None:
    """The catalog does not trust these, so the local score must not either."""
    for name in gate.REPOSITORY_CONFIG_FILES:
        (git_repo / name).write_text('[scanner]\nignore_paths = ["**"]\n', encoding="utf-8")
        _git(git_repo, "add", name)
    _git(git_repo, "commit", "-q", "-m", "config")
    out = tmp_path / "out"
    gate.export_ref(git_repo, "HEAD", out, _deadline())
    assert (out / "tracked.txt").is_file()
    for name in gate.REPOSITORY_CONFIG_FILES:
        assert not (out / name).exists()


def test_export_ref_reads_the_named_ref(git_repo: Path, tmp_path: Path) -> None:
    _git(git_repo, "tag", "first")
    (git_repo / "later.txt").write_text("z", encoding="utf-8")
    _git(git_repo, "add", "later.txt")
    _git(git_repo, "commit", "-q", "-m", "later")
    out = tmp_path / "out"
    gate.export_ref(git_repo, "first", out, _deadline())
    assert (out / "tracked.txt").is_file()
    assert not (out / "later.txt").exists()


def test_export_timeout_is_external_error(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(args: list[str]) -> None:
        if args[1] == "read-tree":
            raise subprocess.TimeoutExpired(args, 1)

    _patch_run(monkeypatch, fake)
    assert gate.main([]) == 3


def test_failed_tree_write_is_external_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_run(
        monkeypatch,
        lambda args: _done(args, 128, b"disk full") if args[1] == "checkout-index" else None,
    )
    assert gate.main([]) == 3
    assert "cannot write the tree of 'HEAD': disk full" in capsys.readouterr().err


def test_summarize_tolerates_missing_categories() -> None:
    assert gate.summarize({"score": 90}) == (90, 0, [])


def test_summarize_skips_malformed_entries() -> None:
    report = {"score": 70, "categories": ["junk", {"name": "c", "checks": ["junk"]}]}
    assert gate.summarize(report) == (70, 0, [])


def test_summarize_rejects_a_missing_score() -> None:
    with pytest.raises(gate.GateError) as exc:
        gate.summarize({})
    assert exc.value.exit_code == 3


def test_scanner_project_lock_pins_the_action_wheel() -> None:
    """The local lock must carry the wheel hash the CI action verifies.

    A Renovate bump of the action SHA, or a re-lock of build/plugin-scanner,
    fails here until both sides name the same scanner, so the local score
    cannot drift from the CI and catalog score unnoticed.
    """
    lock = (REPO_ROOT / gate.SCANNER_PROJECT / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "plugin-scanner"\nversion = "3.57.0"' in lock
    assert "408b302ca427fc8b7bc0b54164f85e9d57d45714d24bafe1a2e6bef7353558fa" in lock
    # The cooldown waiver is a dated cutoff, never `false`, so later scanner
    # releases stay under the 7-day exclude-newer cooldown.
    assert 'plugin-scanner = "2026-10-26T00:00:00Z"' in lock
    assert "plugin-scanner = false" not in lock
    workflow = (REPO_ROOT / ".github" / "workflows" / "plugin-scanner.yml").read_text(
        encoding="utf-8"
    )
    assert "ai-plugin-scanner-action@c96833de5070fab4e564010b5ab6e3c3d7e07a3e" in workflow
    assert "min_score: 80" in workflow
