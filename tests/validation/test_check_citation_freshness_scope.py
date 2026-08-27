"""Scope boundaries for the citation gate.

Issue #5337; split from ``test_check_citation_freshness.py`` at the taste
file-size ceiling (diff parsing and wiring live in sibling files).
Regression provenance for each case is in its comment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import (
    GONE,
    TARGET,
    _add_doc,
    _git,
    _repo,
    _run,
    checker,
)


class TestScopeBoundaries:
    def test_ignore_marker_on_the_line_above_suppresses(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = (
            f"{checker.IGNORE_MARKER} -- quoting the pre-fix state\n"
            f"See `{TARGET}:2` (`magic_token`).\n"
        )
        _add_doc(root, "docs/notes.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0

    def test_ignore_marker_on_the_same_line_suppresses(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = f"See `{TARGET}:2` (`magic_token`). {checker.IGNORE_MARKER} -- historical\n"
        _add_doc(root, "docs/notes.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0

    def test_bare_marker_without_a_reason_does_not_suppress(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The documented form is "marker -- <reason>"; a reasonless marker
        # is a silent bypass and must not count (Copilot, PR #5338).
        root = _repo(tmp_path)
        doc = f"{checker.IGNORE_MARKER}\nSee `{TARGET}:2` (`magic_token`).\n"
        _add_doc(root, "docs/notes.md", doc)

        code, _out = _run(root, capsys)

        assert code == 1

    def test_reasoned_marker_exempts_a_citation_to_a_removed_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot, PR #5338): the marker used to be consulted
        # after the tracked-at-HEAD check, so documenting a deliberate
        # removal could not be exempted.
        root = _repo(tmp_path)
        doc = f"{checker.IGNORE_MARKER} -- documents the removed helper\nSee {GONE}:1.\n"
        _add_doc(root, "docs/notes.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0

    def test_unrelated_indented_block_is_not_an_anchor_without_a_colon(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot, PR #5338): a deeper-indented line was
        # harvested as a quote anchor even when the citation line never
        # introduced one, failing an otherwise anchorless citation.
        root = _repo(tmp_path)
        doc = f"See {TARGET}:2 today.\n\n    unrelated_block_content()\n"
        _add_doc(root, "docs/notes.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0

    def test_deeper_indented_example_block_is_not_sentence_context(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # False positive found replaying post-merge history (the corpus
        # shape PR #5336's own fix text carries): a deeper-indented
        # example line above a citation belongs to the PREVIOUS
        # citation as its continuation quote, not to this sentence.
        root = _repo(tmp_path)
        doc = (
            f"    first {TARGET}:3 (spelled):\n"
            f"        def magic_token():\n"
            f"    second {TARGET}:2 (spelled, shared by\n"
            f"    others):\n"
        )
        _add_doc(root, "docs/notes.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0

    def test_markdown_heading_does_not_join_body_text_as_context(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (CodeRabbit, PR #5338): a heading is a complete
        # unit, but an unterminated one joined the following body line
        # as a sentence wrap, so a body identifier became an unrelated
        # required anchor and rejected a valid heading citation.
        root = _repo(tmp_path)
        doc = f"## About {TARGET}:2\nThe `magic_token` helper is unrelated.\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 1 citation(s)" in out

    def test_adjacent_markdown_headings_never_pool_anchors(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot, PR #5341): two headings share the hash
        # prefix, so the mismatch guard alone let a cited heading join
        # the next heading and absorb its backtick span as a required
        # anchor. A heading joins nothing, another heading included.
        root = _repo(tmp_path)
        doc = f"## About {TARGET}:2\n## The `magic_token` helper\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 1 citation(s)" in out

    def test_unfinished_heading_above_a_body_citation_adds_no_anchors(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The backward direction of the heading boundary (Copilot, PR
        # #5341): a heading with no sentence-ending punctuation reads as
        # a continuing sentence. The shape is guarded twice, by the
        # indent guard (a hash marker counts as indentation, so a heading
        # sits deeper than unindented body text) and by the ATX-heading
        # block, so this pins the behavior: only removing both hands
        # the heading's backtick span to the citation below it.
        root = _repo(tmp_path)
        doc = f"## The `magic_token` helper\nDetails in {TARGET}:2 today.\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 1 citation(s)" in out

    def test_blockquoted_heading_is_still_a_complete_unit(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot, PR #5341): the bare hash-prefix predicate
        # read "> ## heading" as body text, so a blockquoted heading
        # citation absorbed the next blockquote line's backtick span.
        root = _repo(tmp_path)
        doc = f"> ## About {TARGET}:2\n> The `magic_token` helper is here.\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 1 citation(s)" in out

    def test_blockquote_marker_spacing_does_not_hide_a_heading(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # CodeRabbit finding (PR #5341): the marker's own optional space
        # plus the heading's up-to-3 indent means as many as 4 spaces may
        # separate ">" from the hashes, so ">    ## heading" must
        # classify as a heading, not as body text that absorbs the next
        # blockquote line's backtick span.
        root = _repo(tmp_path)
        doc = f">    ## About {TARGET}:2\n> The `magic_token` helper is here.\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 1 citation(s)" in out

    def test_hashtag_paragraph_is_body_text_not_a_heading(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The other direction of the ATX classifier (Copilot, PR #5341):
        # "#hashtag" is not a heading (no space after the hash), so a
        # citation on that line keeps its wrapped-sentence anchor and
        # this stale claim must fail rather than pass anchorless.
        root = _repo(tmp_path)
        doc = f"The `magic_token` helper sits\n#hashtag {TARGET}:2 note\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 1
        assert "magic_token" in out

    def test_code_text_never_joins_a_comment_citation_backward(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The input that isolates the backward hash-mismatch break: a
        # continuing code line sits at indent 0, below the comment's
        # marker-inclusive indent, so only the prefix mismatch stops its
        # identifier becoming this citation's required anchor.
        root = _repo(tmp_path)
        doc = f"magic_token_reader = load()\n# See {TARGET}:2 for the value.\n"
        _add_doc(root, "docs/notes.py", doc)

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 1 citation(s)" in out

    def test_finished_previous_sentence_is_not_an_anchor_source(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot, PR #5338): an identifier on a neighboring
        # finished sentence must not become an assertion about this
        # citation; only a wrapped sentence contributes anchors.
        root = _repo(tmp_path)
        doc = f"Mentions unrelated `foo_bar` here.\nSee {TARGET}:2 in passing\n"
        _add_doc(root, "docs/notes.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0

    def test_historical_roots_are_never_scanned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = f"See `{TARGET}:2` (`magic_token`).\n"
        _add_doc(root, ".agents/retrospective/2020-01-01-note.md", doc)

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 0 citation(s)" in out

    def test_memory_episode_tree_is_never_scanned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 4, PR #5338): stale_script_refs's
        # HISTORICAL_ROOTS has no .agents/memory/ entry, so new episode
        # records under that 750-file historical tree could block a push.
        root = _repo(tmp_path)
        doc = f'{{"note": "See `{TARGET}:2` (`magic_token`)."}}\n'
        _add_doc(root, ".agents/memory/episodes/episode-1.json", doc)

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 0 citation(s)" in out

    def test_fixture_directories_are_never_scanned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = f"See `{TARGET}:2` (`magic_token`).\n"
        _add_doc(root, "tests/hooks/fixtures/sample.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0

    def test_top_level_fixtures_directory_is_never_scanned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Spec-validation boundary case (PR #5338): the fragment match
        # needed a leading slash to also exempt a repo-root fixtures/
        # directory, not only nested ones.
        root = _repo(tmp_path)
        _add_doc(root, "fixtures/sample.md", f"See `{TARGET}:2` (`magic_token`).\n")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 0 citation(s)" in out

    def test_stale_citation_already_in_base_is_not_this_branch_claim(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _git(root, "checkout", "-q", "main")
        _add_doc(root, "docs/old.md", f"See `{TARGET}:2` (`magic_token`).\n")
        _git(root, "checkout", "-q", "feature")
        _git(root, "merge", "-q", "main")
        _add_doc(root, "docs/new.md", "Nothing cited here.\n")

        code, _out = _run(root, capsys)

        assert code == 0

    def test_url_reference_is_not_scanned_as_a_citation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 2, PR #5338): a URL shaped like
        # host/org/file.py:N read as a repository citation and failed as
        # untracked, so an ordinary external link could block a push.
        root = _repo(tmp_path)
        url = "https://example.com/org/file.py:42"
        _add_doc(root, "docs/notes.md", f"See {url} for the upstream form.\n")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 0 citation(s)" in out

    def test_unquoted_bare_filename_is_not_a_required_anchor(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 2, PR #5338): a slashless filename
        # survived path masking, so its stem was harvested as an identifier
        # anchor and failed an otherwise anchorless valid citation.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"About model_pin_manifest.py, see {TARGET}:2 today.\n")

        code, _out = _run(root, capsys)

        assert code == 0

    def test_same_line_citations_use_their_own_anchors(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 2, PR #5338): anchors from every
        # citation on a line were pooled, so a stale citation passed
        # whenever its sibling's anchor matched its range. The midpoint
        # split binds each anchor to its nearer citation.
        root = _repo(tmp_path)
        doc = f"See {TARGET}:2 (`magic_token`) and {TARGET}:2 (`PLACEHOLDER`).\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 1
        assert out.count("none of the cited anchors") == 1
        assert "'magic_token'" in out

    def test_absolute_filesystem_path_is_not_a_repository_citation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 3, PR #5338): without a left boundary
        # the matcher started after the leading slash, so an absolute path
        # in a report quote parsed as a repo citation and failed untracked.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"Reported at /home/richard/repo/{TARGET}:2 today.\n")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 0 citation(s)" in out

    def test_windows_absolute_path_is_not_a_repository_citation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 5, PR #5338): the left boundary
        # excluded / but not backslash, so the matcher restarted at the
        # tail of a Windows absolute path; with root files in scope,
        # C:\tmp\README.md:42 read as a claim about the tracked README.
        root = _repo(tmp_path)
        readme = "README" + ".md"
        _add_doc(root, "docs/notes.md", f"Logged at C:\\tmp\\{readme}:42 today.\n")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 0 citation(s)" in out

    def test_parent_relative_path_is_not_a_repository_citation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Same round: ../ prefixes name a path outside the repo root, so
        # they are never claims about tracked content; ./ remains accepted.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See ../{TARGET}:2 in the sibling checkout.\n")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 0 citation(s)" in out

    def test_dot_slash_prefix_still_matches(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Control for the left boundary: the ./ spelling stays in scope
        # (the gate strips the prefix before resolving the path).
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See ./{TARGET}:3 (`magic_token`).\n")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 1 citation(s)" in out

    def test_untracked_bare_name_is_skipped_as_illustrative(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A slashless name with no tracked root file behind it is an
        # illustrative snippet, never a claim, and is not even counted.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", "Fix the null check at auth.ts:47 first.\n")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 0 citation(s)" in out

    def test_tracked_root_file_stale_citation_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (CodeRabbit + spec validation, PR #5338): the live
        # miss was a stale citation to root-level .markdownlint-cli2.yaml,
        # invisible while the matcher required a slash. A slashless name
        # backed by a tracked root file is a claim and is verified.
        root = _repo(tmp_path)
        readme = "README" + ".md"
        _add_doc(root, "docs/notes.md", f"Per {readme}:5, the base doc.\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "has 1 lines at HEAD" in out

    def test_tracked_root_dotfile_stale_citation_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The incident shape exactly: a hidden root config file.
        root = _repo(tmp_path)
        (root / ".lint.yaml").write_text("rules: none\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "cfg")
        dotfile = ".lint" + ".yaml"
        _add_doc(root, "docs/notes.md", f"Configured at {dotfile}:9 today.\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "has 1 lines at HEAD" in out

    def test_xml_citation_is_in_scope(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Spec-validation edge case (PR #5338): config.xml is a real text
        # format contributors cite; it joins the extension allowlist.
        root = _repo(tmp_path)
        xml = "docs/config" + ".xml"
        _add_doc(root, xml, "<a/>\n")
        _add_doc(root, "docs/notes.md", f"See {xml}:10 today.\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "has 1 lines at HEAD" in out

    def test_tracked_root_file_fresh_citation_passes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        readme = "README" + ".md"
        _add_doc(root, "docs/notes.md", f"Per {readme}:1, the base doc.\n")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 1 citation(s)" in out


