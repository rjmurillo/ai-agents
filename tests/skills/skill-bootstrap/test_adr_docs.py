"""Tests for adr_docs: the rule-section classifier.

Cases port align-cli tests/fetchers_docs-conventions.test.ts (MIT, Copyright (c) 2026
Align Tech Ltd, see LICENSE-align) at the classifier level: the upstream cases drive
fetchDocsItems over a temp repo, and these drive rule_sections over the same Markdown.
"""

from __future__ import annotations

import adr_docs

# ---------------------------------------------------------------------------
# P13: rule sections (cases of fetchers_docs-conventions.test.ts)
# ---------------------------------------------------------------------------

RECART_README = """# openapi
Recart's OpenAPI specification

## Updating the changelog

Every notable API change is tracked in [`docs/changelog.md`](docs/changelog.md) and exposed as an RSS/Atom feed via GitHub Releases.

- **REST API** - date-based, pinned versions (`2023-12`). Additive changes stay on the current version; breaking changes get a new dated version.

When you change either surface:

1. **Add an entry to `docs/changelog.md`** in the same PR, under the matching track.
2. **After merge, cut a GitHub Release** whose notes mirror the entry.
"""  # noqa: E501

RECART_CHANGELOG = """---
stoplight-id:
---

# Changelog

All notable changes to Recart's developer surfaces are documented here.

## Versioning

### REST API - date-based, pinned

- **Additive, backward-compatible changes** ship into the **current** version - changelog entry only, no version bump.
- **Breaking changes** create a **new dated version** that runs side-by-side, so existing integrations keep working.

---

## REST API

### [2023-12.2] - 2026-07-07

#### Deprecated
- The `shopperId` field is deprecated. Clients must stop reading it.

### [2023-12.1] - 2026-06-24

#### Added
- `PATCH /subscribers` endpoint for updating subscribers with custom attributes.
"""  # noqa: E501

INSTALL = "\n## Installation\n\nRun npm install. You must have Node 20 installed first.\n"
USAGE = "\n## Usage\n\nCall the client with your key and read the response.\n"


def _headings(kind: adr_docs.DocKind, markdown: str) -> list[str]:
    return [section.heading for section in adr_docs.rule_sections(kind, markdown)]


def test_rule_sections_turn_the_readme_changelog_passage_into_a_rule_titled_by_its_heading() -> (
    None
):
    (rule,) = adr_docs.rule_sections("readme", RECART_README)
    assert rule.heading == "Updating the changelog"
    assert "Add an entry to `docs/changelog.md`** in the same PR" in rule.body
    assert "breaking changes get a new dated version" in rule.body


def test_rule_sections_do_not_import_readme_sections_that_are_not_rules() -> None:
    assert _headings("readme", RECART_README + INSTALL + USAGE) == ["Updating the changelog"]


def test_rule_sections_read_contributing_importing_only_its_rule_sections() -> None:
    root = (
        "# Contributing\n\n## Commits\n\nEvery commit must reference a ticket. "
        "Never force-push to main.\n\n## Thanks\n\nThank you for helping out with this project!\n"
    )
    github = "## Reviews\n\nAll changes must be reviewed by one other maintainer before merging.\n"
    docs = "## Tests\n\nNew behaviour must ship with a test that failed first.\n"
    assert _headings("contributing", root) == ["Commits"]
    assert _headings("contributing", github) == ["Reviews"]
    assert _headings("contributing", docs) == ["Tests"]


def test_rule_sections_import_a_changelog_versioning_section_but_no_dated_release_entry() -> None:
    (rule,) = adr_docs.rule_sections("changelog", RECART_CHANGELOG)
    assert rule.heading == "Versioning"
    assert "Breaking changes" in rule.body
    for leaked in ("2023-12.2", "shopperId", "PATCH /subscribers"):
        assert leaked not in rule.body
    assert not rule.body.endswith("---")


def test_rule_sections_drop_a_keep_a_changelog_release_entry_even_when_it_says_must() -> None:
    text = (
        "# Changelog\n\n## [1.2.0] - 2026-01-01\n\n### Changed\n"
        "- Clients must now send an API key. Never call without one.\n\n"
        "## Unreleased\n\n- Everyone must upgrade.\n"
    )
    assert adr_docs.rule_sections("changelog", text) == []


def test_rule_sections_import_a_readme_development_section_that_says_do_not_commit_to_main() -> (
    None
):
    text = (
        "# x\n\n## Development\n\nDo not commit directly to main. Open a branch.\n\n"
        "## Installation\n\nRun npm install. You must have Node 20 installed first.\n\n"
        "## Usage\n\nCall the client with your key. Do not share it.\n"
    )
    assert _headings("readme", text) == ["Development"]


def test_rule_sections_require_a_rule_marker_in_contributing_too() -> None:
    text = "## Welcome\n\nWe are glad you stopped by to look around the project today.\n"
    assert adr_docs.rule_sections("contributing", text) == []


def test_rule_sections_drop_a_deprecated_category_under_a_version_release_heading() -> None:
    text = (
        "# Changelog\n\n## Versioning\n\nBreaking changes create a new major version of the "
        "package.\n\n# 1.2.0\n\n## Deprecated\n\n- The old endpoint must not be used any more.\n\n"
        "## Removed\n\n- Never call v0.\n"
    )
    (rule,) = adr_docs.rule_sections("changelog", text)
    assert rule.heading == "Versioning"
    assert "1.2.0" not in rule.body


def test_rule_sections_still_import_a_real_deprecation_policy_heading_in_a_changelog() -> None:
    text = (
        "## Deprecation policy\n\nA feature is deprecated for two releases before it is removed.\n"
    )
    assert _headings("changelog", text) == ["Deprecation policy"]


def test_rule_sections_skip_headingless_preamble_and_normalise_crlf() -> None:
    text = "Intro that must be skipped.\r\n\r\n## Rules\r\n\r\nYou must sign commits.\r\n"
    (rule,) = adr_docs.rule_sections("contributing", text)
    assert (rule.heading, rule.body) == ("Rules", "You must sign commits.")


def test_split_into_sections_keeps_a_headingless_first_section() -> None:
    assert adr_docs.split_into_sections("# T\nintro\n## A\nbody a\n## B\n") == [
        (None, "# T\nintro"),
        ("A", "body a"),
        ("B", ""),
    ]
    assert adr_docs.split_into_sections("") == [(None, "")]


def test_is_rule_section_changelog_decides_by_heading_only() -> None:
    assert adr_docs.is_rule_section("changelog", "Versioning", "plain description")
    assert not adr_docs.is_rule_section("changelog", "Added", "Never do this.")
    assert not adr_docs.is_rule_section("changelog", "1.2.0 policy", "Never do this.")
    assert not adr_docs.is_rule_section("changelog", "2026-01-01 policy", "Never do this.")
    assert adr_docs.is_rule_section("changelog", "v2 policy", "Never do this.")
    assert not adr_docs.is_rule_section("changelog", "Overview", "Never do this.")


def test_is_rule_section_readme_needs_both_a_marker_and_a_convention_heading() -> None:
    assert adr_docs.is_rule_section("readme", "Branch rules", "You must rebase.")
    assert not adr_docs.is_rule_section("readme", "Branch rules", "Nothing binding here.")
    assert not adr_docs.is_rule_section("readme", "Install", "You must have Node.")


def test_section_body_cuts_a_changelog_at_the_next_top_level_heading_only() -> None:
    assert adr_docs.section_body("changelog", "keep\n\n# 1.2.0\ndrop") == "keep"
    assert (
        adr_docs.section_body("readme", "keep\n\n# 1.2.0\nkeep too") == "keep\n\n# 1.2.0\nkeep too"
    )


def test_is_versioned_release_heading_needs_a_version_after_release() -> None:
    assert adr_docs.is_versioned_release_heading("Release: 1.2.0 batch landing")
    assert adr_docs.is_versioned_release_heading("release v2")
    assert adr_docs.is_versioned_release_heading("Release 2.0")
    assert not adr_docs.is_versioned_release_heading("Release process")
    assert not adr_docs.is_versioned_release_heading("Releasing the installer")
    assert not adr_docs.is_versioned_release_heading("Checkpoint 2026-06-10")
