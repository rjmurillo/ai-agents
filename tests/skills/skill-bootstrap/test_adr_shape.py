"""Tests for adr_shape: commit subject shape, rationale gate and merge promotion.

The first half ports the cases of align-cli tests/commit-shape.test.ts (MIT,
Copyright (c) 2026 Align Tech Ltd, see LICENSE-align). Titles follow the upstream
test titles. The second half covers functions that upstream tests only reach through
git-history fixtures: has_stated_rationale, is_decision_commit, resolve_commit_shape.
"""

from __future__ import annotations

import adr_shape
import pytest

# ---------------------------------------------------------------------------
# mechanicalSubjectRegex
# ---------------------------------------------------------------------------


def test_mechanical_regex_treats_a_prefix_literally_even_with_regex_metacharacters() -> None:
    pattern = adr_shape.mechanical_subject_regex(["c++", "wip"])
    assert pattern.search("c++: rebuild the parser")
    # Interpolated raw, `c++` reads as "one or more c" and this would match too.
    assert not pattern.search("ccc: three cs is not the c++ prefix")


def test_mechanical_regex_builds_the_predicate_the_real_list_uses() -> None:
    pattern = adr_shape.mechanical_subject_regex(adr_shape.MECHANICAL_SUBJECT_PREFIXES)
    for prefix in adr_shape.MECHANICAL_SUBJECT_PREFIXES:
        assert pattern.search(f"{prefix}: something"), prefix
    assert not pattern.search("feat: something")


def test_mechanical_regex_is_anchored_to_the_start_and_case_insensitive() -> None:
    pattern = adr_shape.mechanical_subject_regex(["chore"])
    assert pattern.search("CHORE: shout it")
    assert not pattern.search("a chore: not at the start")


# ---------------------------------------------------------------------------
# isReleaseOrBumpSubject
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject",
    [
        "Bumped v5.9.0",
        "Bump v5.9.0",
        "Bumpedv v6.0.0-alpha.5",
        "Bumps lodash from 4.17.20 to 4.17.21",
        "Release v5.9.0",
        "Released 5.11.2 with the fixes below",
        "v5.9.0",
        "5.11.2",
        "Version 5.9.0",
        "chore(release): 5.9.0",
        "Update dependency lodash to v3",
        "Upgrade pino from 9 to 10",
        "fix: bump lodash from 4.17.20 to 4.17.21",
        "build(deps): bump tiny-lru from 10.4.1 to 11.0.1 (#4694)",
    ],
)
def test_release_or_bump_is_housekeeping(subject: str) -> None:
    assert adr_shape.is_release_or_bump_subject(subject) is True


@pytest.mark.parametrize(
    "subject",
    [
        "fix: clamp error statusCode between 400 and 599 with 500 fallback (#7089)",
        "fix: do not trust forwarded host/proto when socket is missing",
        "build(deps): replace `proxy-addr` with `@fastify/proxy-addr` (#5913)",
        "feat: add support for version 2 of the schema",
        "Use release candidates only on the next branch",
        "fix: release the socket when the client aborts mid-request",
        # a scope named release is a topic, not a version
        "feat(release): publish with provenance attestations",
        "fix(release): pin npm to 10 so the publish job stops failing",
        # a bump that states why is a decision
        "fix: bump timeout from 5s to 30s because the upstream is slow",
        "feat: bump minimum Node to 20, drops 18",
        "fix: bump lodash to 4.17.21 (CVE-2021-23337)",
        "Update dependency lodash to v3 to avoid the prototype pollution",
        "Release 2FA support for admin accounts",
        "feat!: v6.0.0 drops Node 18",
        'Revert "Bump x from 1 to 2"',
        "feat: bump ajv-compiler (#3687)",
        "Update documentation for listening to 0.0.0.0 (#5988)",
        "docs: update all nodejs doc links to point to v14.x documentation (#3227)",
        "Update @types/node to 15.3.0 and fix type definition (#3076)",
    ],
)
def test_release_or_bump_is_a_decision_not_housekeeping(subject: str) -> None:
    assert adr_shape.is_release_or_bump_subject(subject) is False


# ---------------------------------------------------------------------------
# isOneOffChangeTitle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "rename abandonment endpoint",
        "fix required properties",
        "add SMSUnsubscription webhook",
        "Add list phonenumber handling",
        "add createdAt and updatedAt to orderSchema",
        "Update actions/deploy-pages action to v5.0.1",
        "Tidy the release scripts",
        "extend outgoing messages properties",
        "post/put order endpoint",
        "Modify the order schema",
        "Put the retry helper in its own file",
        "Document the retry endpoint",
        "2052-epochs.md: typo",
        "refactor(llm): delete the unreachable explicit-provider branch",
        "docs: reword the install section",
        "chore: sort the imports in the cli",
    ],
)
def test_one_off_change_title_is_one_off(title: str) -> None:
    assert adr_shape.is_one_off_change_title(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "Use Postgres for the events store",
        "Switch from REST to gRPC for internal services",
        "Migrate to pnpm",
        "Replace Redis with Valkey",
        "Drop support for Node 16",
        "Stop using moment.js",
        "Move auth to JWT",
        "Make the cache write-through",
        "Change `i686-pc-windows-msvc` from Tier 1 to Tier 2",
        "RFC: Refactor the libs team",
        "RFC: Cargo feature descriptions",
        "feat(check): a human can answer a check that declined to rule",
        "feat!: remove v1 API",
        "Utiliser Postgres pour le store d'evenements",
        "Alle Endpunkte muessen authentifiziert werden",
        "Adopt token-bucket rate limiting on all public endpoints",
        "Require a ticket reference on every commit",
        "Never log request bodies",
    ],
)
def test_one_off_change_title_is_kept_not_one_off(title: str) -> None:
    assert adr_shape.is_one_off_change_title(title) is False


@pytest.mark.parametrize(
    "title",
    [
        "Reject unsigned webhooks so forged events cannot enter",
        "fix(action): a WARNING conflict should not block a merge",
        "Add retries to the queue consumer to keep jobs alive across restarts",
        "Remove every unused feature flag",
        "Add rate limiting to all public endpoints",
        "Fix race in all handlers",
        "Update the schema so that clients can pin a version",
        "Remove the legacy path: do not call it again",
        "Remove x, don't re-add it",
        "Add a lint rule, it should run in CI",
        "Only add endpoints through the registry",
        "Extend every webhook payload with a version field",
    ],
)
def test_one_off_change_title_lead_is_rescued_by_purpose_modal_or_quantifier(title: str) -> None:
    assert adr_shape.is_one_off_change_title(title) is False


@pytest.mark.parametrize(
    "title",
    [
        "fix: clamp error statusCode between 400 and 599 with 500 fallback (#7089)",
        "fix: cap retries at no more than 5 per job",
        "Fix the upload limit: at most 10 MB per file",
        "fix: reject payloads over 1048576 bytes",
    ],
)
def test_one_off_change_title_lead_is_rescued_by_a_numeric_bound(title: str) -> None:
    assert adr_shape.is_one_off_change_title(title) is False


@pytest.mark.parametrize(
    "title",
    [
        "fix: handle the 500 page in the router",
        "Update the base image to node 22",
        "fix: typo in section 4 heading",
    ],
)
def test_one_off_change_title_number_without_a_bound_word_is_still_one_off(title: str) -> None:
    assert adr_shape.is_one_off_change_title(title) is True


# ---------------------------------------------------------------------------
# states_numeric_bound, states_subject_rule (upstream reaches them via the rationale gate)
# ---------------------------------------------------------------------------


def test_states_numeric_bound_needs_a_bound_word_not_just_a_digit() -> None:
    assert adr_shape.states_numeric_bound("between 400 and 599")
    assert adr_shape.states_numeric_bound("no more than 5 retries")
    assert not adr_shape.states_numeric_bound("handle the 500 page")
    assert not adr_shape.states_numeric_bound("")


@pytest.mark.parametrize(
    "title",
    [
        "do not force close idle sockets",
        "should not pass url to the handler",
        "disallow reply status code 600",
        "use X instead of Y for the parser",
        "deprecate A in favour of B",
        "deprecates the old hook in favor of the new one",
        "feat: never log request bodies (#12)",
    ],
)
def test_states_subject_rule_keeps_a_rule_stated_in_the_title(title: str) -> None:
    assert adr_shape.states_subject_rule(title) is True


@pytest.mark.parametrize(
    "title",
    [
        "docs: clarify errors must be Errors",
        "test: the parser should not crash",
        "chore: always sort imports",
        "fastify-https-always plugin update",
        "remove deprecated option",
        "require.cache is read once",
        "add a retry to the client",
    ],
)
def test_states_subject_rule_ignores_exempt_types_and_code_names(title: str) -> None:
    assert adr_shape.states_subject_rule(title) is False


# ---------------------------------------------------------------------------
# P4: has_stated_rationale, is_reason_bearing_line
# ---------------------------------------------------------------------------


def test_rationale_a_subject_rule_or_numeric_bound_passes_with_no_body() -> None:
    assert adr_shape.has_stated_rationale("Never log request bodies", "")
    assert adr_shape.has_stated_rationale("fix: clamp between 400 and 599", "")


def test_rationale_an_empty_or_blank_body_has_none() -> None:
    assert not adr_shape.has_stated_rationale("Add a retry to the client", "")
    assert not adr_shape.has_stated_rationale("Add a retry to the client", "  \n\n ")


def test_rationale_trailers_and_agent_attribution_lines_are_dropped() -> None:
    body = (
        "Co-Authored-By: A <a@b.c>\nSigned-off-by: B <b@c.d>\nCloses: #45\n"
        "\U0001f916 Generated with X"
    )
    assert not adr_shape.has_stated_rationale("Add a retry to the client", body)
    assert not adr_shape.has_stated_rationale("Add a retry", "Generated by a script run")


def test_rationale_a_trailer_word_mid_sentence_is_prose_and_is_kept() -> None:
    body = "Refs APP-123 and closes #45 were reviewed together before this landed."
    assert adr_shape.has_stated_rationale("Add a retry to the client", body)


def test_rationale_an_attribution_look_alike_inside_a_sentence_is_kept() -> None:
    body = "Regenerated with a fresh script because the old output was stale."
    assert adr_shape.has_stated_rationale("Add a retry to the client", body)


def test_rationale_a_line_that_echoes_the_subject_is_dropped() -> None:
    subject = "fix: same as the subject"
    assert not adr_shape.has_stated_rationale(subject, "* fix: same as the subject")
    assert not adr_shape.has_stated_rationale(subject, "Fix - same as the SUBJECT.")


def test_rationale_separators_and_file_action_lines_are_dropped() -> None:
    body = "---------\nModified 2 files\n* Added src/lib/new-thing.ts\nDeleted docs/old.md"
    assert not adr_shape.has_stated_rationale("Add a retry to the client", body)


def test_rationale_plain_prose_counts() -> None:
    body = "The client gave up after one failure, so flaky links lost writes."
    assert adr_shape.has_stated_rationale("Add a retry to the client", body)


def test_reason_bearing_line_a_plain_line_is_evidence() -> None:
    assert adr_shape.is_reason_bearing_line("Plain prose line.")


def test_reason_bearing_line_a_short_bullet_without_a_why_is_not() -> None:
    assert not adr_shape.is_reason_bearing_line("* handle edge case")


def test_reason_bearing_line_a_bullet_that_states_why_is() -> None:
    assert adr_shape.is_reason_bearing_line("- retry on 503 because the gateway drops sockets")


def test_reason_bearing_line_a_bullet_of_eight_words_is_a_sentence() -> None:
    assert adr_shape.is_reason_bearing_line("* one two three four five six seven eight")
    assert not adr_shape.is_reason_bearing_line("* one two three four five six seven")


def test_reason_bearing_line_a_conventional_bullet_is_a_subject_however_long() -> None:
    line = "* fix(router): one two three four five six seven eight nine ten"
    assert not adr_shape.is_reason_bearing_line(line)


# ---------------------------------------------------------------------------
# P6: is_decision_commit, resolve_commit_shape
# ---------------------------------------------------------------------------


def test_decision_commit_accepts_a_long_non_mechanical_subject() -> None:
    assert adr_shape.is_decision_commit("Use Postgres for the events store")


def test_decision_commit_rejects_a_subject_under_the_20_character_floor() -> None:
    assert not adr_shape.is_decision_commit("Use Postgres")
    assert adr_shape.is_decision_commit("x" * 20)
    assert not adr_shape.is_decision_commit("x" * 19)


def test_decision_commit_padding_with_whitespace_does_not_clear_the_floor() -> None:
    assert not adr_shape.is_decision_commit("   Use Postgres   " + " " * 20)


@pytest.mark.parametrize(
    "subject",
    [
        "chore: tidy the whole thing up now",
        "WIP: half finished retry policy",
        "Revert the retry policy change",
        "Bumped v5.9.0 of the whole package",
        "Added src/lib/new-thing.ts (#12)",
    ],
)
def test_decision_commit_rejects_mechanical_release_and_file_action_subjects(
    subject: str,
) -> None:
    assert not adr_shape.is_decision_commit(subject)


def test_resolve_shape_a_non_merge_commit_is_unchanged() -> None:
    shape = adr_shape.resolve_commit_shape("Use Postgres for the events store", "Body.")
    assert shape == ("Use Postgres for the events store", "Body.")


def test_resolve_shape_a_merge_takes_its_body_title_and_keeps_the_merge_subject() -> None:
    shape = adr_shape.resolve_commit_shape(
        "Merge pull request #78 from x/y",
        "Adopt token-bucket rate limiting on all public endpoints\n\nMore detail here.",
    )
    assert shape.subject == "Adopt token-bucket rate limiting on all public endpoints"
    assert shape.body == "Merge pull request #78 from x/y\nMore detail here."


def test_resolve_shape_a_merge_skips_leading_blank_body_lines() -> None:
    shape = adr_shape.resolve_commit_shape(
        "merge branch 'a'", "\n\n  Adopt token-bucket rate limiting everywhere"
    )
    assert shape.subject == "Adopt token-bucket rate limiting everywhere"
    assert shape.body == "merge branch 'a'"


def test_resolve_shape_a_merge_with_nothing_decision_shaped_keeps_its_boilerplate() -> None:
    subject, body = "Merge pull request #78 from x/y", "wip stuff"
    assert adr_shape.resolve_commit_shape(subject, body) == (subject, body)
    assert adr_shape.resolve_commit_shape(subject, "") == (subject, "")


def test_resolve_shape_a_subject_that_only_starts_with_merge_prose_is_not_a_merge() -> None:
    # "Merge" must be a whole word: "Merger" is not a merge commit.
    shape = adr_shape.resolve_commit_shape("Mergers need review", "Adopt a review rule for all")
    assert shape.subject == "Mergers need review"
