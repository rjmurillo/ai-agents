"""Tests for build/scripts/check_surface_parity.py: loading and per-relation checks (issue #5637).

Every test builds a small synthetic repository so a case names exactly the
surface it exercises. Inventory discovery, the CLI, and the build_all wiring are
in ``test_check_surface_parity_inventory.py``; the live repository is held to the
manifest by ``test_surface_parity_repo.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.build_scripts import _surface_parity_helpers as h
from tests.build_scripts._surface_parity_helpers import (
    csp,
    findings,
    generated,
    independent,
    kinds,
    put,
    sm,
    surface,
    write_manifest,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return h.make_repo(tmp_path)


# --- Manifest loading -----------------------------------------------------


def test_clean_repo_has_no_findings(repo: Path) -> None:
    assert findings(repo) == []


def test_absent_manifest_loads_as_none(tmp_path: Path) -> None:
    assert sm.load_manifest(tmp_path) is None


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda s: s.update(relation="bogus"), "unknown relation"),
        (lambda s: s.update(colour="red"), "unknown keys"),
        (lambda s: s.update(extras="sometimes"), "`extras` must be one of"),
        (lambda s: s.pop("generator"), "`generator` is required"),
        (lambda s: s.pop("authority"), "`authority` is required"),
        (lambda s: s.pop("owner"), "`owner`"),
        (lambda s: s.update(path="../escape"), "traversal"),
        (lambda s: s.update(path="/abs"), "absolute"),
        (lambda s: s.pop("id"), "`id` is required"),
        (lambda s: s.update(id=""), "`id` must be a non-empty string"),
        (lambda s: s.update(include="*.md"), "list of non-empty strings"),
        (lambda s: s.update(divergent=["a.md"]), "`divergent` applies only"),
        (lambda s: s.update(reason=5), "non-empty string"),
    ],
)
def test_malformed_surface_is_rejected(repo: Path, mutate: Any, message: str) -> None:
    bad = generated("src/out", "templates/agents", "build/gen.py")
    bad["id"] = "src-out"
    mutate(bad)
    write_manifest(repo, [bad], ["src"])
    with pytest.raises(sm.SurfaceManifestError, match=message):
        sm.load_manifest(repo)


def test_independent_surface_needs_a_reason_and_no_authority(repo: Path) -> None:
    write_manifest(repo, [surface(path="src/notes", relation="independent")], ["src"])
    with pytest.raises(sm.SurfaceManifestError, match="needs a `reason`"):
        sm.load_manifest(repo)
    write_manifest(
        repo,
        [independent("src/notes", authority="templates/agents")],
        ["src"],
    )
    with pytest.raises(sm.SurfaceManifestError, match="has no authority"):
        sm.load_manifest(repo)


def test_hand_translated_surface_must_list_divergent(repo: Path) -> None:
    write_manifest(
        repo,
        [surface(path="src/out", relation="translated", authority="templates/agents", owner="g")],
        ["src"],
    )
    with pytest.raises(sm.SurfaceManifestError, match="must list `divergent`"):
        sm.load_manifest(repo)


def test_duplicate_id_and_duplicate_shape_are_rejected(repo: Path) -> None:
    first = independent("src/notes")
    second = independent("src/other")
    second["id"] = first["id"]
    write_manifest(repo, [first, second], ["src"])
    with pytest.raises(sm.SurfaceManifestError, match="duplicate surface id"):
        sm.load_manifest(repo)
    twin = independent("src/notes")
    twin["id"] = "twin"
    write_manifest(repo, [first, twin], ["src"])
    with pytest.raises(sm.SurfaceManifestError, match="repeats path/include/exclude"):
        sm.load_manifest(repo)


@pytest.mark.parametrize(
    "doc",
    [
        {"schemaVersion": "1.0", "roots": [], "surfaces": [{"id": "a"}]},
        {"schemaVersion": "1.0", "roots": ["src"], "surfaces": []},
        {"schemaVersion": "1.0", "roots": ["src"], "surfaces": ["not a mapping"]},
        {"schemaVersion": "9.0", "roots": ["src"], "surfaces": [{"id": "a"}]},
    ],
)
def test_malformed_document_is_rejected(repo: Path, doc: dict[str, Any]) -> None:
    put(repo, sm.MANIFEST_REL, yaml.safe_dump(doc))
    with pytest.raises(sm.SurfaceManifestError):
        sm.load_manifest(repo)


# --- Generated surfaces ---------------------------------------------------


def test_missing_generator_is_reported(repo: Path) -> None:
    (repo / "build/gen.py").unlink()
    found = findings(repo)
    assert kinds(found) == ["MISSING-GENERATOR"]
    assert found[0].path == "build/gen.py"


def test_missing_authority_is_reported(repo: Path) -> None:
    (repo / "templates/agents/a.md").unlink()
    (repo / "templates/agents").rmdir()
    assert kinds(findings(repo)) == ["MISSING-AUTHORITY"]


def test_stale_generated_path_is_labelled_with_file_and_generator(repo: Path) -> None:
    manifest = sm.load_manifest(repo)
    assert manifest is not None
    (found,) = csp.classify_changes(manifest, ["src/out/a.md"])
    assert found.kind == "STALE-generated"
    assert found.path == "src/out/a.md"
    assert "build/gen.py" in found.detail
    assert "templates/agents" in found.detail
    assert "gate" in found.detail


def test_unrelated_change_produces_no_finding(repo: Path) -> None:
    put(repo, "docs/guide.md", "changed\n")
    put(repo, "src/notes/readme.md", "edited\n")
    assert findings(repo) == []


# --- Hand-maintained mirrors ---------------------------------------------


@pytest.fixture
def mirror(repo: Path) -> Path:
    put(repo, "canon/one.md", "one\n")
    put(repo, "canon/two.md", "two\n")
    put(repo, "copy/one.md", "one\n")
    put(repo, "copy/two.md", "two\n")
    write_manifest(
        repo,
        [
            surface(
                path="copy", relation="mirrored", authority="canon", owner="check_surface_parity"
            ),
            independent("canon"),
        ],
        ["copy", "canon"],
    )
    return repo


def test_matching_hand_maintained_copy_passes(mirror: Path) -> None:
    assert findings(mirror) == []


def test_stale_hand_maintained_copy_fails_with_file_level_diagnostic(mirror: Path) -> None:
    put(mirror, "canon/one.md", "one, edited\n")
    (found,) = findings(mirror)
    assert found.kind == "STALE"
    assert found.path == "copy/one.md"
    assert found.surface == "copy"
    assert "canon/one.md" in found.detail


def test_missing_hand_maintained_copy_fails(mirror: Path) -> None:
    (mirror / "copy/two.md").unlink()
    (found,) = findings(mirror)
    assert (found.kind, found.path) == ("MISSING", "copy/two.md")


def test_extra_file_in_hand_maintained_copy_fails(mirror: Path) -> None:
    put(mirror, "copy/three.md", "three\n")
    (found,) = findings(mirror)
    assert (found.kind, found.path) == ("EXTRA", "copy/three.md")


def test_extras_allow_tolerates_unmatched_files(mirror: Path) -> None:
    put(mirror, "copy/three.md", "three\n")
    write_manifest(
        mirror,
        [
            surface(
                path="copy",
                relation="mirrored",
                authority="canon",
                owner="o",
                extras="allow",
            ),
            independent("canon"),
        ],
        ["copy", "canon"],
    )
    assert findings(mirror) == []


def test_include_limits_which_authority_files_are_required(mirror: Path) -> None:
    (mirror / "copy/two.md").unlink()
    write_manifest(
        mirror,
        [
            surface(
                path="copy",
                relation="mirrored",
                authority="canon",
                owner="o",
                include=["one.md"],
            ),
            independent("copy", id="copy-two", include=["two.md"]),
            independent("canon"),
        ],
        ["copy", "canon"],
    )
    assert findings(mirror) == []


def test_authority_exclude_is_not_required_and_must_not_ship(mirror: Path) -> None:
    (mirror / "copy/two.md").unlink()
    entry = surface(
        path="copy",
        relation="mirrored",
        authority="canon",
        owner="o",
        authority_exclude=["two.md"],
    )
    write_manifest(mirror, [entry, independent("canon")], ["copy", "canon"])
    assert findings(mirror) == []
    put(mirror, "copy/two.md", "leaked\n")
    assert kinds(findings(mirror)) == ["EXCLUSION-VIOLATED"]


def test_authority_exclude_naming_nothing_is_reported(mirror: Path) -> None:
    entry = surface(
        path="copy",
        relation="mirrored",
        authority="canon",
        owner="o",
        authority_exclude=["ghost.md"],
    )
    write_manifest(mirror, [entry, independent("canon")], ["copy", "canon"])
    assert kinds(findings(mirror)) == ["EXCLUSION-UNKNOWN"]


# --- Translated surfaces --------------------------------------------------


@pytest.fixture
def translated(mirror: Path) -> Path:
    put(mirror, "copy/one.md", "one, translated\n")
    entry = surface(
        path="copy",
        relation="translated",
        authority="canon",
        owner="o",
        divergent=["one.md"],
    )
    write_manifest(mirror, [entry, independent("canon")], ["copy", "canon"])
    return mirror


def test_listed_divergence_is_not_a_finding(translated: Path) -> None:
    assert findings(translated) == []


def test_unlisted_divergence_in_a_translated_surface_fails(translated: Path) -> None:
    put(translated, "copy/two.md", "two, drifted\n")
    (found,) = findings(translated)
    assert (found.kind, found.path) == ("STALE", "copy/two.md")


def test_divergent_entry_that_is_now_identical_is_flagged(translated: Path) -> None:
    put(translated, "copy/one.md", "one\n")
    (found,) = findings(translated)
    assert (found.kind, found.path) == ("DIVERGENT-INVALID", "one.md")
    assert "identical" in found.detail


def test_divergent_entry_with_no_authority_file_is_flagged(translated: Path) -> None:
    (translated / "canon/one.md").unlink()
    found = findings(translated)
    assert "DIVERGENT-INVALID" in kinds(found)


# --- Independent surfaces -------------------------------------------------


def test_independent_surface_is_never_compared(repo: Path) -> None:
    put(repo, "src/notes/a.md", "differs from the generated sibling\n")
    assert findings(repo) == []


def test_generator_that_rewrites_an_independent_surface_is_flagged(repo: Path) -> None:
    manifest = sm.load_manifest(repo)
    assert manifest is not None
    (found,) = csp.classify_changes(manifest, ["src/notes/readme.md"])
    assert found.kind == "WROTE-INDEPENDENT"


def test_stale_path_owned_by_no_surface_is_unclassified(repo: Path) -> None:
    manifest = sm.load_manifest(repo)
    assert manifest is not None
    (found,) = csp.classify_changes(manifest, ["elsewhere/file.md"])
    assert found.kind == "UNCLASSIFIED"


# --- Classification -------------------------------------------------------


def test_file_under_a_root_with_no_owner_is_unclassified(repo: Path) -> None:
    put(repo, "src/orphan/file.md")
    (found,) = findings(repo)
    assert (found.kind, found.path) == ("UNCLASSIFIED", "src/orphan/file.md")


def test_equal_depth_surfaces_that_both_match_are_ambiguous(repo: Path) -> None:
    write_manifest(
        repo,
        [
            independent("src/notes", id="notes-md", include=["*.md"]),
            independent("src/notes", id="notes-readme", include=["readme.*"]),
            generated("src/out", "templates/agents", "build/gen.py"),
        ],
        ["src"],
    )
    found = findings(repo)
    assert [(f.kind, f.path) for f in found] == [("AMBIGUOUS", "src/notes/readme.md")]


def test_deeper_surface_wins_over_a_shallower_one(repo: Path) -> None:
    put(repo, "src/notes/deep/x.md")
    write_manifest(
        repo,
        [
            independent("src/notes"),
            independent("src/notes/deep"),
            generated("src/out", "templates/agents", "build/gen.py"),
        ],
        ["src"],
    )
    manifest = sm.load_manifest(repo)
    assert manifest is not None
    owner, ambiguous = sm.owner_of(manifest, "src/notes/deep/x.md")
    assert owner is not None
    assert owner.path == "src/notes/deep"
    assert not ambiguous


def test_include_beats_a_catch_all_at_equal_depth(repo: Path) -> None:
    write_manifest(
        repo,
        [
            independent("src/notes"),
            surface(
                path="src/notes",
                relation="generated",
                authority="templates/agents",
                generator="build/gen.py",
                owner="g",
                id="notes-generated",
                include=["readme.md"],
            ),
            generated("src/out", "templates/agents", "build/gen.py"),
        ],
        ["src"],
    )
    manifest = sm.load_manifest(repo)
    assert manifest is not None
    owner, ambiguous = sm.owner_of(manifest, "src/notes/readme.md")
    assert owner is not None
    assert owner.relation == "generated"
    assert not ambiguous


def test_exclude_removes_a_file_from_a_surface(repo: Path) -> None:
    write_manifest(
        repo,
        [
            independent("src/notes", exclude=["readme.md"]),
            generated("src/out", "templates/agents", "build/gen.py"),
        ],
        ["src"],
    )
    (found,) = findings(repo)
    assert (found.kind, found.path) == ("UNCLASSIFIED", "src/notes/readme.md")
