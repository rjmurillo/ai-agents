#!/usr/bin/env python3
"""The security-review gate accepts a clean merge of main above the marker (issue #6509).

``detect_infrastructure.py`` reimplements the merge rule of
``validate_review_marker.py`` because a skill cannot import a sibling skill's
script. The conformance test below builds one table of real histories and fails
when the two implementations disagree on any of them.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

from tests.validation._main_merge_repo import (
    BASE_REF,
    BRANCH,
    advance_main,
    git,
    reviewed_branch,
    sync_with_main,
    write_commit,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCES_DIR = REPO_ROOT / ".claude" / "skills" / "review" / "references"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validation" / "validate_review_marker.py"

mod = import_skill_script(
    ".claude/skills/security-detection/detect_infrastructure.py",
    module_name="detect_infrastructure_main_merge_under_test",
)


def _load_validator():
    spec = importlib.util.spec_from_file_location("vrm_for_main_merge", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vrm = _load_validator()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    reviewed_branch(tmp_path)
    return tmp_path


def _clean_sync(repo: Path) -> None:
    advance_main(repo)
    sync_with_main(repo)


def _two_syncs(repo: Path) -> None:
    advance_main(repo, "one.txt")
    sync_with_main(repo)
    advance_main(repo, "two.txt")
    sync_with_main(repo)


def _conflict_resolved(repo: Path) -> None:
    advance_main(repo, "feature.txt", "main version\n")
    git(repo, "merge", "--no-edit", BASE_REF, check=False)
    (repo / "feature.txt").write_text("hand resolved\n", encoding="utf-8")
    git(repo, "add", "feature.txt")
    git(repo, "commit", "-q", "--no-edit")


def _extra_edit(repo: Path) -> None:
    advance_main(repo)
    git(repo, "merge", "-q", "--no-commit", "--no-ff", BASE_REF)
    (repo / "smuggled.txt").write_text("unreviewed\n", encoding="utf-8")
    git(repo, "add", "smuggled.txt")
    git(repo, "commit", "-q", "-m", "merge main")


def _ours(repo: Path) -> None:
    advance_main(repo)
    git(repo, "merge", "-q", "-s", "ours", "--no-edit", BASE_REF)


def _side_branch(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "side", "main")
    write_commit(repo, "side.txt", "side\n")
    git(repo, "checkout", "-q", BRANCH)
    git(repo, "merge", "-q", "--no-edit", "side")


def _code_after_marker(repo: Path) -> None:
    write_commit(repo, "late.txt", "unreviewed\n")
    _clean_sync(repo)


def _no_base_ref(repo: Path) -> None:
    advance_main(repo)
    sync_with_main(repo)
    git(repo, "update-ref", "-d", f"refs/remotes/{BASE_REF}")


def _marker_only(repo: Path) -> None:
    git(repo, "update-ref", "-d", f"refs/remotes/{BASE_REF}")


HISTORIES: list[tuple[str, Callable[[Path], None], bool]] = [
    ("clean sync", _clean_sync, True),
    ("two syncs", _two_syncs, True),
    ("marker alone, no base ref", _marker_only, True),
    ("conflict resolved by hand", _conflict_resolved, False),
    ("extra edit in the merge", _extra_edit, False),
    ("ours merge", _ours, False),
    ("merge of a side branch", _side_branch, False),
    ("code after the marker", _code_after_marker, False),
    ("base ref missing", _no_base_ref, False),
]


@pytest.mark.parametrize(("label", "build", "expected"), HISTORIES, ids=[h[0] for h in HISTORIES])
def test_detector_and_validator_agree_on_every_history(
    repo: Path, label: str, build: Callable[[Path], None], expected: bool
) -> None:
    build(repo)

    detector_ok, detail = mod.find_security_review_marker("HEAD", repo)
    validator = vrm.validate_ref("HEAD", repo, references_dir=REFERENCES_DIR)

    assert detector_ok is expected, f"{label}: {detail}"
    assert validator.ok is expected, f"{label}: {validator.message}"


def test_clean_sync_detail_names_the_merge(repo: Path) -> None:
    _clean_sync(repo)

    ok, detail = mod.find_security_review_marker("HEAD", repo)

    assert ok is True
    assert "below 1 clean merge(s) of origin/main" in detail


def test_rejected_merge_detail_says_why(repo: Path) -> None:
    _side_branch(repo)

    ok, detail = mod.find_security_review_marker("HEAD", repo)

    assert ok is False
    assert "2 parents" in detail
    assert "not on origin/main" in detail


def test_hop_cap_rejects_a_long_chain(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _two_syncs(repo)
    monkeypatch.setattr(mod, "MAX_MAIN_MERGE_HOPS", 1)

    ok, detail = mod.find_security_review_marker("HEAD", repo)

    assert ok is False
    assert "more than 1 merges" in detail


def test_custom_base_ref_is_honored(repo: Path) -> None:
    advance_main(repo)
    git(repo, "update-ref", "refs/remotes/upstream/trunk", "main")
    git(repo, "merge", "-q", "--no-edit", "upstream/trunk")
    git(repo, "update-ref", "-d", f"refs/remotes/{BASE_REF}")

    default_ok, _ = mod.find_security_review_marker("HEAD", repo)
    custom_ok, _ = mod.find_security_review_marker("HEAD", repo, "upstream/trunk")

    assert default_ok is False
    assert custom_ok is True


def test_option_like_base_ref_raises(repo: Path) -> None:
    with pytest.raises(mod.GitReadError, match="must not start with"):
        mod.find_security_review_marker("HEAD", repo, "--all")


def test_cli_passes_a_synced_critical_branch(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_sync(repo)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detect_infrastructure.py",
            "--files",
            ".github/workflows/ci.yml",
            "--require-security-review",
            "--repo-root",
            str(repo),
        ],
    )

    assert mod.main() == 0


def test_cli_blocks_a_critical_branch_with_a_side_merge(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _side_branch(repo)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "detect_infrastructure.py",
            "--files",
            ".github/workflows/ci.yml",
            "--require-security-review",
            "--repo-root",
            str(repo),
        ],
    )

    assert mod.main() == 1
