"""Tests for adr_reason: inputs that are not a reason, and importer metadata.

Cases port tests/reason-extract.test.ts of align-cli (MIT, Copyright (c) 2026 Align Tech
Ltd, see LICENSE-align): same inputs, same expected outputs, titles follow upstream. A
wrong "reason" is worse than none, so every shape that is not a reason must give None.
"""

from __future__ import annotations

import adr_shape
import pytest
from adr_reason import extract_reason
from reason_helpers import full

# ---------------------------------------------------------------------------
# what is NOT a reason gives None
# ---------------------------------------------------------------------------


def test_empty_whitespace_and_none_bodies() -> None:
    assert extract_reason("x", "") is None
    assert extract_reason("x", "  \n\n ") is None
    assert extract_reason("x", None) is None


def test_a_body_that_is_only_trailers() -> None:
    body = (
        "Co-authored-by: Ann <ann@x.test>\nSigned-off-by: Bob <bob@x.test>\n"
        "Reviewed-by: Cy <cy@x.test>"
    )
    assert extract_reason("x", body) is None


def test_trailers_are_removed_next_to_a_real_reason() -> None:
    body = (
        "We did it because it was slow.\n\nCo-authored-by: Ann <ann@x.test>\n"
        "Signed-off-by: because to avoid <b@x.test>"
    )
    assert extract_reason("x", body) == "We did it because it was slow."


def test_fixes_closes_refs_lines_are_not_reasons() -> None:
    assert extract_reason("x", "Fixes #12") is None
    body = "Closes #13\nRefs: owner/repo#14\nFixes https://github.com/o/r/issues/15"
    assert extract_reason("x", body) is None


def test_a_fixes_line_is_cut_out_of_the_paragraph_it_sits_in_not_glued_onto_the_reason() -> None:
    top = (
        "Fixes #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24\n"
        "We dropped it because it was slow on big bodies."
    )
    bottom = "We dropped it because it was slow on big bodies.\nCloses owner/repo#7"
    expected = "We dropped it because it was slow on big bodies."
    assert extract_reason("x", top) == expected
    assert extract_reason("x", bottom) == expected


def test_a_fixes_line_carrying_a_real_sentence_is_kept() -> None:
    body = "Fixes a crash because the cache was never cleared."
    assert extract_reason("x", body) == body


def test_dependabot_bump_with_release_notes() -> None:
    body = "\n".join(
        [
            "Bumps [find-my-way](https://github.com/delvedor/find-my-way) from 8.0.0 to 8.1.0.",
            "<details>",
            "<summary>Release notes</summary>",
            '<p><em>Sourced from <a href="https://github.com/delvedor/find-my-way/releases">'
            "find-my-way's releases</a>.</em></p>",
            "<blockquote>",
            "<h2>v8.1.0</h2>",
            "<ul><li>fix: avoid crash because of empty param by "
            '<a href="https://github.com/u">@u</a> in #1</li></ul>',
            "</blockquote>",
            "</details>",
        ]
    )
    assert extract_reason("chore(deps): bump find-my-way from 8.0.0 to 8.1.0", body) is None


def test_a_bump_body_is_none_even_when_its_prose_has_a_marker_and_no_heading() -> None:
    first = (
        "Bumps [x](https://github.com/o/x) from 1.0.0 to 1.1.0.\n"
        "Notes from upstream: it avoids crashes because the parser was rewritten internally."
    )
    second = (
        "This PR contains the following updates:\n\n"
        "Updates were needed because the old version had a crash in the resolver."
    )
    assert extract_reason("x", first) is None
    assert extract_reason("x", second) is None


def test_bot_and_merge_commit_sentences_are_not_reasons() -> None:
    dependabot = "Dependabot will resolve this because it keeps the branch rebased on main."
    merge = "Merge pull request #5 from a/b because of the new flow overall."
    assert extract_reason("x", dependabot) is None
    assert extract_reason("x", merge) is None


@pytest.mark.parametrize("body", ["Because slow.", "Reason: slow.", "To avoid crashes."])
def test_a_bare_keyword_or_tiny_fragment_is_not_a_statement(body: str) -> None:
    assert extract_reason("x", body) is None


def test_a_hash_led_changelog_line_is_not_a_reason_a_hash_looking_word_is() -> None:
    assert (
        extract_reason("x", "abcdef1 fix: avoid the crash because of a bad parse in the lexer")
        is None
    )
    body = "effaced entries were kept because the audit needs them later."
    assert extract_reason("x", body) == body


def test_renovate_style_table() -> None:
    body = (
        "This PR contains the following updates:\n\n| Package | Change |\n|---|---|\n"
        "| x | `1.0.0` -> `2.0.0` |"
    )
    assert extract_reason("Update dependency x to v2", body) is None


def test_a_release_notes_or_changelog_dump_is_cut_at_its_heading() -> None:
    dump = (
        "Release 5.1.0\n\n## What's Changed\n* fix: prevent crash because x by @a in #1\n"
        "* feat: to avoid y by @b in #2"
    )
    assert extract_reason("chore: release 5.1.0", dump) is None
    body = "We did it because it was slow.\n\n## Changelog\n- avoid z because of w"
    assert extract_reason("x", body) == "We did it because it was slow."


def test_squash_merge_bullets_of_plain_subjects() -> None:
    body = (
        "* feat(logger): use pino.BaseLogger as main interface\n"
        "* fix: handle edge\n* chore: bump deps"
    )
    assert extract_reason("feat: logger (#9)", body) is None


def test_a_squash_bullet_with_only_a_medium_marker_is_not_kept() -> None:
    body = "* fix(router): use the native URL instead of the splitter, which broke on IPv6"
    assert extract_reason("x", body) is None


def test_any_list_item_of_a_squash_is_a_sub_commit_title_a_medium_marker_is_not_enough() -> None:
    first = (
        "* Hooks: throw on incorrect async function\n\n* Log a warn instead of throwing an error"
        "\n\n* Updated test"
    )
    second = "- Return early on empty input rather than crash in the parser"
    assert extract_reason("x", first) is None
    assert extract_reason("x", second) is None


def test_a_conventional_commit_subject_line_in_a_plain_paragraph_is_a_title_too() -> None:
    medium = "fix(router): use the native URL instead of the splitter, which broke on IPv6."
    strong = "fix(router): decode params so that encoded slashes survive intact."
    assert extract_reason("x", medium) is None
    assert extract_reason("x", strong) == "decode params so that encoded slashes survive intact."


def test_a_squash_bullet_with_a_strong_marker_is_kept() -> None:
    body = "* fix(router): do not decode params so that encoded slashes survive\n* chore: bump deps"
    assert (
        extract_reason("feat: router (#9)", body)
        == "do not decode params so that encoded slashes survive"
    )


def test_a_body_that_restates_the_title_in_other_words() -> None:
    title = "Remove the legacy parser because it is deprecated and slow"
    body = "The legacy parser is removed because it is deprecated and slow."
    assert extract_reason(title, body) is None


def test_a_body_that_repeats_the_title() -> None:
    assert (
        extract_reason(
            "remove parser because it is deprecated", "Remove parser because it is deprecated."
        )
        is None
    )
    same = "fix: avoid crash because header missing"
    assert extract_reason(same, same) is None


def test_a_body_repeating_a_title_the_importer_cut_at_80_characters() -> None:
    title = "fix: added a check to prevent creation of secondary server when extern"
    body = (
        "added a check to prevent creation of secondary server when external server is "
        "passed to serverfactory #4725"
    )
    assert extract_reason(title, body) is None


def test_a_markdown_table() -> None:
    body = "| Before | After |\n|---|---|\n| slow because x | fast to avoid y |"
    assert extract_reason("x", body) is None


def test_headings_and_bare_keywords() -> None:
    assert extract_reason("x", "## Performance\n\n## Security") is None
    assert extract_reason("x", "Performance improvements.") is None


def test_mostly_non_english_text_with_an_english_marker_word_in_it() -> None:
    chinese = (
        "删除了旧的解析器，因为它太慢"
        "了，这个改动是为了避免崩溃 "
        "because it is slow on every request we measured."
    )
    japanese = (
        "古いパーサーを削除しました、"
        "遅すぎるため、クラッシュを"
        "避けるために because slow on every request we measured."
    )
    assert extract_reason("x", chinese) is None
    assert extract_reason("x", japanese) is None


def test_non_english_text() -> None:
    body = "Wir haben das entfernt, weil es zu langsam war.\n\n因为这个很慢，所以删除。"
    assert extract_reason("x", body) is None


# ---------------------------------------------------------------------------
# the importer metadata never leaks
# ---------------------------------------------------------------------------


def test_reason_comes_from_the_body_not_from_author_date_files_url() -> None:
    text = full("fix: parser", "We removed it because the old one leaked.")
    assert extract_reason("fix: parser", text) == "We removed it because the old one leaked."


def test_a_commit_with_no_body_yields_none_even_though_file_names_contain_marker_words() -> None:
    assert extract_reason("fix: parser", full("fix: parser", "")) is None


def test_a_title_echoed_on_the_line_above_the_body_is_not_glued_to_it() -> None:
    echo = "fix: drop the legacy parser from the request pipeline entirely now"
    assert (
        extract_reason(echo, f"{echo}\nWe dropped it because it was slow.")
        == "We dropped it because it was slow."
    )
    body = "It avoids repeat reads, which is needed because disks are slow."
    assert extract_reason("feat: add a cache", full("feat: add a cache", body)) == body


def test_a_body_that_is_only_a_title_echo_plus_metadata_is_none() -> None:
    assert extract_reason("fix: parser", full("fix: parser", "fix: parser")) is None


def test_importer_metadata_helpers_detect_and_strip_the_block() -> None:
    text = full("fix: parser", "Body.")
    assert adr_shape.has_importer_metadata(text)
    assert adr_shape.strip_importer_metadata(text) == "fix: parser\n\nBody."
    assert not adr_shape.has_importer_metadata("fix: parser\n\nBody.")
    assert adr_shape.strip_importer_metadata("a\r\nb") == "a\nb"


# ---------------------------------------------------------------------------
# wrong-polarity and look-alike inputs found in review give None
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "This is not because of the cache. We changed the key format for fun.",
        "We did it, but not because the old one was slow on big inputs.",
        "It isn't just because of speed that the old one went away today.",
    ],
)
def test_negated_reasons(body: str) -> None:
    assert extract_reason("x", body) is None


def test_questions() -> None:
    first = "Is this broken because of the proxy? We should look at the retry logic later."
    assert extract_reason("x", first) is None
    second = "Why not use the native one? Maybe because it is slower than the other one."
    assert extract_reason("x", second) == "Maybe because it is slower than the other one."


def test_a_marker_inside_quotation_marks_is_someone_elses_claim() -> None:
    body = (
        'The reporter wrote "it crashes because the cache is stale" '
        "but we could not reproduce that issue."
    )
    assert extract_reason("x", body) is None


def test_release_please_entries_and_version_headings_are_another_changes_text() -> None:
    first = "## 1.2.0\n\n### Bug Fixes\n\n* fix crash because the parser was incorrect (#12)"
    second = "Notes.\n\n### Bug Fixes\n\n* fix crash because the parser was incorrect (#12)"
    third = (
        "## [1.2.0](https://x.test/compare)\n\nWe fixed it because the parser was incorrect today."
    )
    assert extract_reason("chore(main): release 1.2.0", first) is None
    assert extract_reason("x", second) is None
    assert extract_reason("x", third) is None


def test_merge_branch_subjects() -> None:
    body = "Merge branch 'fix-bug-because-of-race' into main"
    assert extract_reason("Merge branch 'x' into main", body) is None


def test_short_unpunctuated_lines_are_not_fused_into_one_sentence() -> None:
    body = (
        "Add the billing feature flag to settings\n"
        "Fix crash in login screen because token was null\nUpdate docs for the flag"
    )
    assert extract_reason("x", body) == "Fix crash in login screen because token was null"


def test_abbreviations_do_not_split_a_sentence() -> None:
    body = "The old code did not work because of Mr. Jones bug in the Node release. It crashed."
    assert (
        extract_reason("x", body)
        == "The old code did not work because of Mr. Jones bug in the Node release."
    )


@pytest.mark.parametrize(
    "body",
    [
        "Reason: n/a for this one, just a trivial change really.",
        "Why: see #123 for the longer discussion of why this change happened.",
        "Problem: the foo module is in the wrong place and nothing else here.",
    ],
)
def test_a_label_with_a_placeholder_or_pointer_is_not_a_reason_and_problem_is_not_a_label(
    body: str,
) -> None:
    assert extract_reason("x", body) is None


def test_a_marker_word_inside_a_file_name_is_not_a_marker() -> None:
    body = "Rename because.ts and so_that.md into the shared utils folder for clarity."
    assert extract_reason("x", body) is None


# ---------------------------------------------------------------------------
# PR template checklists
# ---------------------------------------------------------------------------


def test_never_reads_a_ticked_or_unticked_task_list_item_as_a_reason() -> None:
    body = "\n".join(
        [
            "## Checklist",
            "- [ ] I added tests because the old suite missed the regression",
            "- [x] I updated the docs so that users find the new flag",
        ]
    )
    assert extract_reason("feat: flag", body) is None
    task = "* [X] Ran the benchmarks to avoid a perf regression in the router"
    assert extract_reason("feat: flag", task) is None


def test_still_reads_the_because_sentence_that_sits_next_to_a_checklist() -> None:
    sentence = (
        "The router rebuilt its table on every call because the cache key ignored the prefix."
    )
    body = f"{sentence}\n\n- [ ] tests added\n- [x] docs updated"
    assert extract_reason("fix: router cache", body) == sentence
