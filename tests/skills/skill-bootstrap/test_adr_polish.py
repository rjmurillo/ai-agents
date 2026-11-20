"""Draft polish: RFC folders take no drafts, titles lose commit syntax, excerpts lose PR forms."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import adr_locate
import adr_scan
import bootstrap_adr
import pytest
from adr_helpers import commit, new_repo, write
from adr_scan import ConfigError


def _candidate(title: str, kind: str = "commit") -> dict[str, Any]:
    return {
        "id": "c-1234567",
        "kind": kind,
        "title": title,
        "reason": None,
        "excerpt": title,
        "date": "2026-11-02",
        "source": {"sha": "1234567" + "0" * 33},
    }


def _scan_file(tmp_path: Path, repo: Path, candidate: dict[str, Any]) -> str:
    path = tmp_path / "scan.json"
    path.write_text(json.dumps({"repo": str(repo), "candidates": [candidate]}), encoding="utf-8")
    return str(path)


def test_an_rfc_folder_is_located_but_is_not_a_draft_target(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-use-postgres.md", "# 1. Use postgres\n")
    write(repo, "docs/rfcs/0001-new-api.md", "# RFC 1: New API\n")

    result = adr_locate.locate(repo)

    assert [(f["path"], f["draft_target"]) for f in result["folders"]] == [
        ("docs/adr", True),
        ("docs/rfcs", False),
    ]
    assert (result["primary"], result["next_number"]) == ("docs/adr", 2)


def test_draft_refuses_an_rfc_folder_in_the_repository(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/rfcs/0001-new-api.md", "# RFC 1: New API\n")
    commit(repo, "Initial work")
    scan = _scan_file(tmp_path, repo, _candidate("Adopt the queue"))

    with pytest.raises(ConfigError, match="not an ADR folder that takes drafts"):
        bootstrap_adr.draft(scan, "c-1234567", str(repo / "docs" / "rfcs"), "Proposed")

    assert sorted(p.name for p in (repo / "docs" / "rfcs").iterdir()) == ["0001-new-api.md"]


@pytest.mark.parametrize(
    ("kind", "title", "expected"),
    [
        ("commit", "feat(skills)!: adopt typed artifacts (#7496)", "Adopt typed artifacts"),
        ("pr", "refactor: replace the queue with a log", "Replace the queue with a log"),
        ("commit", "Use postgres for sessions", "Use postgres for sessions"),
        ("decision-log", "D-001: never retry a payment", "D-001: never retry a payment"),
        ("commit", "feat: (#12)", "feat: (#12)"),
    ],
)
def test_the_adr_title_drops_commit_syntax_only(kind: str, title: str, expected: str) -> None:
    assert bootstrap_adr.adr_title(kind, title) == expected


def test_a_draft_h1_and_file_name_use_the_cleaned_title(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-use-postgres.md", "# 1. Use postgres\n")
    commit(repo, "Initial work")
    scan = _scan_file(tmp_path, repo, _candidate("feat(api): adopt grpc (#40)"))

    result = bootstrap_adr.draft(scan, "c-1234567", str(repo / "docs" / "adr"), "Proposed")

    assert Path(result["path"]).name == "0002-adopt-grpc.md"
    assert Path(result["path"]).read_text(encoding="utf-8").startswith("# 2. Adopt grpc\n")


def test_an_excerpt_drops_template_comments_and_checklist_lines() -> None:
    body = (
        "## Summary\n\n<!-- Describe the change -->\nWe adopt grpc because REST\n"
        "cannot stream.\n\n## Checklist\n\n- [x] Tests added\n- [ ] Docs updated\n"
    )

    excerpt = adr_scan._excerpt("Adopt grpc", body)

    assert "<!--" not in excerpt and "[x]" not in excerpt and "[ ]" not in excerpt
    assert "We adopt grpc because REST" in excerpt


def test_an_excerpt_of_many_unclosed_comment_openers_returns_quickly() -> None:
    body = "<!--" * 50_000
    assert len(body) == 200_000

    started = time.monotonic()
    excerpt = adr_scan._excerpt("Adopt grpc", body)
    elapsed = time.monotonic() - started

    assert len(excerpt) <= adr_scan.EXCERPT_CHARS
    assert excerpt.startswith("Adopt grpc")
    assert elapsed < 2.0
