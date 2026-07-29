"""Regression guard for the ADR-089 removal of Tier 3 causal memory.

The removal deleted six canonical test files and their per-skill mirrors. The
tests that survive assert positive keys only, so a reintroduction of the causal
machinery, whether by a bad merge, a revert, or a generator that still carries
the old template, would pass unnoticed. These are the inverse assertions that
close that gap, per TESTING-RIGOR (positive, negative, edge).

Each test names the surface it guards, so a failure tells the reader which part
of the tier came back rather than only that something did.

Reintroducing the tier deliberately is allowed. It means superseding ADR-089
and deleting this file in the same change, which is the point: the removal
becomes a decision someone has to overturn on the record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

SKILL_TREES = (".claude", "src/copilot-cli")

DELETED_ARTIFACTS = (
    ".agents/memory/causality/causal-graph.json",
    "scripts/maintenance/install_merge_drivers.py",
    "scripts/maintenance/repair_causal_graph_ids.py",
    "scripts/validation/merge_causal_graph.py",
)

DELETED_PER_TREE = (
    "skills/memory/scripts/update_causal_graph.py",
    "skills/memory/scripts/backfill_episode_provenance.py",
    "skills/memory/resources/schemas/causal-graph.schema.json",
)

REMOVED_EXPORTS = (
    "add_causal_edge",
    "add_causal_node",
    "get_causal_path",
)


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative", DELETED_ARTIFACTS)
def test_deleted_artifact_stays_deleted(relative: str) -> None:
    assert not (REPO_ROOT / relative).exists(), (
        f"{relative} is back. ADR-089 removed it; reintroducing the causal tier "
        "requires superseding that ADR."
    )


@pytest.mark.parametrize("tree", SKILL_TREES)
@pytest.mark.parametrize("relative", DELETED_PER_TREE)
def test_deleted_skill_file_stays_deleted(tree: str, relative: str) -> None:
    target = REPO_ROOT / tree / relative
    assert not target.exists(), (
        f"{tree}/{relative} is back. Both skill trees must stay in parity; a "
        "mirror regenerated from a stale template is the likely cause."
    )


@pytest.mark.parametrize("tree", SKILL_TREES)
@pytest.mark.parametrize("symbol", REMOVED_EXPORTS)
def test_memory_core_exports_no_causal_symbol(tree: str, symbol: str) -> None:
    source = _read(f"{tree}/skills/memory/memory_core/__init__.py")
    assert symbol not in source, (
        f"{tree} memory_core re-exports {symbol}. The causal write API was removed by ADR-089."
    )


def test_gitattributes_declares_no_causal_merge_driver() -> None:
    source = _read(".gitattributes")
    assert "merge=causal-graph" not in source, (
        "A merge=causal-graph attribute is declared again. Its driver was "
        "deleted, so the attribute would name a nonexistent driver and git "
        "would fall back to a text merge on a megabyte of JSON."
    )


@pytest.mark.parametrize(
    "job",
    ("update-causal-graph", "install-merge-drivers"),
)
def test_lefthook_declares_no_causal_job(job: str) -> None:
    source = _read("lefthook.yml")
    assert job not in source, (
        f"lefthook.yml declares the {job} job again. ADR-089 removed it along "
        "with the script it invoked."
    )


def test_git_hook_policy_has_no_causal_subcommand() -> None:
    source = _read("scripts/validation/git_hook_policy.py")
    assert "update-causal-graph" not in source, (
        "git_hook_policy.py accepts the update-causal-graph subcommand again. "
        "The lefthook job that called it was removed with the tier."
    )


def test_episode_schema_retains_intra_episode_causal_links() -> None:
    """Edge case: the removal must not have taken the per-event links with it.

    ADR-089 keeps ``caused_by`` and ``leads_to`` inside episode files. They
    order events within one session and predate the derived graph. A cleanup
    that greps for "causal" and deletes matches would strip them, which is why
    this asserts presence rather than absence.
    """
    episodes = sorted((REPO_ROOT / ".agents/memory/episodes").glob("episode-*.json"))
    assert episodes, "no episode files found; the fixture for this test is gone"

    for path in episodes:
        events = json.loads(path.read_text(encoding="utf-8")).get("events") or []
        if any("caused_by" in event or "leads_to" in event for event in events):
            return

    pytest.fail(
        "No episode retains a caused_by or leads_to link. ADR-089 kept the "
        "intra-episode links; only the derived graph was removed."
    )


def test_non_causal_push_gate_tests_survived_the_removal() -> None:
    """Edge case: the removal must not have deleted tests by filename.

    ``test_git_hook_policy_causal_restore.py`` held five classes. Three covered
    the graph snapshot-and-restore path and went with the graph. Two covered the
    push gate's suppression parser and the ADR-review merge scope, which never
    touched causality; they shared the file only because both exercise
    ``git_hook_policy``. A first pass of ADR-089 deleted the file on the
    strength of its name and dropped 25 unrelated tests. This asserts the
    survivors are still collected.

    The file keeps its stale name on purpose. The push gate diffs with
    ``--no-renames`` to close a rename-based bypass, and the one real
    suppression in that file, the ``E402`` on its ``sys.path`` shim import,
    reads as newly added under a rename. Renaming needs the gate to follow
    renames first; filed as issue 3635.
    """
    path = REPO_ROOT / "tests/validation/test_git_hook_policy_causal_restore.py"
    assert path.is_file(), (
        "tests/validation/test_git_hook_policy_causal_restore.py is missing. Its "
        "name is stale but it still holds the suppression-parser and "
        "ADR-merge-scope tests, which never covered causality (ADR-089 Scope)."
    )

    body = path.read_text(encoding="utf-8")
    for expected in ("class TestPushedSuppressionPolicy:", "class TestAdrReviewPolicyMergeScope:"):
        assert expected in body, f"{expected} was dropped from the surviving push-gate tests"
