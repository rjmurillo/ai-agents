"""Tests for the decision-shaped title filter and breaking changes.

The decision-shaped cases port the seeded titles of align-cli tests/context-from-graph.test.ts
(MIT, Copyright (c) 2026 Align Tech Ltd, see LICENSE-align) at the title level: upstream
seeds them as github rows and reads them back through selectForFile, which calls
decisionShapedRows. The graph, database and embedding parts of those tests are not ported.
The commit object parser lives in test_adr_commit_objects.py. The breaking-change signal is
added by this port, so those cases are new.
"""

from __future__ import annotations

import adr_commits
import adr_shape
import pytest

# ---------------------------------------------------------------------------
# P8: is_decision_shaped_title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title",
    [
        "Adopt token-bucket rate limiting",
        "Switch to gRPC for internal calls",
        "Use Postgres for the events store",
        # Upstream: "names every active decision in the local graph" and the superseded pair.
        "Use Postgres 16 for the events store",
        "Always retry webhooks three times with backoff",
        "Use Redis to cache sessions",
        "Use Postgres to cache sessions",
    ],
)
def test_title_decision_wording_is_kept(title: str) -> None:
    assert adr_shape.is_decision_shaped_title(title)


@pytest.mark.parametrize(
    "title",
    [
        "Fix retry on 503",
        "Rename the helper module",
        "#123 something",
        "fix: adopt nothing, this is a fix",
        "docs: always sign commits",
        "chore: never mind the policy",
        "build(deps): bump lodash and prefer ranges",
        "perf(core): drop support for old paths",
        "refactor(core): migrate the parser",
        "test(api): must not crash",
        "revert: switch to gRPC",
        "feat: fix retry policy",
    ],
)
def test_title_a_fix_shaped_type_or_lead_is_dropped(title: str) -> None:
    assert not adr_shape.is_decision_shaped_title(title)


@pytest.mark.parametrize(
    "title",
    [
        "feat: adopt token-bucket rate limiting",
        "feat(api): switch to gRPC for internal calls",
        # Upstream's ^\w+\([^)]*\): alternative drops each of these scoped commits.
        "api(v2): switch to gRPC for internal calls",
        "arch(auth): migrate sessions to JWT",
        "policy(commits): always sign commits",
        "feat(api)!: drop support for the v1 endpoints",
        "feature(core): prefer streams over buffers",
    ],
)
def test_title_a_scoped_commit_with_a_decision_wording_is_kept(title: str) -> None:
    assert adr_shape.is_decision_shaped_title(title)


def test_decision_shaped_title_the_leading_issue_number_after_the_prefix_is_ignored() -> None:
    assert adr_shape.is_decision_shaped_title("feat: #12 adopt the new router")
    assert not adr_shape.is_decision_shaped_title("feat: #12 fix the router")
    assert not adr_shape.is_decision_shaped_title("")


# ---------------------------------------------------------------------------
# E3: breaking_change
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject",
    ["feat!: drop the v1 API", "feat(api)!: drop the v1 API", "FIX(core)!: rename the flag"],
)
def test_breaking_change_a_bang_after_the_type_or_scope_is_breaking(subject: str) -> None:
    assert adr_commits.breaking_change(subject, "") is True


@pytest.mark.parametrize(
    "body",
    [
        "BREAKING CHANGE: the v1 endpoints are gone",
        "Explains why.\n\nBREAKING CHANGE: the v1 endpoints are gone",
        "Explains why.\n\nBREAKING-CHANGE: the v1 endpoints are gone",
        "Explains why.\n\nBREAKING CHANGE: spans\nmore than one line",
        "Explains why.\n\nReviewed-by: Z\nBREAKING CHANGE: the v1 endpoints are gone",
        "Explains why.\n\nBREAKING CHANGE: gone\n\nCo-Authored-By: A <a@b.c>",
        "Explains why.\r\n\r\nBREAKING CHANGE: gone\r\n",
    ],
)
def test_breaking_change_a_footer_line_in_the_trailer_paragraph_is_breaking(body: str) -> None:
    assert adr_commits.breaking_change("feat: drop the v1 API", body) is True


@pytest.mark.parametrize(
    "body",
    [
        "We note that this is not a BREAKING CHANGE: nothing is removed.",
        "BREAKING CHANGE: the v1 endpoints are gone\n\nMore prose follows after the footer.",
        "Intro.\n\nSee the BREAKING CHANGE: section of the docs for details.",
        "breaking change: lowercase is not the token",
        "BREAKING CHANGES: plural is not the token",
        "BREAKING CHANGE:",
        "BREAKING CHANGE ahead without a colon",
        "",
    ],
)
def test_breaking_change_the_phrase_in_mid_body_prose_is_not_breaking(body: str) -> None:
    assert adr_commits.breaking_change("feat: drop the v1 API", body) is False


@pytest.mark.parametrize(
    "subject",
    ["feat: add a ! to the greeting", "feat(a!b): odd scope", "fix: handle bang! in names", ""],
)
def test_breaking_change_a_bang_elsewhere_in_the_subject_is_not_breaking(subject: str) -> None:
    assert adr_commits.breaking_change(subject, "") is False
