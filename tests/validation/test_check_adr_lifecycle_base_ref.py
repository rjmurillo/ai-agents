"""Base-ref provenance for the committed ADR lifecycle baseline (issue #5270).

A branch that hand-edits ``adr_lifecycle_baseline.json`` to add a violation,
without ever running ``--write-baseline``, must fail a plain run. The ceiling
is compared with its value at the fork point, not with how it was written.
The comparison is by record path, so moving a recorded violation to another
record also fails (issue #5273).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_adr_lifecycle import CHECKS, EXIT_CONFIG, EXIT_OK, EXIT_REGRESSION, main

_BAD_FRONTMATTER = "---\nid: ADR-002\nstatus: [unclosed\n---\n\n# ADR-002: Bad\n"
_GOOD = (
    "---\nid: ADR-001\nstatus: accepted\ndate: 2026-08-21\nsupersedes: []\n"
    "superseded-by: null\nimplemented: true\n---\n\n# ADR-001: Thing\n\n"
    "## Status\n\nAccepted (2026-08-21). Conditions were cleared in review.\n\n"
    "## Context\n\nWhy.\n\n## Decision\n\nWhat.\n\n## Consequences\n\nSo.\n"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


_BAD_PATH = ".project-toolkit/architecture/ADR-002-bad.md"
_GOOD_PATH = ".project-toolkit/architecture/ADR-001-thing.md"


def _set_baseline(baseline: Path, parse_count: int, path: str = _BAD_PATH) -> None:
    """Record ``parse_count`` frontmatter-parses violations against ``path``."""
    violations: dict[str, dict[str, int]] = {name: {} for name in CHECKS}
    if parse_count:
        violations["frontmatter-parses"] = {path: parse_count}
    baseline.write_text(
        json.dumps({"schema_version": "2", "violations": violations}), encoding="utf-8"
    )


def _set_legacy_baseline(baseline: Path, parse_count: int) -> None:
    """The schema 1 shape: one count per check, no record paths."""
    counts = {name: 0 for name in CHECKS}
    counts["frontmatter-parses"] = parse_count
    baseline.write_text(json.dumps({"schema_version": "1", "counts": counts}), encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _repo(tmp_path: Path, parse_count: int | None = 0) -> tuple[Path, Path]:
    """A repo whose main commit holds one clean ADR and, optionally, a baseline."""
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-thing.md").write_text(_GOOD, encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    if parse_count is not None:
        _set_baseline(baseline, parse_count)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, "base")
    return adr_dir, baseline


def _plain_run(repo: Path, baseline: Path) -> int:
    return main(["--repo-root", str(repo), "--baseline", str(baseline)])


def test_hand_edited_raise_of_the_baseline_fails_a_plain_run(tmp_path, capsys):
    adr_dir, baseline = _repo(tmp_path)
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (adr_dir / "ADR-002-bad.md").write_text(_BAD_FRONTMATTER, encoding="utf-8")
    _set_baseline(baseline, 1)
    _commit(tmp_path, "regress and raise the ceiling by hand")

    assert _plain_run(tmp_path, baseline) == EXIT_REGRESSION
    assert "frontmatter-parses" in capsys.readouterr().err


def test_uncommitted_hand_edit_also_fails(tmp_path):
    adr_dir, baseline = _repo(tmp_path)
    (adr_dir / "ADR-002-bad.md").write_text(_BAD_FRONTMATTER, encoding="utf-8")
    _set_baseline(baseline, 1)

    assert _plain_run(tmp_path, baseline) == EXIT_REGRESSION


def test_unchanged_baseline_passes(tmp_path):
    _, baseline = _repo(tmp_path)

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_lowered_baseline_passes(tmp_path):
    _, baseline = _repo(tmp_path, parse_count=2)
    _set_baseline(baseline, 0)

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_bootstrap_passes_when_the_base_ref_has_no_baseline(tmp_path):
    _, baseline = _repo(tmp_path, parse_count=None)
    _set_baseline(baseline, 5)

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_baseline_outside_the_repo_skips_the_comparison(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo(repo)
    outside = tmp_path / "outside.json"
    _set_baseline(outside, 9)

    assert _plain_run(repo, outside) == EXIT_OK


def test_stale_branch_is_not_blamed_for_a_baseline_main_lowered_later(tmp_path):
    _, baseline = _repo(tmp_path, parse_count=3)
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    _git(tmp_path, "checkout", "-q", "main")
    _set_baseline(baseline, 0)
    _commit(tmp_path, "main lowers the ceiling after the branch forked")
    _git(tmp_path, "checkout", "-q", "feature")

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_unreadable_baseline_at_the_base_ref_is_a_config_error(tmp_path, capsys):
    _, baseline = _repo(tmp_path)
    baseline.write_text("not json", encoding="utf-8")
    _commit(tmp_path, "corrupt the base baseline")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    _set_baseline(baseline, 0)

    assert _plain_run(tmp_path, baseline) == EXIT_CONFIG
    assert "could not read the baseline" in capsys.readouterr().err


def test_no_resolvable_base_ref_skips_the_comparison(tmp_path):
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-thing.md").write_text(_GOOD, encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    _set_baseline(baseline, 0)

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_missing_merge_base_is_a_config_error_not_a_tip_comparison(tmp_path, capsys):
    _, baseline = _repo(tmp_path, parse_count=3)
    _git(tmp_path, "checkout", "-q", "--orphan", "unrelated")
    _set_baseline(baseline, 3)
    _commit(tmp_path, "history with no shared ancestor")
    _git(tmp_path, "checkout", "-q", "main")
    _set_baseline(baseline, 0)
    _commit(tmp_path, "main lowers the ceiling")
    _git(tmp_path, "checkout", "-q", "unrelated")

    assert _plain_run(tmp_path, baseline) == EXIT_CONFIG
    assert "no merge base" in capsys.readouterr().err


def test_exported_git_dir_of_another_checkout_does_not_redirect_the_fork_point(
    tmp_path, monkeypatch
):
    other = tmp_path / "other"
    other.mkdir()
    _repo(other, parse_count=1)
    repo = tmp_path / "repo"
    repo.mkdir()
    adr_dir, baseline = _repo(repo)
    (adr_dir / "ADR-002-bad.md").write_text(_BAD_FRONTMATTER, encoding="utf-8")
    _set_baseline(baseline, 1)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))

    assert _plain_run(repo, baseline) == EXIT_REGRESSION


def test_moving_a_recorded_violation_to_another_record_fails(tmp_path, capsys):
    """Issue #5273: the base ref records ADR-001; the branch fixes it and breaks ADR-002."""
    adr_dir, baseline = _repo(tmp_path, parse_count=0)
    (adr_dir / "ADR-001-thing.md").write_text(_BAD_FRONTMATTER.replace("002", "001"), "utf-8")
    _set_baseline(baseline, 1, _GOOD_PATH)
    _commit(tmp_path, "base records ADR-001 as the known violation")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (adr_dir / "ADR-001-thing.md").write_text(_GOOD, encoding="utf-8")
    (adr_dir / "ADR-002-bad.md").write_text(_BAD_FRONTMATTER, encoding="utf-8")
    _set_baseline(baseline, 1, _BAD_PATH)

    assert _plain_run(tmp_path, baseline) == EXIT_REGRESSION
    assert "frontmatter-parses" in capsys.readouterr().err


def test_schema_1_baseline_at_zero_on_the_base_ref_is_accepted(tmp_path):
    """The pull request that introduces schema 2 forks from a schema 1 file."""
    _, baseline = _repo(tmp_path, parse_count=None)
    _set_legacy_baseline(baseline, 0)
    _commit(tmp_path, "base still on schema 1")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    _set_baseline(baseline, 0)

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_schema_1_baseline_with_debt_on_the_base_ref_is_a_config_error(tmp_path, capsys):
    """A nonzero count names no records, so it cannot seed an identity comparison."""
    _, baseline = _repo(tmp_path, parse_count=None)
    _set_legacy_baseline(baseline, 2)
    _commit(tmp_path, "base on schema 1 with recorded debt")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    _set_baseline(baseline, 0)

    assert _plain_run(tmp_path, baseline) == EXIT_CONFIG
    assert "could not read the baseline" in capsys.readouterr().err


def _without_check(baseline: Path, name: str) -> None:
    """Drop ``name`` from a schema 2 baseline, as a base ref predating that check would."""
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    del payload["violations"][name]
    baseline.write_text(json.dumps(payload), encoding="utf-8")


def test_a_check_the_base_ref_baseline_lacks_does_not_fail_the_branch_adding_it(tmp_path):
    adr_dir, baseline = _repo(tmp_path)
    _without_check(baseline, "cited-paths-exist")
    _commit(tmp_path, "base baseline predates cited-paths-exist")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (adr_dir / "ADR-002-stale.md").write_text(
        _GOOD.replace("ADR-001", "ADR-002").replace(
            "## Decision\n\nWhat.\n",
            "## Decision\n\nRun `scripts/gone.py`.\n",
        ),
        encoding="utf-8",
    )
    _set_baseline(baseline, 0)
    payload = json.loads(baseline.read_text(encoding="utf-8"))
    payload["violations"]["cited-paths-exist"] = {
        ".project-toolkit/architecture/ADR-002-stale.md": 1
    }
    baseline.write_text(json.dumps(payload), encoding="utf-8")
    _commit(tmp_path, "add the check and record its one violation")

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_a_missing_check_at_the_base_ref_still_guards_the_checks_it_names(tmp_path, capsys):
    adr_dir, baseline = _repo(tmp_path)
    _without_check(baseline, "cited-paths-exist")
    _commit(tmp_path, "base baseline predates cited-paths-exist")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (adr_dir / "ADR-002-bad.md").write_text(_BAD_FRONTMATTER, encoding="utf-8")
    _set_baseline(baseline, 1)
    _commit(tmp_path, "raise an existing check by hand")

    assert _plain_run(tmp_path, baseline) == EXIT_REGRESSION
    assert "frontmatter-parses" in capsys.readouterr().err


def test_a_live_baseline_missing_a_check_is_still_refused(tmp_path):
    _, baseline = _repo(tmp_path)
    _without_check(baseline, "cited-paths-exist")

    assert _plain_run(tmp_path, baseline) == EXIT_CONFIG


def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    """Create a symlink, or skip where the platform denies it (Windows without elevation)."""
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")


def _symlink_baseline_to(baseline: Path, target: Path) -> None:
    """Replace the repo baseline with a symlink to ``target``."""
    baseline.unlink()
    _symlink_or_skip(baseline, target)


def test_symlinked_baseline_pointing_outside_the_repo_is_refused(tmp_path, capsys):
    """Issue #6506: a symlink out of the repo must not switch off the base-ref check."""
    repo = tmp_path / "repo"
    repo.mkdir()
    adr_dir, baseline = _repo(repo)
    _git(repo, "checkout", "-q", "-b", "feature")
    (adr_dir / "ADR-002-bad.md").write_text(_BAD_FRONTMATTER, encoding="utf-8")
    outside = tmp_path / "outside.json"
    _set_baseline(outside, 1)
    _symlink_baseline_to(baseline, outside)
    _commit(repo, "regress and hide the raised ceiling behind a symlink")

    assert _plain_run(repo, baseline) == EXIT_CONFIG
    err = capsys.readouterr().err
    assert "symlink" in err
    assert "[CONFIG]" in err


def test_symlinked_baseline_pointing_inside_the_repo_is_refused(tmp_path, capsys):
    adr_dir, baseline = _repo(tmp_path)
    real = tmp_path / "real-baseline.json"
    _set_baseline(real, 0)
    _symlink_baseline_to(baseline, real)
    _commit(tmp_path, "point the baseline at another tracked file")

    assert _plain_run(tmp_path, baseline) == EXIT_CONFIG
    assert "symlink" in capsys.readouterr().err


def test_baseline_under_a_symlinked_directory_is_refused(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo(repo)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    _set_baseline(outside_dir / "baseline.json", 0)
    _symlink_or_skip(repo / "linked", outside_dir, directory=True)

    assert _plain_run(repo, repo / "linked" / "baseline.json") == EXIT_CONFIG
    assert "linked" in capsys.readouterr().err


def test_write_baseline_through_a_symlink_is_refused(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _, baseline = _repo(repo)
    outside = tmp_path / "outside.json"
    _set_baseline(outside, 0)
    _symlink_baseline_to(baseline, outside)

    code = main(["--repo-root", str(repo), "--baseline", str(baseline), "--write-baseline"])

    assert code == EXIT_CONFIG
    assert "symlink" in capsys.readouterr().err


def test_regular_baseline_file_is_still_accepted(tmp_path):
    """Control for the symlink refusals: the same layout without the link passes."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _, baseline = _repo(repo)

    assert not baseline.is_symlink()
    assert _plain_run(repo, baseline) == EXIT_OK


def test_dotdot_segment_does_not_hide_a_symlinked_directory(tmp_path, capsys):
    """``repo/linked/../baseline.json`` is opened through ``linked``, so it must be walked."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo(repo)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    _symlink_or_skip(repo / "linked", outside_dir, directory=True)

    assert _plain_run(repo, repo / "linked" / ".." / "baseline.json") == EXIT_CONFIG
    assert "linked" in capsys.readouterr().err


def test_resolved_root_with_a_baseline_reached_through_a_symlinked_parent_is_walked(
    tmp_path, capsys
):
    """``main`` builds a resolved root and an unresolved baseline; the forms must still line up."""
    real = tmp_path / "real"
    real.mkdir()
    repo = real / "repo"
    repo.mkdir()
    _, baseline = _repo(repo)
    outside = tmp_path / "outside.json"
    _set_baseline(outside, 0)
    _symlink_baseline_to(baseline, outside)
    alias = tmp_path / "alias"
    _symlink_or_skip(alias, real, directory=True)

    code = main(["--repo-root", str(repo), "--baseline", str(alias / "repo" / "baseline.json")])

    assert code == EXIT_CONFIG
    assert "symlink" in capsys.readouterr().err


def test_resolved_root_with_a_regular_baseline_through_a_symlinked_parent_is_accepted(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    repo = real / "repo"
    repo.mkdir()
    _repo(repo)
    alias = tmp_path / "alias"
    _symlink_or_skip(alias, real, directory=True)

    code = main(["--repo-root", str(repo), "--baseline", str(alias / "repo" / "baseline.json")])

    assert code == EXIT_OK
