"""Tests for CodeRabbit pass 4 on PR #7527, group B: decision-log keys, rule sections, ADR reads."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import adr_docs
import adr_locate
import adr_log
import pytest
from adr_helpers import new_repo, write

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
