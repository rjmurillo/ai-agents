"""Axis-list validation for the ``/review`` marker (Issue #5113).

A marker's axis list must name only discovered axes, each once. A subset is
allowed because /review selects axes by change risk.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "validate_review_marker.py"
SELECT_AXES_PATH = REPO_ROOT / ".claude" / "skills" / "review" / "scripts" / "select_axes.py"
REFERENCES = REPO_ROOT / ".claude" / "skills" / "review" / "references"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vrm = _load("validate_review_marker_axes_under_test", SCRIPT_PATH)
KNOWN = frozenset({"analyst", "qa", "security", "correctness", "taste-lints"})


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "feat: initial commit")
    return repo


def _marker_commit(repo: Path, *values: str) -> None:
    tip = _git(repo, "rev-parse", "HEAD")
    args = ["commit", "-q", "--allow-empty", "-m", "review: /review PASS marker"]
    for value in values:
        args += ["--trailer", f"Reviewed-By: /review@{value} on {tip}"]
    _git(repo, *args)


def test_check_axes_accepts_subset() -> None:
    assert vrm.check_axes(("analyst", "qa"), KNOWN) is None


def test_check_axes_accepts_full_set() -> None:
    assert vrm.check_axes(tuple(sorted(KNOWN)), KNOWN) is None


def test_check_axes_rejects_unknown_name() -> None:
    reason = vrm.check_axes(("analyst", "code-review"), KNOWN)
    assert reason == "unknown axis name(s): code-review"


def test_check_axes_lists_every_unknown_name_sorted() -> None:
    reason = vrm.check_axes(("zeta", "analyst", "alpha"), KNOWN)
    assert reason == "unknown axis name(s): alpha, zeta"


def test_check_axes_rejects_duplicate() -> None:
    reason = vrm.check_axes(("analyst", "analyst", "qa"), KNOWN)
    assert reason == "axis named more than once: analyst"


def test_check_axes_rejects_literal_all() -> None:
    assert vrm.check_axes(("all",), KNOWN) is not None


def test_discover_known_axes_reads_reference_stems(tmp_path: Path) -> None:
    (tmp_path / "alpha.md").write_text("x", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    known = vrm.discover_known_axes(tmp_path)
    assert "alpha" in known
    assert "notes" not in known
    assert set(vrm.LOCAL_AXES) <= known
    assert "correctness" in known


def test_discover_known_axes_covers_the_real_review_skill() -> None:
    known = vrm.discover_known_axes(REFERENCES)
    assert {"analyst", "security", "spec-compliance", "code-quality"} <= known


def test_local_axes_match_select_axes() -> None:
    select_axes = _load("select_axes_under_test_5113", SELECT_AXES_PATH)
    assert vrm.LOCAL_AXES == select_axes.LOCAL_AXES


def test_find_references_dir_is_none_for_canonical_copy() -> None:
    """The canonical copy has no skill sibling; its caller passes --references-dir."""
    assert vrm.find_references_dir() is None


def test_find_references_dir_finds_sibling_of_installed_copy(tmp_path: Path) -> None:
    skill = tmp_path / "skills" / "review"
    (skill / "scripts").mkdir(parents=True)
    (skill / "references").mkdir()
    installed = skill / "scripts" / "validate_review_marker.py"
    installed.write_text(SCRIPT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    module = _load("installed_copy_under_test_5113", installed)
    assert module.find_references_dir() == (skill / "references").resolve()


def test_default_known_axes_none_for_missing_dir(tmp_path: Path) -> None:
    assert vrm.default_known_axes(tmp_path / "nope") is None


def test_default_known_axes_reads_explicit_dir() -> None:
    assert "analyst" in vrm.default_known_axes(REFERENCES)


def test_validate_ref_rejects_unknown_axis(git_repo: Path) -> None:
    _marker_commit(git_repo, "analyst,code-review")
    outcome = vrm.validate_ref("HEAD", git_repo, KNOWN)
    assert not outcome.ok
    assert outcome.exit_code == 1
    assert "code-review" in outcome.message


def test_validate_ref_rejects_duplicate_axis(git_repo: Path) -> None:
    _marker_commit(git_repo, "analyst,analyst,qa")
    outcome = vrm.validate_ref("HEAD", git_repo, KNOWN)
    assert outcome.exit_code == 1
    assert "more than once" in outcome.message


def test_validate_ref_accepts_subset(git_repo: Path) -> None:
    _marker_commit(git_repo, "analyst,correctness")
    outcome = vrm.validate_ref("HEAD", git_repo, KNOWN)
    assert outcome.ok
    assert outcome.exit_code == 0


def test_validate_ref_accepts_second_trailer_when_first_is_invalid(git_repo: Path) -> None:
    _marker_commit(git_repo, "bogus", "analyst")
    outcome = vrm.validate_ref("HEAD", git_repo, KNOWN)
    assert outcome.ok


def test_validate_ref_axes_come_from_references_dir(git_repo: Path) -> None:
    _marker_commit(git_repo, "analyst,security,correctness")
    assert vrm.validate_ref("HEAD", git_repo, references_dir=REFERENCES).ok


def test_validate_ref_references_dir_rejects_unknown_axis(git_repo: Path) -> None:
    _marker_commit(git_repo, "analyst,not-an-axis")
    outcome = vrm.validate_ref("HEAD", git_repo, references_dir=REFERENCES)
    assert outcome.exit_code == 1


def test_validate_ref_config_error_without_references_dir(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _marker_commit(git_repo, "analyst")
    monkeypatch.setattr(vrm, "find_references_dir", lambda: None)
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.exit_code == 2
    assert "references/" in outcome.message


def test_default_known_axes_is_none_for_empty_references_dir(tmp_path: Path) -> None:
    empty = tmp_path / "references"
    empty.mkdir()
    (empty / "notes.txt").write_text("not a prompt\n", encoding="utf-8")
    assert vrm.default_known_axes(empty) is None


def test_validate_ref_config_error_for_empty_references_dir(
    git_repo: Path, tmp_path: Path
) -> None:
    """A forged /review@correctness must not pass when every axis prompt is absent."""
    empty = tmp_path / "references"
    empty.mkdir()
    _marker_commit(git_repo, "correctness")
    outcome = vrm.validate_ref("HEAD", git_repo, references_dir=empty)
    assert outcome.exit_code == 2
    assert "references/" in outcome.message


def test_main_exit_2_for_empty_references_dir(git_repo: Path, tmp_path: Path) -> None:
    empty = tmp_path / "references"
    empty.mkdir()
    _marker_commit(git_repo, "correctness")
    code = vrm.main(["--repo-root", str(git_repo), "--references-dir", str(empty)])
    assert code == 2


def test_validate_ref_stale_marker_wins_over_missing_references(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A marker naming another SHA is exit 1 even with no axis directory."""
    monkeypatch.setattr(vrm, "find_references_dir", lambda: None)
    _git(git_repo, "commit", "-q", "--allow-empty", "-m", "review: marker", "--trailer",
         f"Reviewed-By: /review@analyst on {'b' * 40}")
    outcome = vrm.validate_ref("HEAD", git_repo)
    assert outcome.exit_code == 1
    assert "does not bind" in outcome.message


def test_main_exit_2_for_bad_references_dir(
    git_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _marker_commit(git_repo, "analyst")
    code = vrm.main(
        ["--repo-root", str(git_repo), "--references-dir", str(tmp_path / "missing")]
    )
    assert code == 2


def test_main_passes_with_references_dir(
    git_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _marker_commit(git_repo, "analyst,correctness")
    code = vrm.main(["--repo-root", str(git_repo), "--references-dir", str(REFERENCES)])
    assert code == 0
    assert "reviewed:" in capsys.readouterr().out


def test_main_exit_1_for_unknown_axis(
    git_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _marker_commit(git_repo, "analyst,bogus")
    code = vrm.main(["--repo-root", str(git_repo), "--references-dir", str(REFERENCES)])
    assert code == 1
    assert "bogus" in capsys.readouterr().err


def test_wrong_sha_still_reports_binding_failure(git_repo: Path) -> None:
    _git(git_repo, "commit", "-q", "--allow-empty", "-m", "review: marker", "--trailer",
         f"Reviewed-By: /review@bogus on {'a' * 40}")
    outcome = vrm.validate_ref("HEAD", git_repo, KNOWN)
    assert outcome.exit_code == 1
    assert "does not bind" in outcome.message


def test_check_axes_scales_linearly_on_a_forged_long_list() -> None:
    """A 20,000-name trailer must not stall the ship gate."""
    import time

    axes = ("analyst",) * 20_000
    start = time.monotonic()
    reason = vrm.check_axes(axes, KNOWN)
    assert reason == "axis named more than once: analyst"
    assert time.monotonic() - start < 1.0
