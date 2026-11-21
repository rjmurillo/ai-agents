"""adr_drift.py scan: each deterministic finding kind, positive, negative, and edge."""

from __future__ import annotations

from pathlib import Path

import pytest
from adr_drift_helpers import (
    ADR_DIR,
    adr_path,
    adr_text,
    commit,
    init_repo,
    kinds,
    scan,
    seeded_repo,
)


def _repo(tmp_path: Path, adrs: dict[str, str]) -> Path:
    return seeded_repo(tmp_path / "repo", adrs)


def test_no_adr_directory_is_an_info_finding_not_an_error(tmp_path, capsys):
    repo = init_repo(tmp_path / "repo")
    commit(repo, {"README.md": "x"}, "docs: readme")

    found = kinds(scan(capsys, repo), "no-adr-directory")

    assert len(found) == 1 and found[0]["severity"] == "info"
    assert found[0]["group"] == "Setup"
    assert found[0]["suggested_fix"]


def test_adr_directory_present_has_no_missing_directory_finding(tmp_path, capsys):
    repo = _repo(tmp_path, {adr_path(1): adr_text(1)})

    assert kinds(scan(capsys, repo), "no-adr-directory") == []


def test_duplicate_number_names_the_later_file_and_next_free_number(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        {
            adr_path(1, "alpha"): adr_text(1),
            adr_path(1, "beta"): adr_text(1),
            adr_path(2): adr_text(2),
        },
    )

    found = kinds(scan(capsys, repo), "adr-duplicate-number")

    assert len(found) == 1
    assert found[0]["evidence"]["path"].endswith("ADR-001-beta.md")
    assert "003" in found[0]["suggested_fix"]
    assert found[0]["confidence"] == "deterministic"


def test_unique_numbers_have_no_duplicate_finding(tmp_path, capsys):
    repo = _repo(tmp_path, {adr_path(1): adr_text(1), adr_path(2): adr_text(2)})

    assert kinds(scan(capsys, repo), "adr-duplicate-number") == []


def test_three_files_with_one_number_make_one_finding_listing_all_three(tmp_path, capsys):
    adrs = {adr_path(4, s): adr_text(4) for s in ("a", "b", "c")}

    found = kinds(scan(capsys, _repo(tmp_path, adrs)), "adr-duplicate-number")

    assert len(found) == 1 and len(found[0]["evidence"]["paths"]) == 3


def test_same_number_in_two_folders_is_not_a_duplicate(tmp_path, capsys):
    adrs = {adr_path(1): adr_text(1), "docs/adr/ADR-001-other.md": adr_text(1)}

    assert kinds(scan(capsys, _repo(tmp_path, adrs)), "adr-duplicate-number") == []


def test_title_number_mismatch_reports_both_numbers(tmp_path, capsys):
    repo = _repo(tmp_path, {adr_path(5): adr_text(5, h1="# ADR-006: Wrong")})

    found = kinds(scan(capsys, repo), "adr-title-number-mismatch")

    assert len(found) == 1
    assert found[0]["evidence"]["h1_number"] == 6 and found[0]["evidence"]["filename_number"] == 5
    assert found[0]["evidence"]["line"] > 0


def test_matching_title_has_no_mismatch(tmp_path, capsys):
    repo = _repo(tmp_path, {adr_path(5): adr_text(5)})

    assert kinds(scan(capsys, repo), "adr-title-number-mismatch") == []


def test_h1_without_a_number_is_not_a_mismatch(tmp_path, capsys):
    repo = _repo(tmp_path, {adr_path(5): adr_text(5, h1="# A plain title")})

    assert kinds(scan(capsys, repo), "adr-title-number-mismatch") == []


def test_h1_inside_a_code_fence_is_ignored(tmp_path, capsys):
    text = adr_text(5, h1="# A plain title") + "\n```\n# ADR-099: example\n```\n"

    assert (
        kinds(scan(capsys, _repo(tmp_path, {adr_path(5): text})), "adr-title-number-mismatch") == []
    )


def test_unparseable_name_is_flagged(tmp_path, capsys):
    repo = _repo(tmp_path, {adr_path(1): adr_text(1), f"{ADR_DIR}/ADR-oops.md": "# x\n"})

    found = kinds(scan(capsys, repo), "adr-unparseable-name")

    assert [f["evidence"]["path"] for f in found] == [f"{ADR_DIR}/ADR-oops.md"]


@pytest.mark.parametrize("name", ["ADR-TEMPLATE.md", "README.md", "notes.md", "DESIGN-REVIEW-x.md"])
def test_template_readme_and_unrelated_names_are_not_unparseable(tmp_path, capsys, name):
    repo = _repo(tmp_path, {adr_path(1): adr_text(1), f"{ADR_DIR}/{name}": "# x\n"})

    assert kinds(scan(capsys, repo), "adr-unparseable-name") == []


def test_number_gap_lists_missing_numbers_with_low_severity(tmp_path, capsys):
    repo = _repo(tmp_path, {adr_path(n): adr_text(n) for n in (1, 2, 5)})

    found = kinds(scan(capsys, repo), "adr-number-gap")

    assert found[0]["evidence"]["missing"] == [3, 4] and found[0]["severity"] == "low"
    assert found[0]["suggested_fix"].startswith("None needed")


def test_consecutive_numbers_and_a_single_file_have_no_gap(tmp_path, capsys):
    consecutive = _repo(tmp_path / "a", {adr_path(n): adr_text(n) for n in (1, 2, 3)})
    single = _repo(tmp_path / "b", {adr_path(7): adr_text(7)})

    assert kinds(scan(capsys, consecutive), "adr-number-gap") == []
    assert kinds(scan(capsys, single), "adr-number-gap") == []


def test_broken_link_names_the_existing_file_for_that_number(tmp_path, capsys):
    body = "See [other](ADR-002-old-name.md)."
    repo = _repo(
        tmp_path,
        {adr_path(1): adr_text(1, body=body), adr_path(2, "new-name"): adr_text(2)},
    )

    found = kinds(scan(capsys, repo), "adr-broken-link")

    assert len(found) == 1 and "ADR-002-new-name.md" in found[0]["suggested_fix"]


def test_broken_link_to_a_number_with_no_file_says_so(tmp_path, capsys):
    repo = _repo(tmp_path, {adr_path(1): adr_text(1, body="[x](ADR-099-gone.md)")})

    found = kinds(scan(capsys, repo), "adr-broken-link")

    assert "No file holds ADR-99" in found[0]["suggested_fix"]


@pytest.mark.parametrize(
    "body",
    [
        "[ok](ADR-002-decision.md)",
        "[ok](ADR-002-decision.md#context)",
        "```\n[x](ADR-099-gone.md)\n```",
        "`[x](ADR-099-gone.md)`",
        "[ext](https://example.com/ADR-099-gone.md)",
        "[other dir](../elsewhere/ADR-099-gone.md)",
    ],
)
def test_valid_or_out_of_scope_links_are_not_broken(tmp_path, capsys, body):
    repo = _repo(
        tmp_path,
        {adr_path(1): adr_text(1, body=body), adr_path(2): adr_text(2)},
    )

    assert kinds(scan(capsys, repo), "adr-broken-link") == []


def test_supersedes_missing_target_from_frontmatter(tmp_path, capsys):
    text = adr_text(2, frontmatter="").replace("supersedes: []", "supersedes: [ADR-050]")
    repo = _repo(tmp_path, {adr_path(2): text})

    found = kinds(scan(capsys, repo), "adr-supersedes-missing-target")

    assert found[0]["evidence"]["number"] == 50 and "Fix the number" in found[0]["suggested_fix"]


def test_supersedes_existing_target_is_not_missing(tmp_path, capsys):
    newer = adr_text(2).replace("supersedes: []", "supersedes: [ADR-001]")
    older = adr_text(1, status="superseded").replace(
        "superseded-by: null", "superseded-by: ADR-002"
    )
    repo = _repo(tmp_path, {adr_path(1): older, adr_path(2): newer})

    assert kinds(scan(capsys, repo), "adr-supersedes-missing-target") == []


def test_superseded_by_status_line_to_a_missing_record_is_found(tmp_path, capsys):
    text = adr_text(1, status="Superseded by ADR-777")

    found = kinds(
        scan(capsys, _repo(tmp_path, {adr_path(1): text})), "adr-supersedes-missing-target"
    )

    assert found and found[0]["evidence"]["number"] == 777


def test_one_sided_supersession_is_not_reciprocal(tmp_path, capsys):
    newer = adr_text(2).replace("supersedes: []", "supersedes: [ADR-001]")
    repo = _repo(tmp_path, {adr_path(1): adr_text(1), adr_path(2): newer})

    found = kinds(scan(capsys, repo), "adr-supersession-not-reciprocal")

    assert len(found) == 1 and found[0]["evidence"]["path"].endswith("ADR-001-decision.md")
    assert "superseded-by: ADR-2" in found[0]["suggested_fix"]


def test_reciprocal_supersession_has_no_finding(tmp_path, capsys):
    newer = adr_text(2).replace("supersedes: []", "supersedes: [ADR-001]")
    older = adr_text(1, status="superseded").replace(
        "superseded-by: null", "superseded-by: ADR-002"
    )
    repo = _repo(tmp_path, {adr_path(1): older, adr_path(2): newer})

    assert kinds(scan(capsys, repo), "adr-supersession-not-reciprocal") == []


def test_reciprocity_through_a_status_line_counts(tmp_path, capsys):
    newer = adr_text(2).replace("supersedes: []", "supersedes: [ADR-001]")
    older = adr_text(1, status="Superseded by ADR-002")
    repo = _repo(tmp_path, {adr_path(1): older, adr_path(2): newer})

    assert kinds(scan(capsys, repo), "adr-supersession-not-reciprocal") == []


def test_cited_path_that_no_longer_exists_is_found(tmp_path, capsys):
    body = "The code lives in `src/gone/module.py`."
    repo = _repo(tmp_path, {adr_path(1): adr_text(1, body=body), "src/keep.py": "x"})

    found = kinds(scan(capsys, repo), "adr-cited-path-missing")

    assert [f["evidence"]["cited"] for f in found] == ["src/gone/module.py"]


def test_cited_path_that_exists_is_not_flagged(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        {adr_path(1): adr_text(1, body="See `src/keep.py`."), "src/keep.py": "x"},
    )

    assert kinds(scan(capsys, repo), "adr-cited-path-missing") == []


@pytest.mark.parametrize(
    ("status", "body"),
    [
        ("superseded", "See `src/gone/module.py`."),
        ("accepted", "See `src/<name>/module.py`."),
        ("accepted", "See `nowhere/at/all.py`."),
        ("accepted", "See `src/gone/YYYY-MM-DD.md`."),
    ],
)
def test_superseded_placeholder_and_foreign_paths_are_skipped(tmp_path, capsys, status, body):
    repo = _repo(
        tmp_path,
        {adr_path(1): adr_text(1, status=status, body=body), "src/keep.py": "x"},
    )

    assert kinds(scan(capsys, repo), "adr-cited-path-missing") == []


def test_every_finding_has_a_nonempty_suggested_fix(tmp_path, capsys):
    adrs = {
        adr_path(1, "a"): adr_text(1, body="`src/gone/x.py` [l](ADR-009-x.md)"),
        adr_path(1, "b"): adr_text(1, h1="# ADR-002: Wrong"),
        adr_path(4): adr_text(4),
        f"{ADR_DIR}/ADR-bad.md": "# x\n",
        "src/keep.py": "x",
    }

    result = scan(capsys, _repo(tmp_path, adrs))

    assert len(result["findings"]) >= 5
    assert all(f["suggested_fix"].strip() for f in result["findings"])
    assert all(f["confidence"] in {"deterministic", "heuristic"} for f in result["findings"])
