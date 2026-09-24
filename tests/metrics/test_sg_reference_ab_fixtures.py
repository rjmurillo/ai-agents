"""Tests for scripts/metrics/sg_reference_ab_fixtures.py (#5856, REQ-6, REQ-7).

The four seeded fixture repositories (``f_repeat``, ``f_paths``, ``f_trunc``,
``f_mismatch``). Split out of ``tests/metrics/test_sg_reference_ab.py`` under
the taste-lints file-size gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.metrics import sg_diff_reference as sgd
from scripts.metrics import sg_reference_ab_fixtures as fixtures_mod


@pytest.mark.parametrize("name", list(fixtures_mod.FIXTURE_NAMES))
def test_each_fixture_builder_seeds_new_vuln_on_plus_line_only(tmp_path: Path, name: str) -> None:
    fixture = fixtures_mod._FIXTURE_BUILDERS[name](tmp_path)

    assert fixture.name == name
    seeded_content = dict(fixture.diff_files)[fixture.seeded_path]
    assert any(line.startswith("+") for line in seeded_content.splitlines())
    assert not any(line.startswith("-") for line in seeded_content.splitlines())

    preexisting_content = dict(fixture.diff_files)[fixture.preexisting_path]
    # Pre-existing vuln appears only as unprefixed context, never a new "+" line.
    assert not any(line.startswith("+") for line in preexisting_content.splitlines())

    # The seeded file is real on disk and readable through fixture_dir.
    on_disk = (fixture.fixture_dir / fixture.seeded_path).read_text(encoding="utf-8")
    assert on_disk  # non-empty


def test_f_paths_preserves_ordering_of_rename_delete_and_new_file(tmp_path: Path) -> None:
    fixture = fixtures_mod._build_f_paths(tmp_path)

    assert fixture.touched_paths == [
        "queries_old.py",
        "queries.py",
        "obsolete.py",
        "legacy_query.py",
    ]
    assert dict(fixture.diff_files)["obsolete.py"].startswith("-")


def test_f_trunc_places_vuln_file_before_the_large_generated_file(tmp_path: Path) -> None:
    fixture = fixtures_mod._build_f_trunc(tmp_path)

    assert fixture.touched_paths.index(fixture.seeded_path) < fixture.touched_paths.index(
        "generated_data.json"
    )
    assert fixture.per_file_bytes == 6_000
    assert fixture.total_bytes == 20_000


def test_f_mismatch_context_dir_differs_from_main_but_shares_repo_identity(tmp_path: Path) -> None:
    fixture = fixtures_mod._build_f_mismatch(tmp_path)

    assert fixture.context_note != ""
    assert "trust the diff" in fixture.context_note
    # The on-disk seeded file at the mismatched checkout predates the vuln.
    on_disk = (fixture.fixture_dir / fixture.seeded_path).read_text(encoding="utf-8")
    assert "yaml" not in on_disk
    assert sgd.repo_identity(fixture.fixture_dir) == fixture.repo_id


def test_build_fixtures_selects_requested_names(tmp_path: Path) -> None:
    fixtures = fixtures_mod.build_fixtures(tmp_path, ["f_repeat", "f_trunc"])

    assert [f.name for f in fixtures] == ["f_repeat", "f_trunc"]
