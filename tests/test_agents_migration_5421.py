"""Verify the issue #5421 migration manifest against repository state.

Issue #5421 gave every tracked ``.agents/**`` file at the post-#5420 baseline
exactly one disposition. The manifest is temporary migration evidence. Delete
this module together with the manifest once the migration has settled.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / ".project-toolkit" / "analysis" / "5421-agents-migration-manifest.json"
DISPOSITIONS = frozenset(
    {"MOVE", "RETAIN_CANONICAL", "RETAIN_HISTORY", "DELETE_OBSOLETE", "REHOME_CANONICAL"}
)
RELOCATIONS = frozenset({"MOVE", "REHOME_CANONICAL"})
RETAINED = frozenset({"RETAIN_CANONICAL", "RETAIN_HISTORY"})


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entries(manifest: dict) -> list[dict]:
    return manifest["entries"]


@pytest.fixture(scope="module")
def tracked() -> frozenset[str]:
    result = _git("ls-files", "-z")
    assert result.returncode == 0, result.stderr
    return frozenset(filter(None, result.stdout.split("\0")))


@pytest.fixture(scope="module")
def baseline_paths(manifest: dict) -> frozenset[str]:
    sha = manifest["baseline_sha"]
    if _git("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
        pytest.skip(f"baseline commit {sha} is not in this clone")
    result = _git("ls-tree", "-r", "--name-only", "-z", sha, "--", ".agents")
    assert result.returncode == 0, result.stderr
    return frozenset(filter(None, result.stdout.split("\0")))


def test_accounting_balances(manifest: dict, entries: list[dict]) -> None:
    counts = Counter(entry["disposition"] for entry in entries)
    assert sum(counts.values()) == manifest["baseline_file_count"] == len(entries)
    assert dict(counts) == manifest["disposition_counts"]


def test_every_entry_has_one_known_disposition(entries: list[dict]) -> None:
    paths = [entry["old_path"] for entry in entries]
    assert len(paths) == len(set(paths))
    unknown = [entry["old_path"] for entry in entries if entry["disposition"] not in DISPOSITIONS]
    assert unknown == []


def test_every_entry_documents_rationale_and_owner(entries: list[dict]) -> None:
    missing = [
        entry["old_path"]
        for entry in entries
        if not entry.get("rationale") or not entry.get("owner") or "consumers" not in entry
    ]
    assert missing == []


def test_manifest_covers_exactly_the_baseline(
    entries: list[dict], baseline_paths: frozenset[str]
) -> None:
    assert {entry["old_path"] for entry in entries} == baseline_paths


def test_moves_preserve_relative_paths(entries: list[dict]) -> None:
    wrong = [
        entry["old_path"]
        for entry in entries
        if entry["disposition"] == "MOVE"
        and entry.get("new_path") != ".project-toolkit/" + entry["old_path"][len(".agents/") :]
    ]
    assert wrong == []


def test_relocated_sources_are_gone_and_destinations_exist(
    entries: list[dict], tracked: frozenset[str]
) -> None:
    for entry in entries:
        if entry["disposition"] in RELOCATIONS:
            assert entry["old_path"] not in tracked, entry["old_path"]
            assert entry["new_path"] in tracked, entry["new_path"]


def test_deleted_sources_are_gone(entries: list[dict], tracked: frozenset[str]) -> None:
    present = [
        entry["old_path"]
        for entry in entries
        if entry["disposition"] == "DELETE_OBSOLETE" and entry["old_path"] in tracked
    ]
    assert present == []


def test_retained_sources_still_exist(entries: list[dict], tracked: frozenset[str]) -> None:
    missing = [
        entry["old_path"]
        for entry in entries
        if entry["disposition"] in RETAINED and entry["old_path"] not in tracked
    ]
    assert missing == []


def test_no_destination_collided_with_a_baseline_file(
    manifest: dict, entries: list[dict], baseline_paths: frozenset[str]
) -> None:
    sha = manifest["baseline_sha"]
    collisions = [
        entry["new_path"]
        for entry in entries
        if entry["disposition"] in RELOCATIONS
        and _git("cat-file", "-e", f"{sha}:{entry['new_path']}").returncode == 0
    ]
    assert collisions == []


def test_no_moved_subtree_remains_under_agents(
    entries: list[dict], tracked: frozenset[str]
) -> None:
    moved_dirs = {
        "/".join(entry["old_path"].split("/")[:2]) + "/"
        for entry in entries
        if entry["disposition"] == "MOVE" and entry["old_path"].count("/") > 1
    }
    leftovers = sorted(path for path in tracked if path.startswith(tuple(moved_dirs)))
    assert leftovers == []
