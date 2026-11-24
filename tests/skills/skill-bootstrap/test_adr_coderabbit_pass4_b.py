"""Tests for CodeRabbit pass 4 on PR #7527, group B: decision-log keys, rule sections, ADR reads."""

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
# D4 (thread PRRT_kwDOQoWRls67QJRA): every entry with an id gets a title key
# ---------------------------------------------------------------------------


def test_a_unique_id_gets_a_title_key() -> None:
    entry = adr_log.LogEntry("D-7", PNPM, PNPM, f"{PNPM}\n\n{WHY}")

    assert adr_log._entry_keys([("decisions.md", entry)]) == [_key("D-7", PNPM)]


def test_adding_a_second_same_id_row_keeps_the_drafted_row_hidden(tmp_path: Path) -> None:
    adr = _cites(_key("D-7", PNPM))

    before, _ = _logged(tmp_path, _rows(PNPM), adr)
    after, dropped = _logged(tmp_path, _rows(PNPM, NODE), adr)

    assert before == []
    assert after == [_key("D-7", NODE)] and dropped["already_documented"] == 1


def test_deleting_one_of_two_same_id_rows_keeps_the_drafted_row_hidden(tmp_path: Path) -> None:
    adr = _cites(_key("D-7", PNPM))

    before, _ = _logged(tmp_path, _rows(PNPM, NODE), adr)
    after, dropped = _logged(tmp_path, _rows(PNPM), adr)

    assert before == [_key("D-7", NODE)]
    assert after == [] and dropped["already_documented"] == 1


def test_reordering_same_id_rows_with_distinct_titles_moves_no_key(tmp_path: Path) -> None:
    adr = _cites(_key("D-7", PNPM))

    forward, _ = _logged(tmp_path, _rows(PNPM, NODE), adr)
    backward, _ = _logged(tmp_path, _rows(NODE, PNPM), adr)

    assert forward == backward == [_key("D-7", NODE)]


def test_reordering_same_title_twins_keeps_one_hidden_and_the_same_ids(tmp_path: Path) -> None:
    # Same-title twins differ only by position, so the drafted key stays hidden and the other
    # twin keeps the one candidate id, whichever row comes first.
    key = _key("D-7", PNPM)
    one, two = f"## {PNPM}\n\nFirst. {WHY}\n\n", f"## {PNPM}\n\nSecond. {WHY}\n\n"

    forward, _ = _logged(tmp_path, one + two, _cites(key))
    backward, dropped = _logged(tmp_path, two + one, _cites(key))

    assert forward == backward == [f"{key}-2"] and dropped["already_documented"] == 1


def test_a_bare_id_hides_an_entry_only_while_the_id_is_unique(tmp_path: Path) -> None:
    unique, _ = _logged(tmp_path / "a", _rows(PNPM), "See D-7.")
    twins, _ = _logged(tmp_path / "b", _rows(PNPM, NODE), "See D-7.")
    cased, _ = _logged(tmp_path / "c", _rows(PNPM, "d-7 - Pin Node"), "See D-7.")

    assert unique == []
    assert twins == [_key("D-7", PNPM), _key("D-7", NODE)]
    assert len(cased) == 2


# ---------------------------------------------------------------------------
# B1: an ADR naming D-1.alpha does not hide D-1; D-1.md still does
# ---------------------------------------------------------------------------

_DOTTED_LEDGER = (
    "id: D-1 | status: test\nWe keep the queue on one host for now.\n\n"
    "id: D-1.alpha | status: test\nWe run the alpha build on a canary ring.\n"
)


def test_an_adr_naming_a_dotted_id_keeps_the_shorter_id_a_candidate(tmp_path: Path) -> None:
    found, _ = _logged(tmp_path, _DOTTED_LEDGER, "See D-1.alpha for the canary.")

    assert [key.split("--")[0] for key in found] == ["D-1"]


def test_an_adr_citing_a_dotted_key_keeps_the_shorter_id_a_candidate(tmp_path: Path) -> None:
    alpha = _key("D-1.alpha", "We run the alpha build on a canary ring.")

    found, _ = _logged(tmp_path, _DOTTED_LEDGER, _cites(alpha))

    assert [key.split("--")[0] for key in found] == ["D-1"]


def test_a_file_name_still_names_its_id() -> None:
    existing = adr_docs.ExistingAdrs([("a.md", "See D-1.md and auth.session.mdx.")])

    assert existing.names_id("D-1") and existing.names_id("auth.session")
    assert not existing.names_id("auth")


# ---------------------------------------------------------------------------
# B2: fenced lines are neither headings nor rule markers
# ---------------------------------------------------------------------------


def test_a_fenced_top_heading_does_not_cut_a_changelog_policy() -> None:
    text = (
        "## Deprecation policy\n\nWe deprecate in two steps.\n\n"
        "```sh\n# Set up the release\nmake release\n```\n\nText below the example stays.\n"
    )

    [section] = adr_docs.rule_sections("changelog", text)

    assert section.body.endswith("Text below the example stays.")


def test_a_changelog_policy_still_ends_at_a_release_heading() -> None:
    text = "## Versioning policy\n\nWe follow semver.\n\n# 1.2.0\n\n- Added x\n"

    assert adr_docs.rule_sections("changelog", text)[0].body == "We follow semver."


def test_a_fenced_h2_does_not_start_a_section() -> None:
    text = "## Commits\n\nYou must sign commits.\n\n~~~\n## Not a heading\n~~~\nAfter.\n"

    sections = adr_docs.split_into_sections(text)

    assert [heading for heading, _body in sections] == [None, "Commits"]
    assert sections[1][1].endswith("After.")


def test_a_rule_marker_inside_a_fence_does_not_make_a_rule() -> None:
    fenced = "## Conventions\n\n```\nyou must run make\n```\n"
    prose = "## Conventions\n\nYou must run make.\n"

    assert adr_docs.rule_sections("readme", fenced) == []
    assert adr_docs.rule_sections("contributing", fenced) == []
    assert len(adr_docs.rule_sections("readme", prose)) == 1


@pytest.mark.parametrize(
    ("text", "headings"),
    [
        ("```\n## A\n``` x\n## B\n````\n## C", [None, "C"]),  # an info string never closes
        ("~~~\n## A\n```\n## B\n~~~\n## C", [None, "C"]),  # the other mark never closes
        ("````\n## A\n```\n## B\n`````\n## C", [None, "C"]),  # shorter never closes
        ("    ```\n## A", [None, "A"]),  # four spaces of indent is not a fence
        ("   ```\n## A\n   ```\n## B", [None, "B"]),  # three spaces is
        ("```x```\n## A", [None, "A"]),  # a code span is not a fence
        ("```\n## A", [None]),  # an unclosed fence runs to the end
    ],
)
def test_fences_follow_commonmark(text: str, headings: list[str | None]) -> None:
    assert [heading for heading, _body in adr_docs.split_into_sections(text)] == headings


# ---------------------------------------------------------------------------
# B3: a leading dot is part of a decision-log id
# ---------------------------------------------------------------------------


def test_a_leading_dot_stays_in_an_adr_token() -> None:
    existing = adr_docs.ExistingAdrs([("a.md", "We cite .cache here.")])

    assert existing.names_id(".cache") and not existing.names_id("cache")


def test_a_drafted_dot_id_entry_is_not_offered_again(tmp_path: Path) -> None:
    ledger = "id: .cache | status: test\nWe keep the build cache on local disk.\n"
    key = _key(".cache", "We keep the build cache on local disk.")

    found, dropped = _logged(tmp_path, ledger, _cites(key))

    assert found == [] and dropped["already_documented"] == 1


# ---------------------------------------------------------------------------
# B4: a major-only version heading is a release, not policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("heading", ["v2 - Deprecation policy", "[v3] Versioning policy", "v2"])
def test_a_major_only_release_heading_is_not_policy(heading: str) -> None:
    assert not adr_docs.is_rule_section("changelog", heading, "x")


@pytest.mark.parametrize("heading", ["Deprecation policy", "v2a deprecation policy"])
def test_a_policy_heading_without_a_version_token_is_policy(heading: str) -> None:
    assert adr_docs.is_rule_section("changelog", heading, "x")


# ---------------------------------------------------------------------------
# B5: a pull request page compares without its query or fragment
# ---------------------------------------------------------------------------

PR = "https://github.com/acme/app/pull/42"


@pytest.mark.parametrize(
    ("adr", "candidate"),
    [
        (f"See {PR}.", f"{PR}?tab=conversation"),
        (f"See {PR}#issuecomment-9 here.", PR),
        (f"See {PR}/?x=1#y here.", f"{PR}#z"),
    ],
)
def test_a_pr_page_matches_without_query_or_fragment(adr: str, candidate: str) -> None:
    assert adr_docs.ExistingAdrs([("a.md", adr)]).names((), (candidate,), None)


@pytest.mark.parametrize(
    "candidate",
    [
        "https://github.com/acme/other/pull/42?tab=files",
        "https://gitlab.com/acme/app/pull/42",
        "https://github.com/acme/app/pull/421",
    ],
)
def test_a_pr_page_keeps_its_host_repository_and_number(candidate: str) -> None:
    assert not adr_docs.ExistingAdrs([("a.md", f"See {PR}?a=1.")]).names((), (candidate,), None)


def test_other_urls_still_compare_with_their_query() -> None:
    existing = adr_docs.ExistingAdrs([("a.md", "See https://example.com/doc?a=1.")])

    assert not existing.names((), ("https://example.com/doc",), None)
    assert existing.names((), ("https://example.com/doc?a=1",), None)


# ---------------------------------------------------------------------------
# B6: a later invalid date does not hide an earlier valid one
# ---------------------------------------------------------------------------


def test_the_first_valid_value_of_a_repeated_date_key_wins() -> None:
    assert adr_log.entry_date("D-1\ndate: 2026-03-04 | date: TBD") == "2026-03-04"


def test_date_keeps_priority_over_decided_and_modified() -> None:
    text = "D-1\nmodified: 2026-01-01 | decided: 2026-02-02 | date: 2026-03-03 | date: TBD"

    assert adr_log.entry_date(text) == "2026-03-03"


# ---------------------------------------------------------------------------
# B7: a bare id keeps its numeric dotted segments
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("log", "ident"),
    [
        (f"## D-1.2 - Retry policy\n\n{WHY}\n", "D-1.2"),
        (f"D-1.2.3: Retry policy\n\n{WHY}\n", "D-1.2.3"),
        (f"## D-1. Retry policy\n\n{WHY}\n", "D-1"),
        (f"D-1.x Retry policy\n\n{WHY}\n", "D-1"),
    ],
)
def test_a_bare_id_keeps_its_dotted_number(log: str, ident: str) -> None:
    assert [entry.id for entry in adr_log.split_decision_log(log)] == [ident]


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
