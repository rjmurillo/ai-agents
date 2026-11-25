"""Tests for CodeRabbit pass 4 on PR #7527, group B, part 2."""

from __future__ import annotations

import os
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

import adr_docs
import adr_locate
import adr_log
import adr_scan
import adr_write
import pytest
from adr_helpers import commit, git, new_repo, write

WHY = "Because the team already runs it in production and a second system needs a second on-call."
PNPM, NODE = "D-7 - Use pnpm", "D-7 - Pin Node"


def _key(ident: str, title: str) -> str:
    return f"{ident}--{sha256(title.encode()).hexdigest()[:8]}"


def _rows(*titles: str) -> str:
    return "".join(f"## {title}\n\n{WHY}\n\n" for title in titles)


def _logged(root: Path, log: str, *adrs: str) -> tuple[list[str], dict[str, int]]:
    """The entry keys ``log_candidates`` offers for ``log``, given ADRs with these texts."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "decisions.md").write_text(log, encoding="utf-8")
    dropped = dict.fromkeys(adr_docs.DROP_KEYS, 0)
    existing = adr_docs.ExistingAdrs((f"{n}.md", text) for n, text in enumerate(adrs))
    found, _files, _skipped = adr_log.log_candidates(root, existing, dropped)
    return [c["source"]["entry_id"] for c in found], dropped


def _cites(key: str) -> str:
    return f"# 1. Drafted\n\nDecided in decisions.md (entry {key})\n"


# ---------------------------------------------------------------------------
# B1: an ADR naming D-1.alpha does not hide D-1; D-1.md still does
# ---------------------------------------------------------------------------

_DOTTED_LEDGER = (
    "id: D-1 | status: test\nWe keep the queue on one host for now.\n\n"
    "id: D-1.alpha | status: test\nWe run the alpha build on a canary ring.\n"
)


# ---------------------------------------------------------------------------
# B5: a pull request page compares without its query or fragment
# ---------------------------------------------------------------------------

PR = "https://github.com/acme/app/pull/42"


# ---------------------------------------------------------------------------
# B10, B20: the ADR text cap is strict, and an exact fit is kept
# ---------------------------------------------------------------------------


def _two_adrs(tmp_path: Path) -> tuple[Path, int]:
    repo = new_repo(tmp_path / "r")
    for n in (1, 2):
        write(repo, f"docs/adr/000{n}-x.md", f"# {n}. X\n" + "y" * 30)
    return repo, len("# 1. X\n") + 30


def _read_all(repo: Path) -> tuple[list[str], adr_locate.AdrTally]:
    tally = adr_locate.AdrTally()
    return [rel for rel, _text in adr_locate.read_adr_texts(repo, tally=tally)], tally


# ---------------------------------------------------------------------------
# B18: a folder reached through an RFC alias takes no draft
# ---------------------------------------------------------------------------


def _aliased(tmp_path: Path, alias: str, real: str) -> Path:
    repo = new_repo(tmp_path / "r")
    write(repo, f"{real}/0001-x.md", "# 1. X\n\n## Context\n")
    try:
        (repo / alias).parent.mkdir(parents=True, exist_ok=True)
        (repo / alias).symlink_to(repo / real, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create a symlink here")
    return repo


def test_an_adr_naming_d_1_does_not_hide_d_1_2(tmp_path: Path) -> None:
    found, _ = _logged(tmp_path, _rows("D-1.2 - Retry policy"), "See D-1.")

    assert found == [_key("D-1.2", "D-1.2 - Retry policy")]


def test_an_adr_naming_d_1_2_hides_it(tmp_path: Path) -> None:
    found, dropped = _logged(tmp_path, _rows("D-1.2 - Retry policy"), "See D-1.2.")

    assert found == [] and dropped["already_documented"] == 1


def test_the_bare_id_patterns_stay_linear_on_long_dotted_runs() -> None:
    line = "D-1" + ".1" * 32_768 + "x"
    started = time.perf_counter()
    adr_log.split_decision_log(f"{line}\n## {line}\n")
    assert time.perf_counter() - started < 0.5


# ---------------------------------------------------------------------------
# B8, B9: immutable records use slots
# ---------------------------------------------------------------------------


def test_immutable_records_have_no_instance_dict(tmp_path: Path) -> None:
    records: list[Any] = [
        adr_locate.AdrFile("0001-x.md", 1, "0001", ""),
        adr_locate.folder_style(tmp_path),
        adr_log.LogEntry("D-1", None, "t", "t"),
    ]

    assert all(not hasattr(record, "__dict__") for record in records)
    tally = adr_locate.AdrTally()
    tally.read = 1
    assert tally.read == 1


def test_two_files_that_fit_the_text_cap_exactly_are_both_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, size = _two_adrs(tmp_path)
    monkeypatch.setattr(adr_locate, "MAX_ADR_CHARS", 2 * size)

    read, tally = _read_all(repo)

    assert len(read) == 2 and (tally.read, tally.skipped, tally.cut) == (2, 0, False)


def test_a_file_that_would_cross_the_text_cap_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, size = _two_adrs(tmp_path)
    monkeypatch.setattr(adr_locate, "MAX_ADR_CHARS", 2 * size - 1)

    read, tally = _read_all(repo)

    assert read == ["docs/adr/0002-x.md"] and (tally.read, tally.skipped, tally.cut) == (1, 1, True)


def test_the_scan_reports_truncation_when_the_last_file_would_cross_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, size = _two_adrs(tmp_path)
    commit(repo, "Initial work")
    monkeypatch.setattr(adr_locate, "MAX_ADR_CHARS", 2 * size - 1)

    assert adr_scan.scan(repo, "HEAD", 10, None, None)["adr_corpus_truncated"] is True


# ---------------------------------------------------------------------------
# B11, B15: a backtick code span on its own line opens no fence
# ---------------------------------------------------------------------------


def test_a_code_span_line_does_not_hide_the_next_log_entry() -> None:
    log = f"## D-1 - A\n\n```example```\n\n{WHY}\n\n## D-2 - B\n\n{WHY}\n"

    assert [entry.id for entry in adr_log.split_decision_log(log)] == ["D-1", "D-2"]


def test_a_code_span_line_does_not_hide_a_date() -> None:
    assert adr_log.entry_date("D-1\n```x```\ndate: 2026-03-04") == "2026-03-04"


def test_a_tilde_info_string_may_hold_a_backtick() -> None:
    log = f"## D-1 - A\n\n~~~ `x`\n## D-2 - hidden\n~~~\n\n{WHY}\n"

    assert [entry.id for entry in adr_log.split_decision_log(log)] == ["D-1"]


def test_a_code_span_line_does_not_hide_adr_headings(tmp_path: Path) -> None:
    write(tmp_path, "0001-x.md", "# 1. X\n\n```example```\n\n## Background\n\n## Outcome\n")

    assert adr_locate.folder_style(tmp_path).headings == ("Background", "Outcome")


# ---------------------------------------------------------------------------
# B12: a ledger record keeps its id-less subsections
# ---------------------------------------------------------------------------


def test_a_ledger_record_keeps_its_rationale_section() -> None:
    log = (
        "# Ledger\n\nid: D-7 | status: test\nWe chose the x runtime.\n\n### Rationale\n\n"
        "Because it is fast in CI runs.\n\nid: D-8 | status: test\nWe keep Postgres as is.\n"
    )

    entries = adr_log.split_decision_log(log)

    assert [entry.id for entry in entries] == ["D-7", "D-8"]
    assert "Because it is fast" in entries[0].text


def test_a_numbered_peer_heading_still_ends_a_ledger_record() -> None:
    log = f"id: D-7 | status: test\nWe chose x.\n\n## D-8 - Keep Postgres\n\n{WHY}\n"

    assert [entry.id for entry in adr_log.split_decision_log(log)] == ["D-7", "D-8"]


# ---------------------------------------------------------------------------
# B13: symlinked logs take no slot from a real log
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_symlinked_logs_do_not_displace_a_real_log(tmp_path: Path) -> None:
    target = write(tmp_path, "notes/x.md", _rows("D-9 - Linked"))
    try:
        for n in range(adr_log.MAX_LOG_FILES):
            (tmp_path / f"a{n:02d}-ledger.md").symlink_to(target)
    except OSError:
        pytest.skip("cannot create a symlink here")

    found, _ = _logged(tmp_path, _rows("D-1 - Real"))

    assert adr_log.find_log_files(tmp_path) == ["decisions.md"]
    assert found == [_key("D-1", "D-1 - Real")]


# ---------------------------------------------------------------------------
# B14: a broken ADR folder hint is skipped
# ---------------------------------------------------------------------------


def test_a_folder_hint_that_cannot_resolve_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(tmp_path, ".adr-dir", "loop\n")
    write(tmp_path, "docs/adr/0001-x.md", "# 1. X\n")
    real = Path.resolve

    def resolve(self: Path, strict: bool = False) -> Path:
        if self.name == "loop":
            raise RuntimeError("Symlink loop from 'loop'")  # Python 3.10 to 3.12
        return real(self, strict)

    monkeypatch.setattr(Path, "resolve", resolve)

    assert adr_locate.locate_folders(tmp_path)[0] == [("docs/adr", "known")]


# ---------------------------------------------------------------------------
# B16: a literal trailing hash stays in an ADR heading
# ---------------------------------------------------------------------------


def test_only_a_closing_marker_leaves_an_adr_heading(tmp_path: Path) -> None:
    text = "# 1. X\n\n## C#\n\n## F# ##\n\n## Title ##  \n\n== Plain ==\n\n## ##\n"
    write(tmp_path, "0001-x.md", text)

    assert adr_locate.folder_style(tmp_path).headings == ("C#", "F#", "Title", "Plain")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_an_rfc_alias_is_read_but_takes_no_draft(tmp_path: Path) -> None:
    repo = _aliased(tmp_path, "rfcs", "design/proposals")

    payload = adr_locate.locate(repo)

    assert [(f["path"], f["draft_target"]) for f in payload["folders"]] == [("rfcs", False)]
    assert payload["primary"] is None
    assert [rel for rel, _text in adr_locate.read_adr_texts(repo)] == ["rfcs/0001-x.md"]
    for out in (repo / "rfcs", repo / "design" / "proposals"):
        with pytest.raises(adr_scan.ConfigError, match="not an ADR folder that takes drafts"):
            adr_write.gate_target(out)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_an_adr_dir_spelling_of_an_rfc_alias_takes_no_draft(tmp_path: Path) -> None:
    repo = _aliased(tmp_path, "notes/rfc", "design/proposals")
    write(repo, ".adr-dir", "./notes/rfc/\n")

    payload = adr_locate.locate(repo)

    assert [(f["path"], f["draft_target"]) for f in payload["folders"]] == [("notes/rfc", False)]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_a_non_rfc_alias_still_takes_drafts(tmp_path: Path) -> None:
    repo = _aliased(tmp_path, "docs/adr", "design/records")

    payload = adr_locate.locate(repo)

    assert payload["primary"] == "design/records"
    assert adr_write.gate_target(repo / "docs" / "adr")[1] == repo / "design" / "records"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlinks")
def test_a_known_folder_named_first_keeps_drafts_when_an_rfc_alias_points_at_it(
    tmp_path: Path,
) -> None:
    repo = _aliased(tmp_path, "rfcs", "docs/adr")

    assert adr_locate.locate(repo)["primary"] == "docs/adr"


# ---------------------------------------------------------------------------
# B19: YAML front matter comes off before fences are read
# ---------------------------------------------------------------------------


def test_a_fence_inside_front_matter_does_not_hide_adr_headings(tmp_path: Path) -> None:
    text = "---\nnotes: |\n  ```\n  example\n---\n# 1. X\n\n## Background\n\n```\n## Hidden\n```\n"
    write(tmp_path, "0001-x.md", text)

    assert adr_locate.folder_style(tmp_path).headings == ("Background",)


# ---------------------------------------------------------------------------
# Hostile input: the fence tracker and the version pattern stay linear
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "```" + "`" * 65_536,
        "```" + " " * 65_536 + "x",
        "   " + "~" * 65_536 + "`",
        ("```\n" + "#" * 64 + "\n") * 1024,
    ],
)
def test_the_fence_tracker_is_linear_on_hostile_input(text: str) -> None:
    started = time.perf_counter()
    adr_docs.split_into_sections(text)
    adr_docs.lines_outside_fences(text)
    adr_log.split_decision_log(text)
    assert time.perf_counter() - started < 0.5


def test_the_release_heading_pattern_is_linear_on_long_digit_runs() -> None:
    started = time.perf_counter()
    adr_docs.is_rule_section("changelog", "v" + "9" * 65_536 + "x policy", "x")
    adr_docs.is_rule_section("changelog", "[" + "9." * 32_768 + "policy", "x")
    assert time.perf_counter() - started < 0.5


@pytest.mark.parametrize(
    "text",
    [
        "a." * 32_768 + "md",
        "D-1" + ".md" * 21_845 + "x",
        "https://github.com/" + "a/" * 32_768 + "pull/1?x",
        "https://github.com/a/b/pull/" + "9" * 65_536 + "/x",
    ],
)
def test_the_id_and_url_identity_patterns_are_linear(text: str) -> None:
    started = time.perf_counter()
    existing = adr_docs.ExistingAdrs([("a.md", text)])
    existing.names((), (text,), None)
    assert time.perf_counter() - started < 0.5


def test_a_scan_hides_a_pr_whose_export_url_has_a_query(tmp_path: Path) -> None:
    origin = "https://github.com/o/r"
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", f"# 1. First\n\nDecided in {origin}/pull/42\n")
    commit(repo, "Initial work")
    git(repo, "remote", "add", "origin", f"{origin}.git")
    row = {
        "number": 42,
        "title": "Adopt Postgres instead of MySQL",
        "body": WHY,
        "url": f"{origin}/pull/42?tab=conversation",
        "merged_at": "2026-03-04T10:00:00Z",
        "author": {"login": "ada"},
    }

    payload = adr_scan.scan(repo, "HEAD", 10, None, [row])

    assert payload["candidates"] == [] and payload["dropped"]["already_documented"] == 1
