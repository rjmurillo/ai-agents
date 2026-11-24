"""Review round 2 tests for the draft renderer: items 1, 2, 14 and 15."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import adr_locate
import bootstrap_adr
import pytest
from adr_helpers import commit, new_repo, run_cli, write
from draft_helpers import _cand, _scan_file, _text

_SHA40 = "1234567" + "0" * 33


def _adr_repo(path: Path) -> Path:
    repo = new_repo(path)
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    commit(repo, "Initial work")
    return repo


def _draft(tmp_path: Path, repo: Path, **cand: Any) -> dict[str, Any]:
    scan = _scan_file(tmp_path, repo, _cand(**cand))
    result: dict[str, Any] = bootstrap_adr.draft(
        scan, cand.get("id", "c-1234567"), str(repo / "docs" / "adr"), "Proposed"
    )
    return result


def _headings(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.startswith("## ")]


def _fences(text: str) -> list[str]:
    return [line for line in text.split("\n") if re.match(r"\s{0,3}(`{3,}|~{3,})", line)]


# ---------------------------------------------------------------------------
# Item 1: a title that starts with Markdown syntax stays text
# ---------------------------------------------------------------------------


def test_a_title_that_starts_with_a_heading_mark_is_not_a_heading(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    text = _text(_draft(tmp_path, repo, title="## Status Accepted"))
    assert _headings(text) == ["## Status", "## Context", "## Decision"]
    assert "\\## Status Accepted" in text


def test_a_title_that_starts_with_a_fence_does_not_open_one(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    text = _text(_draft(tmp_path, repo, title="```python adopt the thing"))
    assert _fences(text) == []
    assert _headings(text) == ["## Status", "## Context", "## Decision"]


def test_a_title_that_starts_with_a_tilde_fence_does_not_open_one(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    text = _text(_draft(tmp_path, repo, title="~~~ adopt the thing"))
    assert _fences(text) == []


def test_a_title_that_starts_with_a_quote_mark_is_not_a_block_quote(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    text = _text(_draft(tmp_path, repo, title="> quote the policy"))
    decision = text.split("## Decision\n\n", 1)[1]
    assert decision.startswith("\\> quote the policy\n")


@pytest.mark.parametrize(
    ("title", "escaped"),
    [
        ("- adopt x", "\\- adopt x"),
        ("+ adopt x", "\\+ adopt x"),
        ("* adopt x", "\\* adopt x"),
        ("=== adopt x", "\\=== adopt x"),
        ("| adopt | x |", "\\| adopt | x |"),
        ("12. adopt x", "12\\. adopt x"),
        ("3) adopt x", "3\\) adopt x"),
    ],
)
def test_every_leading_control_character_is_escaped(
    tmp_path: Path, title: str, escaped: str
) -> None:
    repo = _adr_repo(tmp_path / "r")
    text = _text(_draft(tmp_path, repo, title=title))
    decision = text.split("## Decision\n\n", 1)[1]
    assert decision.startswith(escaped)


@pytest.mark.parametrize(
    "title", ["Adopt x", "2026 plan for x", "x - y", "1.5x speedup", "3.11 migration"]
)
def test_a_plain_title_is_left_alone(tmp_path: Path, title: str) -> None:
    repo = _adr_repo(tmp_path / "r")
    text = _text(_draft(tmp_path, repo, title=title))
    decision = text.split("## Decision\n\n", 1)[1]
    assert decision.startswith(title[:1].upper() + title[1:] + "\n")


def test_the_prepare_candidate_docstring_makes_no_claim_the_code_breaks() -> None:
    doc = bootstrap_adr._prepare_candidate.__doc__ or ""
    assert "so neither can start a heading" not in doc


# ---------------------------------------------------------------------------
# Item 2: source fields that reach the link are one line and well formed
# ---------------------------------------------------------------------------

_FORGED = "x\n\n## Forged\n\nmore"


def test_a_source_sha_with_a_line_break_cannot_start_a_heading(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    result = _draft(tmp_path, repo, source={"sha": _FORGED, "url": None})
    assert _headings(_text(result)) == ["## Status", "## Context", "## Decision"]


def test_a_source_file_with_a_line_break_cannot_start_a_heading(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    result = _draft(
        tmp_path,
        repo,
        id="log-D-1",
        kind="decision-log",
        source={"file": _FORGED, "entry_id": "D-1"},
    )
    assert _headings(_text(result)) == ["## Status", "## Context", "## Decision"]


def test_a_source_entry_id_with_a_line_break_cannot_start_a_heading(tmp_path: Path) -> None:
    repo = _adr_repo(tmp_path / "r")
    result = _draft(
        tmp_path,
        repo,
        id="log-D-1",
        kind="decision-log",
        source={"file": "docs/decisions.md", "entry_id": _FORGED},
    )
    assert _headings(_text(result)) == ["## Status", "## Context", "## Decision"]


def test_a_source_url_with_a_line_break_is_dropped_before_the_draft() -> None:
    prepared = bootstrap_adr._prepare_candidate(
        _cand(source={"sha": _SHA40, "url": "https://x.example/a\n## Forged"})
    )
    assert "url" not in prepared["source"]


def test_a_source_pr_url_with_a_line_break_is_dropped_before_the_draft() -> None:
    prepared = bootstrap_adr._prepare_candidate(
        _cand(source={"sha": _SHA40, "pr_url": "https://x.example/p\n## Forged"})
    )
    assert "pr_url" not in prepared["source"]


def test_a_source_url_that_is_not_https_is_dropped() -> None:
    prepared = bootstrap_adr._prepare_candidate(
        _cand(source={"url": "javascript:alert(1)", "pr_url": "http://x.example/p"})
    )
    assert "url" not in prepared["source"] and "pr_url" not in prepared["source"]


def test_a_source_sha_that_is_not_full_hex_is_dropped() -> None:
    for sha in ("abc1234", "g" * 40, _SHA40 + "0", _FORGED):
        prepared = bootstrap_adr._prepare_candidate(_cand(source={"sha": sha}))
        assert "sha" not in prepared["source"], sha


def test_a_clean_source_keeps_its_fields() -> None:
    source = {
        "sha": _SHA40,
        "url": "https://github.com/o/r/commit/1234567",
        "pr_url": "https://github.com/o/r/pull/3",
        "pr_number": 3,
    }
    assert bootstrap_adr._prepare_candidate(_cand(source=dict(source)))["source"] == source


def test_a_sixty_four_hex_sha_is_kept() -> None:
    sha = "ab" * 32
    assert bootstrap_adr._prepare_candidate(_cand(source={"sha": sha}))["source"] == {"sha": sha}


def test_other_source_strings_lose_their_line_breaks() -> None:
    prepared = bootstrap_adr._prepare_candidate(
        _cand(source={"file": "docs/a\nb.md", "entry_id": "D-1\n## x"})
    )
    assert prepared["source"] == {"file": "docs/a b.md", "entry_id": "D-1 ## x"}


# ---------------------------------------------------------------------------
# Item 14: the scan file's repository gates nothing
# ---------------------------------------------------------------------------


def test_a_scan_file_with_no_repository_string_is_still_refused(tmp_path: Path) -> None:
    path = tmp_path / "scan.json"
    path.write_text(json.dumps({"repo": 7, "candidates": [_cand()]}), encoding="utf-8")
    code, payload = run_cli(
        "draft", "--scan", str(path), "--id", "c-1234567", "--out", str(tmp_path / "s")
    )
    assert code == 2 and payload["error"] == "config"


# ---------------------------------------------------------------------------
# Item 15: the exists payload says whether a file was written
# ---------------------------------------------------------------------------


def test_an_existing_target_reports_written_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _adr_repo(tmp_path / "r")
    folder = repo / "docs" / "adr"
    stale = adr_locate.folder_style(folder)
    write(repo, "docs/adr/0002-replace-eo-inference-with-the-per-copy-engine.md", "mine\n")
    monkeypatch.setattr(bootstrap_adr, "folder_style", lambda _dir: stale)
    scan = _scan_file(tmp_path, repo, _cand())
    args = ["draft", "--scan", scan, "--id", "c-1234567", "--out", str(folder)]
    assert bootstrap_adr.main(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "exists" and payload["written"] is False


def test_a_twin_after_the_write_reports_written_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _adr_repo(tmp_path / "r")
    scan = _scan_file(tmp_path, repo, _cand())
    real = bootstrap_adr.create_new

    def racing(target: Path, data: bytes) -> None:
        real(target, data)
        (target.parent / "0002-other-decision.md").write_text("# 2. Other\n", encoding="utf-8")

    monkeypatch.setattr(bootstrap_adr, "create_new", racing)
    with pytest.raises(bootstrap_adr.ExistsError) as caught:
        bootstrap_adr.draft(scan, "c-1234567", str(repo / "docs" / "adr"), "Proposed")
    assert caught.value.written is True and caught.value.others == ["0002-other-decision.md"]


def test_the_exists_payload_carries_written_through_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _adr_repo(tmp_path / "r")
    scan = _scan_file(tmp_path, repo, _cand())
    real = bootstrap_adr.create_new

    def racing(target: Path, data: bytes) -> None:
        real(target, data)
        (target.parent / "0002-other-decision.md").write_text("# 2. Other\n", encoding="utf-8")

    monkeypatch.setattr(bootstrap_adr, "create_new", racing)
    args = ["draft", "--scan", scan, "--id", "c-1234567", "--out", str(repo / "docs" / "adr")]
    assert bootstrap_adr.main(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "exists" and payload["written"] is True
