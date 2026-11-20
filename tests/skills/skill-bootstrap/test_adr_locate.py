"""Tests for adr_locate: ADR folder detection, numbering, and the folder style (P11, P16).

Ports the folder and number cases of align-cli tests/adr-writer.test.ts (MIT, Copyright
(c) 2026 Align Tech Ltd, see LICENSE-align): the repo's own folder is used, the highest
number and its width are kept, and an empty folder starts at 0001. Each fix from the port
plan, section 3, has a case that fails on upstream's rule.
"""

from __future__ import annotations

from pathlib import Path

import adr_locate
import pytest
from adr_helpers import new_repo, write

ADR_122 = (
    "# ADR-122: Use Postgres\n\n## Status\n\nAccepted\n\n## Context\n\nWhy.\n\n"
    "## Decision\n\nDo it.\n\n## Consequences\n\nSome.\n"
)


def _adr(repo: Path, rel: str, text: str = "# x\n") -> None:
    write(repo, rel, text)


def _locate(repo: Path) -> dict[str, object]:
    return adr_locate.locate(repo)


def test_a_repo_with_no_adr_folder_has_no_folders_and_no_primary(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    assert _locate(repo) == {"folders": [], "primary": None, "next_number": None, "examined": 0}


def test_the_project_toolkit_architecture_folder_is_found_with_prefix_and_width(
    tmp_path: Path,
) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, ".project-toolkit/architecture/ADR-121-a.md")
    _adr(repo, ".project-toolkit/architecture/ADR-122-use-postgres.md", ADR_122)
    result = _locate(repo)
    (folder,) = result["folders"]  # type: ignore[misc]
    assert result["primary"] == ".project-toolkit/architecture"
    assert result["next_number"] == 123
    assert result["examined"] == 2
    assert (folder["prefix"], folder["width"], folder["highest"]) == ("ADR-", 3, 122)
    assert folder["h1_form"] == "# ADR-{number}: {title}"
    assert folder["headings"] == ["Status", "Context", "Decision", "Consequences"]
    assert folder["source"] == "known" and folder["newest"] == "ADR-122-use-postgres.md"


@pytest.mark.parametrize(
    ("name", "prefix", "width", "highest"),
    [
        ("ADR-007-x.md", "ADR-", 3, 7),
        ("adr-0012-x.md", "adr-", 4, 12),
        ("0012-x.md", "", 4, 12),
        ("0012_x.md", "", 4, 12),
        ("12-x.md", "", 2, 12),
        ("0012-x.mdx", "", 4, 12),
        ("0012-x.adoc", "", 4, 12),
    ],
)
def test_every_adr_name_pattern_is_recognized(
    tmp_path: Path, name: str, prefix: str, width: int, highest: int
) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, f"docs/adr/{name}")
    folder = adr_locate.folder_style(repo / "docs" / "adr")
    assert (folder.prefix, folder.width, folder.highest, folder.count) == (
        prefix,
        width,
        highest,
        1,
    )


@pytest.mark.parametrize(
    "name", ["README.md", "template.md", "ADR-template.md", "notes-0012.md", "20240301-x.md"]
)
def test_a_file_that_is_not_named_like_an_adr_is_not_one(name: str, tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, f"docs/adr/{name}")
    assert adr_locate.adr_files(repo / "docs" / "adr") == []


def test_a_folder_holding_only_a_readme_is_not_an_adr_folder(tmp_path: Path) -> None:
    # Upstream's adrDirFor took the first folder with any .md file, README included.
    repo = new_repo(tmp_path / "r")
    _adr(repo, "docs/adr/README.md", "# ADRs\n")
    _adr(repo, "docs/decisions/0001-use-postgres.md")
    result = _locate(repo)
    assert result["primary"] == "docs/decisions"
    assert [f["path"] for f in result["folders"]] == ["docs/decisions"]  # type: ignore[attr-defined]


def test_an_empty_known_folder_is_not_an_adr_folder(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    (repo / "adr").mkdir()
    (repo / "docs").write_text("not a folder", encoding="utf-8")
    assert _locate(repo)["folders"] == []


def test_two_folders_give_no_primary_and_no_next_number(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, "docs/adr/0001-a.md")
    _adr(repo, "docs/decisions/0001-b.md")
    result = _locate(repo)
    assert [f["path"] for f in result["folders"]] == ["docs/adr", "docs/decisions"]  # type: ignore[attr-defined]
    assert (result["primary"], result["next_number"]) == (None, None)


def test_the_highest_number_wins_and_keeps_its_width(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    for name in ("0007-a.md", "0012-b.md", "README.md"):
        _adr(repo, f"docs/adr/{name}")
    style = adr_locate.folder_style(repo / "docs" / "adr")
    assert (style.highest, style.width) == (12, 4)
    assert adr_locate.locate(repo)["next_number"] == 13


def test_an_empty_folder_starts_at_one_with_the_nygard_defaults(tmp_path: Path) -> None:
    style = adr_locate.folder_style(tmp_path / "missing")
    assert (style.count, style.highest, style.width, style.prefix) == (0, 0, 4, "")
    assert style.headings == adr_locate.NYGARD_HEADINGS
    assert adr_locate.render_h1(style.h1_form, 1, "Use X") == "# 1. Use X"


def test_adr_dir_file_names_the_folder_and_beats_nothing_else(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, "records/0001-a.md")
    write(repo, ".adr-dir", "records\n")
    result = _locate(repo)
    (folder,) = result["folders"]  # type: ignore[misc]
    assert (folder["path"], folder["source"]) == ("records", "adr-dir")


def test_adr_dir_and_a_known_folder_are_both_reported(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, "records/0001-a.md")
    _adr(repo, "docs/adr/0001-b.md")
    write(repo, ".adr-dir", "records\n")
    result = _locate(repo)
    assert [(f["path"], f["source"]) for f in result["folders"]] == [  # type: ignore[attr-defined]
        ("docs/adr", "known"),
        ("records", "adr-dir"),
    ]
    assert result["primary"] is None


@pytest.mark.parametrize("declared", ["../outside", "/etc", "", "missing", "a\x00b"])
def test_an_adr_dir_that_escapes_or_names_nothing_is_ignored(tmp_path: Path, declared: str) -> None:
    repo = new_repo(tmp_path / "r")
    (tmp_path / "outside").mkdir()
    _adr(tmp_path, "outside/0001-a.md")
    write(repo, ".adr-dir", declared + "\n")
    assert _locate(repo)["folders"] == []


def test_a_folder_of_three_adr_files_is_found_when_nothing_else_is(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    for n in (1, 2, 3):
        _adr(repo, f"team/records/{n:04d}-a.md")
    _adr(repo, "other/0001-a.md")
    _adr(repo, "other/0002-b.md")
    result = _locate(repo)
    assert [(f["path"], f["source"]) for f in result["folders"]] == [("team/records", "scan")]  # type: ignore[attr-defined]


def test_the_scan_does_not_run_when_a_known_folder_exists(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, "docs/adr/0001-a.md")
    for n in (1, 2, 3):
        _adr(repo, f"team/records/{n:04d}-a.md")
    assert [f["path"] for f in _locate(repo)["folders"]] == ["docs/adr"]  # type: ignore[attr-defined]


def test_the_scan_skips_dependency_and_build_folders(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    for skipped in ("node_modules/pkg", "vendor/x", "build/out"):
        for n in (1, 2, 3):
            _adr(repo, f"{skipped}/{n:04d}-a.md")
    assert _locate(repo)["folders"] == []


def test_known_folders_are_pinned() -> None:
    assert adr_locate.KNOWN_FOLDERS[:5] == (
        ".project-toolkit/architecture",
        "docs/architecture",
        "docs/decisions",
        "docs/adr",
        "architecture/decisions",
    )
    upstream = (
        "docs/adr doc/adr docs/decisions doc/decisions adr docs/adrs src/docs/adrs "
        "src/docs/adr docs/architecture/adr docs/architecture/decisions "
        "docs/rfcs docs/rfc rfcs rfc"
    ).split()
    assert set(upstream) <= set(adr_locate.KNOWN_FOLDERS)
    assert len(set(adr_locate.KNOWN_FOLDERS)) == len(adr_locate.KNOWN_FOLDERS) == 17


def test_a_symlinked_folder_is_reported_once(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, "docs/adr/0001-a.md")
    try:
        (repo / "adr").symlink_to(repo / "docs" / "adr", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert len(_locate(repo)["folders"]) == 1  # type: ignore[arg-type]


def test_a_symlinked_adr_file_is_not_read(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    secret = write(tmp_path, "secret.md", "# secret\n")
    _adr(repo, "docs/adr/0001-a.md")
    try:
        (repo / "docs" / "adr" / "0002-link.md").symlink_to(secret)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert [f.name for f in adr_locate.adr_files(repo / "docs" / "adr")] == ["0001-a.md"]


def test_a_file_over_one_mebibyte_is_skipped_and_counted(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, "docs/adr/0001-small.md", "# small\n")
    _adr(repo, "docs/adr/0002-big.md", "x" * (adr_locate.MAX_READ_BYTES + 1))
    texts, skipped = adr_locate.read_adr_texts(repo)
    assert [path for path, _ in texts] == ["docs/adr/0001-small.md"]
    assert skipped == 1


@pytest.mark.parametrize(
    ("h1", "file_number", "form", "rendered"),
    [
        ("ADR-123: Use X", 123, "# ADR-{number}: {title}", "# ADR-124: Y"),
        ("ADR-007: Use X", 7, "# ADR-{number:03d}: {title}", "# ADR-008: Y"),
        ("12. Use X", 12, "# {number}. {title}", "# 13. Y"),
        ("0012. Use X", 12, "# {number:04d}. {title}", "# 0013. Y"),
        ("ADR 0012 - Use X", 12, "# ADR {number:04d} - {title}", "# ADR 0013 - Y"),
        ("ADR-5 Use X", 5, "# ADR-{number} {title}", "# ADR-6 Y"),
        ("Use Postgres 15 for events", 3, "# {title}", "# Y"),
    ],
)
def test_the_h1_form_copies_the_newest_adrs_h1(
    tmp_path: Path, h1: str, file_number: int, form: str, rendered: str
) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, f"docs/adr/{file_number:04d}-a.md", f"# {h1}\n")
    style = adr_locate.folder_style(repo / "docs" / "adr")
    assert style.h1_form == form
    assert adr_locate.render_h1(style.h1_form, style.highest + 1, "Y") == rendered


def test_the_h1_form_ignores_headings_inside_fences_and_front_matter(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    text = (
        "---\ntitle: x\n# not this\n---\n\n```\n# ADR-1: not this\n## Fenced\n```\n\n"
        "# ADR-9: Real\n\n## Status\n\nok\n\n## Context\n\nok\n"
    )
    _adr(repo, "docs/adr/ADR-009-real.md", text)
    style = adr_locate.folder_style(repo / "docs" / "adr")
    assert style.h1_form == "# ADR-{number}: {title}"
    assert style.headings == ("Status", "Context")


def test_a_newest_adr_with_no_h2_headings_gets_the_nygard_set(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    _adr(repo, "docs/adr/ADR-004-a.md", "# ADR-4: Flat\n\nJust prose.\n")
    assert adr_locate.folder_style(repo / "docs" / "adr").headings == adr_locate.NYGARD_HEADINGS


def test_a_title_with_braces_renders_as_plain_text() -> None:
    form = "# ADR-{number}: {title}"
    assert adr_locate.render_h1(form, 5, "Use {braces} and {0}") == "# ADR-5: Use {braces} and {0}"
