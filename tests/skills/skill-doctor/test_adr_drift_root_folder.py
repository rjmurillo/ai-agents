"""adr_drift.py when the ADR folder is the repository root: no path is empty, `./`, or `/` led."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import report_adr
from adr_drift_helpers import (
    adr_text,
    commit,
    init_repo,
    kinds,
    run_cli,
    scan,
    symlink_or_skip,
)
from render_report import esc

PATH_KEYS = frozenset({"path", "paths", "adr", "from"})
SUPERSEDED = "adr-superseded-by-commit"


def _root_files() -> dict[str, str]:
    return {
        "ADR-001-first.md": adr_text(1, body="See [gone](ADR-009-gone.md) and `src/gone.py`."),
        "ADR-003-third.md": adr_text(3),
        "ADR-003-dup.md": adr_text(3),
        "ADR-notes.md": "# notes\n",
        "2024-01-01-dated.md": "# dated\n",
        "ADR-004-old.mdx": "old\n",
        "ADR-template.md": "# template\n",
    }


def _marker_layout(repo: Path) -> None:
    commit(repo, {**_root_files(), ".adr-dir": ".\n"}, "docs: root adr folder")


def _symlink_layout(repo: Path) -> None:
    (repo / "docs").mkdir()
    symlink_or_skip(repo / "docs" / "adr", Path(".."))
    commit(repo, _root_files(), "docs: root adr folder behind a known name")


LAYOUTS = [_marker_layout, _symlink_layout]


def _file_paths(node: Any, key: str = "") -> list[str]:
    """Every string a scan result holds under a file-path key, at any depth."""
    if isinstance(node, dict):
        return [p for k, v in node.items() for p in _file_paths(v, k)]
    if isinstance(node, list):
        return [p for item in node for p in _file_paths(item, key)]
    return [node] if isinstance(node, str) and key in PATH_KEYS else []


def _built(tmp_path: Path, layout: Any) -> Path:
    repo = init_repo(tmp_path / "repo")
    layout(repo)
    return repo


def _bad(path: str) -> bool:
    return path == "" or path.startswith(("/", "./"))


@pytest.mark.parametrize("layout", LAYOUTS)
def test_no_file_path_in_a_root_folder_scan_is_empty_or_dot_slash_or_absolute(
    tmp_path, capsys, layout
):
    result = scan(capsys, _built(tmp_path, layout))

    files = [
        p
        for f in result["findings"]
        if f["kind"] != "adr-number-gap"
        for p in _file_paths(f["evidence"])
    ]
    rejected = [r["path"] for r in result["locate"]["rejected"]]
    templates = [m.removeprefix("template:") for m in result["locate"]["markers"] if ":" in m]

    assert files and not [p for p in files + rejected + templates if _bad(p)]
    assert sorted(rejected) == ["2024-01-01-dated.md", "ADR-004-old.mdx"]


@pytest.mark.parametrize("layout", LAYOUTS)
def test_unparseable_name_path_is_the_bare_file_name(tmp_path, capsys, layout):
    found = kinds(scan(capsys, _built(tmp_path, layout)), "adr-unparseable-name")

    assert [f["evidence"]["path"] for f in found] == ["ADR-notes.md"]
    assert "Rename ADR-notes.md to" in found[0]["suggested_fix"]


@pytest.mark.parametrize("layout", LAYOUTS)
def test_gap_and_locate_name_the_root_folder_as_a_dot(tmp_path, capsys, layout):
    result = scan(capsys, _built(tmp_path, layout))

    gap = kinds(result, "adr-number-gap")
    assert [f["evidence"]["path"] for f in gap] == ["."]
    assert [d["path"] for d in result["locate"]["adr_dirs"]] == ["."]
    assert result["locate"]["primary"] == "."


@pytest.mark.parametrize("layout", LAYOUTS)
def test_locate_command_prints_a_dot_primary_for_the_root_folder(tmp_path, capsys, layout):
    repo = _built(tmp_path, layout)

    code, out, err = run_cli(capsys, "locate", "--repo", str(repo))

    located = json.loads(out)
    assert code == 0, err
    assert located["primary"] == "." and located["adr_dirs"][0]["path"] == "."


def test_a_template_in_a_known_folder_that_is_the_root_has_a_bare_marker(tmp_path, capsys):
    repo = _built(tmp_path, _symlink_layout)

    markers = scan(capsys, repo)["locate"]["markers"]

    assert "template:ADR-template.md" in markers


@pytest.mark.parametrize("layout", LAYOUTS)
def test_a_commit_that_edits_a_root_level_adr_is_not_a_supersession_candidate(
    tmp_path, capsys, layout
):
    repo = _built(tmp_path, layout)
    commit(
        repo,
        {"ADR-001-first.md": adr_text(1, body="Edited.")},
        "refactor: replace the approach in ADR-001 with a queue",
    )

    assert kinds(scan(capsys, repo), SUPERSEDED) == []


def test_a_commit_that_only_mentions_a_root_level_adr_is_still_a_candidate(tmp_path, capsys):
    repo = _built(tmp_path, _symlink_layout)
    commit(repo, {"a.txt": "1"}, "refactor: replace the approach in ADR-001 with a queue")

    assert len(kinds(scan(capsys, repo), SUPERSEDED)) == 1


def test_the_html_report_renders_the_gap_location(tmp_path, capsys):
    repo = _built(tmp_path, _marker_layout)
    gap = kinds(scan(capsys, repo), "adr-number-gap")[0]
    resolved = {"repos": [{"repo": "r", "head": "h", "examined": 1, "truncated": False}]}
    resolved["repos"][0]["findings"] = [gap]

    html = report_adr.render_adr_drift({"adr_drift": resolved}, esc)

    assert "<code>.</code>" in html


def test_a_non_root_folder_keeps_its_slash_joined_paths(tmp_path, capsys):
    repo = init_repo(tmp_path / "repo")
    files = {"docs/adr/ADR-001-a.md": adr_text(1), "docs/adr/ADR-003-b.md": adr_text(3)}
    files["docs/adr/ADR-notes.md"] = "# notes\n"
    commit(repo, files, "docs: adrs")

    result = scan(capsys, repo)

    assert kinds(result, "adr-number-gap")[0]["evidence"]["path"] == "docs/adr"
    assert kinds(result, "adr-unparseable-name")[0]["evidence"]["path"] == "docs/adr/ADR-notes.md"
    assert result["locate"]["primary"] == "docs/adr"
