"""A clean merge of main above a review marker keeps the marker valid (issue #6509).

A marker is an empty commit on the reviewed tip. Syncing the branch with main
adds a merge commit above it, and the validator used to reject every merge tip,
so each sync forced a full re-review of code that did not change. The tip is
accepted only when it is a clean merge of the base ref: two parents, the second
reachable from the base ref, and a tree equal to what ``git merge-tree``
produces. Anything else (conflict edits, extra edits, another branch, new code
under the merge) still needs a fresh review.

Each test builds a real repository, because the rule is about commit shape and
a mock would encode the same assumption it is meant to check.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tests.validation._main_merge_repo import (
    BASE_REF,
    BRANCH,
    advance_main,
    git,
    reviewed_branch,
    sync_with_main,
    write_commit,
)
from tests.validation._review_artifact import commit_message, marker_message

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REFERENCES_DIR = REPO_ROOT / ".claude" / "skills" / "review" / "references"
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "validate_review_marker.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("vrm_main_merge", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vrm = _load_module()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    reviewed_branch(tmp_path)
    return tmp_path


def _validate(repo: Path, **kwargs):
    return vrm.validate_ref("HEAD", repo, references_dir=REFERENCES_DIR, **kwargs)


def test_clean_main_merge_above_marker_passes(repo: Path) -> None:
    advance_main(repo)
    sync_with_main(repo)

    outcome = _validate(repo)

    assert outcome.ok is True, outcome.message
    assert outcome.exit_code == 0
    assert "1 clean merge of origin/main" in outcome.message


def test_two_successive_syncs_pass(repo: Path) -> None:
    advance_main(repo, "one.txt")
    sync_with_main(repo)
    advance_main(repo, "two.txt")
    sync_with_main(repo)

    outcome = _validate(repo)

    assert outcome.ok is True, outcome.message
    assert "2 clean merges of origin/main" in outcome.message


def test_main_moving_again_after_the_sync_still_passes(repo: Path) -> None:
    advance_main(repo, "one.txt")
    sync_with_main(repo)
    advance_main(repo, "two.txt")

    assert _validate(repo).ok is True


def test_marker_alone_still_passes_without_a_base_ref(repo: Path) -> None:
    git(repo, "update-ref", "-d", f"refs/remotes/{BASE_REF}")

    assert _validate(repo).ok is True


def test_merge_with_conflict_resolution_is_rejected(repo: Path) -> None:
    advance_main(repo, "feature.txt", "main version\n")
    git(repo, "merge", "--no-edit", BASE_REF, check=False)
    (repo / "feature.txt").write_text("hand resolved\n", encoding="utf-8")
    git(repo, "add", "feature.txt")
    git(repo, "commit", "-q", "--no-edit")

    outcome = _validate(repo)

    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "conflict" in outcome.message


def test_merge_with_an_extra_edit_is_rejected(repo: Path) -> None:
    advance_main(repo)
    git(repo, "merge", "-q", "--no-commit", "--no-ff", BASE_REF)
    (repo / "smuggled.txt").write_text("unreviewed\n", encoding="utf-8")
    git(repo, "add", "smuggled.txt")
    git(repo, "commit", "-q", "-m", "merge main")

    outcome = _validate(repo)

    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "clean merge" in outcome.message


def test_ours_merge_that_drops_main_is_rejected(repo: Path) -> None:
    advance_main(repo)
    git(repo, "merge", "-q", "-s", "ours", "--no-edit", BASE_REF)

    outcome = _validate(repo)

    assert outcome.ok is False
    assert "clean merge" in outcome.message


def test_merge_of_a_branch_that_is_not_on_main_is_rejected(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "side", "main")
    write_commit(repo, "side.txt", "side\n")
    git(repo, "checkout", "-q", BRANCH)
    git(repo, "merge", "-q", "--no-edit", "side")

    outcome = _validate(repo)

    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "not on origin/main" in outcome.message


def test_code_landed_after_the_marker_then_merged_is_rejected(repo: Path) -> None:
    write_commit(repo, "late.txt", "reviewed? no\n")
    advance_main(repo)
    sync_with_main(repo)

    outcome = _validate(repo)

    assert outcome.ok is False
    assert outcome.exit_code == 1


def test_merge_above_a_marker_for_another_tip_is_rejected(tmp_path: Path) -> None:
    reviewed_branch(tmp_path)
    git(tmp_path, "reset", "-q", "--hard", "HEAD~1")
    commit_message(tmp_path, marker_message("analyst,security", "a" * 40))
    advance_main(tmp_path)
    sync_with_main(tmp_path)

    outcome = _validate(tmp_path)

    assert outcome.ok is False
    assert "does not bind" in outcome.message


def test_unresolvable_base_ref_rejects_a_merge_tip(repo: Path) -> None:
    advance_main(repo)
    sync_with_main(repo)

    outcome = _validate(repo, base_ref="origin/does-not-exist")

    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "origin/does-not-exist" in outcome.message


def test_octopus_merge_is_rejected(repo: Path) -> None:
    git(repo, "branch", "side-one", "main")
    git(repo, "branch", "side-two", "main")
    git(repo, "checkout", "-q", "side-one")
    write_commit(repo, "one.txt", "1\n")
    git(repo, "checkout", "-q", "side-two")
    write_commit(repo, "two.txt", "2\n")
    git(repo, "checkout", "-q", BRANCH)
    git(repo, "merge", "-q", "--no-edit", "side-one", "side-two")

    outcome = _validate(repo)

    assert outcome.ok is False
    assert "3 parents" in outcome.message


def test_walk_stops_at_the_hop_cap(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    advance_main(repo, "one.txt")
    sync_with_main(repo)
    advance_main(repo, "two.txt")
    sync_with_main(repo)
    monkeypatch.setattr(vrm, "MAX_MAIN_MERGE_HOPS", 1)

    outcome = _validate(repo)

    assert outcome.ok is False
    assert outcome.exit_code == 1
    assert "more than 1 merges" in outcome.message


def test_cli_accepts_a_custom_base_ref(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    advance_main(repo)
    git(repo, "update-ref", "refs/remotes/upstream/trunk", "main")
    git(repo, "merge", "-q", "--no-edit", "upstream/trunk")

    exit_code = vrm.main(
        [
            "--repo-root",
            str(repo),
            "--references-dir",
            str(REFERENCES_DIR),
            "--base-ref",
            "upstream/trunk",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    assert "upstream/trunk" in captured.out
