"""A ratchet cannot reset itself by renaming its script or leaving the registry.

The fork's registry is read through ``git show``. Each case drives a real git
repository whose fork commit carries a registry file, then changes only the
branch-side registry (patched into ``branch_registry``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.ci import base_derived_ratchet as brd
from scripts.ci import merge_tree_ratchet_check as mtc
from scripts.ci import ratchet_registry_at_ref as rr
from tests.ci.test_base_derived_ratchet import MARKER, _branch, _git, _init, _run
from tests.ci.test_merge_tree_ratchet_check import (
    _branch_with_counts,
    _commit_all,
    _make_repo_with_baselines,
    _tree_counters,
)
from tests.ci.test_merge_tree_ratchet_check import _git as _git_cp

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

LABEL = "fake ratchet"
FORK_REGISTRY = f'RATCHETS = (_base_derived("{LABEL}", marker_ratchet),)\n'


def _commit_registry(repo: Path, text: str) -> None:
    path = repo / rr.REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    module = repo / "scripts/ci/marker_ratchet.py"
    module.write_text(f'_SCRIPT = "{MARKER}"\n', encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "registry")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = _init(tmp_path / "repo", 10)
    _commit_registry(root, FORK_REGISTRY)
    return root


def _branch_registry(monkeypatch: pytest.MonkeyPatch, entries: dict[str, str]) -> None:
    monkeypatch.setattr(brd, "branch_registry", lambda: entries, raising=False)


def test_unchanged_label_still_compares_counts(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _branch(repo, 12)
    _branch_registry(monkeypatch, {LABEL: MARKER})
    assert _run(repo, label=LABEL) == brd.EXIT_REGRESSION


def test_unchanged_label_at_the_fork_count_passes(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _branch(repo, 10)
    _branch_registry(monkeypatch, {LABEL: MARKER})
    assert _run(repo, label=LABEL) == brd.EXIT_OK


def test_a_moved_script_with_the_label_kept_fails(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    moved = "scripts/ci/renamed_ratchet.py"
    _branch(repo, 99)
    _branch_registry(monkeypatch, {LABEL: moved})
    assert _run(repo, label=LABEL, introduced_by=moved) == brd.EXIT_REGRESSION
    err = capsys.readouterr().err
    assert f"{LABEL}: RATCHET SCRIPT MOVED" in err
    assert MARKER in err
    assert moved in err


def test_a_removed_label_fails(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _branch(repo, 99)
    _branch_registry(monkeypatch, {})
    assert _run(repo, label=LABEL) == brd.EXIT_REGRESSION
    assert f"{LABEL}: RATCHET REMOVED" in capsys.readouterr().err


def test_a_label_absent_at_the_fork_still_bootstraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _init(tmp_path / "repo", 10, marker=False)
    _commit_registry(root, 'RATCHETS = (_base_derived("other ratchet", marker_ratchet),)\n')
    (root / MARKER).unlink(missing_ok=True)
    _branch(root, 99)
    _branch_registry(monkeypatch, {"other ratchet": MARKER, LABEL: "scripts/ci/new_ratchet.py"})
    assert _run(root, label=LABEL, introduced_by="scripts/ci/new_ratchet.py") == brd.EXIT_OK
    assert "bootstrap" in capsys.readouterr().out


def test_an_unparseable_fork_registry_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _init(tmp_path / "repo", 10)
    _commit_registry(root, "def broken(:\n")
    _branch(root, 10)
    _branch_registry(monkeypatch, {LABEL: MARKER})
    assert _run(root, label=LABEL) == brd.EXIT_EXTERNAL
    assert "REGISTRY UNREADABLE" in capsys.readouterr().err


def test_the_fork_is_read_from_git_not_the_working_tree(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _branch(repo, 10)
    (repo / rr.REGISTRY_PATH).write_text("RATCHETS = ()\n", encoding="utf-8")
    _branch_registry(monkeypatch, {})
    assert rr.registry_labels_at(repo, "main") == {LABEL: MARKER}


def test_both_registry_shapes_and_missing_script_info_parse(repo: Path) -> None:
    text = (
        'RATCHETS = (MergeTreeRatchet("a", "b.txt", mod, "scripts/ci/a.py"),'
        ' MergeTreeRatchet("old", "o.txt", mod),)\n'
    )
    _commit_registry(repo, text)
    assert rr.registry_labels_at(repo, "HEAD") == {"a": "scripts/ci/a.py", "old": None}


def test_a_commit_without_a_registry_file_holds_an_empty_registry(tmp_path: Path) -> None:
    root = _init(tmp_path / "repo", 10)
    assert rr.registry_labels_at(root, "main") == {}


def test_drift_ignores_a_fork_entry_with_no_recorded_script() -> None:
    assert rr.registry_drift({"old": None}, {"old": "scripts/ci/x.py"}) == []


# merge-tree runner -------------------------------------------------------------

MT_LABELS = (
    "ruff count ratchet",
    "taste count ratchet",
    "type-ignore count ratchet",
    "memory-index count ratchet",
)
MT_SCRIPTS = {
    "ruff count ratchet": "scripts/ci/ruff_count_ratchet.py",
    "taste count ratchet": "scripts/ci/taste_count_ratchet.py",
    "type-ignore count ratchet": "scripts/ci/type_ignore_count_ratchet.py",
    "memory-index count ratchet": "scripts/ci/memory_index_count_ratchet.py",
}


def _mt_repo(tmp_path: Path, *, drop: str | None = None) -> Path:
    repo = _make_repo_with_baselines(tmp_path, ruff=5, taste=10, ignore=10)
    calls = "".join(
        f'    MergeTreeRatchet("{label}", None, m, "{MT_SCRIPTS[label]}"),\n'
        for label in MT_LABELS
        if label != drop
    )
    (repo / rr.REGISTRY_PATH).write_text(f"RATCHETS = (\n{calls})\n", encoding="utf-8")
    if drop is not None:
        (repo / MT_SCRIPTS[drop]).unlink()
    _commit_all(repo, "registry")
    return repo


def _mt_run(repo: Path, monkeypatch: pytest.MonkeyPatch, entries: dict[str, str]) -> int:
    monkeypatch.setattr(brd, "branch_registry", lambda: entries)
    with _tree_counters():
        return mtc.main(["--repo-root", str(repo), "--base-ref", "main"])


def test_merge_tree_unchanged_registry_compares_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _mt_repo(tmp_path)
    _branch_with_counts(repo, ruff=50)
    assert _mt_run(repo, monkeypatch, dict(MT_SCRIPTS)) == mtc.EXIT_REGRESSION


def test_merge_tree_moved_script_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _mt_repo(tmp_path)
    _branch_with_counts(repo, ruff=6)
    entries = {**MT_SCRIPTS, "ruff count ratchet": "scripts/ci/ruff_renamed.py"}
    assert _mt_run(repo, monkeypatch, entries) == mtc.EXIT_REGRESSION
    assert "ruff count ratchet: RATCHET SCRIPT MOVED" in capsys.readouterr().err


def test_merge_tree_removed_label_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _mt_repo(tmp_path)
    _branch_with_counts(repo, ruff=6)
    entries = {k: v for k, v in MT_SCRIPTS.items() if k != "taste count ratchet"}
    assert _mt_run(repo, monkeypatch, entries) == mtc.EXIT_REGRESSION
    assert "taste count ratchet: RATCHET REMOVED" in capsys.readouterr().err


def test_merge_tree_label_absent_at_the_fork_still_bootstraps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _mt_repo(tmp_path, drop="ruff count ratchet")
    _branch_with_counts(repo, ruff=500)
    assert _git_cp(repo, "rev-parse", "--verify", "main").returncode == 0
    rc = _mt_run(repo, monkeypatch, dict(MT_SCRIPTS))
    assert "ruff count ratchet: bootstrap" in capsys.readouterr().out
    assert rc == mtc.EXIT_OK
