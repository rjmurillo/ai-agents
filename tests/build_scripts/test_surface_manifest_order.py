"""The manifest sorts its surfaces once, not once per file (issue #5382).

``owner_of`` runs for every tracked file under a root. It used to rebuild the
specificity-sorted tuple on each call, which made 4,684 sorts of the live
manifest's rows and dominated the classification check. These tests pin that
the order is built once, that it is still the order ``owner_of`` needs, and that
the answers match a reference that sorts on every call.
"""

from __future__ import annotations

import dataclasses

from tests.build_scripts._surface_parity_helpers import REPO_ROOT, sm


def _row(path: str, **fields: object) -> sm.Surface:
    return sm.Surface(
        id=path.replace("/", "-"), path=path, relation="independent", reason="authored", **fields
    )  # type: ignore[arg-type]


def _manifest(*surfaces: sm.Surface, roots: tuple[str, ...] = ("src",)) -> sm.Manifest:
    return sm.Manifest(roots=roots, surfaces=tuple(surfaces))


def _reference_owner(manifest: sm.Manifest, path: str) -> tuple[sm.Surface | None, bool]:
    """``owner_of`` with the sort inside the loop, as it was before the change."""
    first: sm.Surface | None = None
    for surface in sorted(manifest.surfaces, key=lambda s: s.specificity, reverse=True):
        rel = sm.rel_to(path, surface.path)
        if rel is None or not sm.matches(surface, rel):
            continue
        if first is None:
            first = surface
            continue
        return first, surface.specificity == first.specificity
    return first, False


class TestOrderedIsBuiltOnce:
    def test_same_tuple_object_on_every_access(self) -> None:
        manifest = _manifest(_row("src/a"), _row("src/a/b"))

        assert manifest.ordered is manifest.ordered

    def test_most_specific_first(self) -> None:
        shallow = _row("src")
        deep = _row("src/a/b")
        mid = _row("src/a")

        assert _manifest(shallow, deep, mid).ordered == (deep, mid, shallow)

    def test_include_wins_at_equal_depth(self) -> None:
        catch_all = _row("src/a")
        included = _row("src/a", include=("*.md",))
        included = dataclasses.replace(included, id="src-a-md")

        assert _manifest(catch_all, included).ordered[0] is included

    def test_empty_manifest_has_an_empty_order(self) -> None:
        assert _manifest().ordered == ()

    def test_replace_rebuilds_the_order_for_the_new_rows(self) -> None:
        deep = _row("src/a/b")
        shallow = _row("src")
        manifest = _manifest(deep, shallow)

        weakened = dataclasses.replace(manifest, surfaces=(shallow,))

        assert weakened.ordered == (shallow,)
        assert manifest.ordered == (deep, shallow)

    def test_the_order_is_not_part_of_equality_or_repr(self) -> None:
        a = _manifest(_row("src/a"), _row("src"))
        b = _manifest(_row("src/a"), _row("src"))

        assert a == b
        assert "ordered" not in repr(a)


class TestOwnerOfIsUnchanged:
    def test_synthetic_tree_matches_the_reference(self) -> None:
        manifest = _manifest(
            _row("src"),
            _row("src/notes"),
            _row("src/notes/deep"),
            _row("src/notes", include=("readme.md",)),
            _row("src/out", exclude=("skip.md",)),
            _row("src/tie"),
            _row("src/tie"),
        )
        paths = [
            "src/other.md",
            "src/notes/readme.md",
            "src/notes/other.md",
            "src/notes/deep/x.md",
            "src/out/a.md",
            "src/out/skip.md",
            "src/tie/x.md",
            "elsewhere/x.md",
        ]

        for path in paths:
            assert sm.owner_of(manifest, path) == _reference_owner(manifest, path), path

    def test_ties_are_still_reported_ambiguous(self) -> None:
        manifest = _manifest(_row("src/tie"), dataclasses.replace(_row("src/tie"), id="other"))

        owner, ambiguous = sm.owner_of(manifest, "src/tie/x.md")

        assert owner is not None
        assert ambiguous

    def test_live_manifest_matches_the_reference_on_a_sample_of_tracked_files(self) -> None:
        manifest = sm.load_manifest(REPO_ROOT)
        assert manifest is not None
        files = sm.list_files(REPO_ROOT)
        sample = files[::25]
        assert len(sample) > 100, "the sample is too small to mean anything"

        mismatches = [
            path
            for path in sample
            if sm.owner_of(manifest, path) != _reference_owner(manifest, path)
        ]

        assert mismatches == []
