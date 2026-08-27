"""Scope boundaries, diff parsing, and wiring for the citation gate.

Issue #5337; split from ``test_check_citation_freshness.py`` at the taste
file-size ceiling. Regression provenance for each case is in its comment.
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


class TestDiffParsing:
    """The unified-diff parse must use git's LF-only line model."""

    def test_added_content_starting_with_plus_plus_is_not_a_file_header(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot, PR #5338): "+" + "++ heading" renders as
        # "+++ heading" in the diff, and the old parser read it as a file
        # header, misattributing every following added line.
        root = _repo(tmp_path)
        doc = f"++ heading\nSee `{TARGET}:2` (`magic_token`).\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 1
        # Composed, not literal: a literal expected-finding string is
        # itself a citation to an untracked path, and the gate flagged
        # these two assertions when they were first written literally.
        assert f"{'docs/notes.md'}:2:" in out

    def test_a_configured_textconv_driver_cannot_rewrite_the_parsed_diff(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 2, PR #5338): .gitattributes assigns
        # markdown a diff driver, so a contributor's configured textconv
        # could rewrite the patch the parser reads. With --no-textconv the
        # stale citation is still found; without it, the uppercased patch
        # no longer matches the citation pattern and the gate goes silent.
        root = _repo(tmp_path)
        (root / ".gitattributes").write_text("*.md diff=markdown\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "attrs")
        _git(root, "config", "diff.markdown.textconv", "tr a-z A-Z <")
        _add_doc(root, "docs/notes.md", f"See `{TARGET}:2` (`magic_token`).\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "examined 1 citation(s)" in out

    def test_a_pure_rename_does_not_reauthor_its_latent_citations(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 4, PR #5338): with a contributor's
        # diff.renames=false a pure rename degrades to delete-plus-add,
        # so a stale citation that predates the branch reads as newly
        # authored and blocks the push. --find-renames pins detection on.
        root = _repo(tmp_path)
        _git(root, "checkout", "-q", "main")
        _add_doc(root, "docs/old.md", f"See `{TARGET}:2` (`magic_token`).\n")
        _git(root, "checkout", "-q", "feature")
        _git(root, "merge", "-q", "main")
        _git(root, "config", "diff.renames", "false")
        _git(root, "mv", "docs/old.md", "docs/renamed.md")
        _git(root, "commit", "-q", "-m", "rename")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 0 citation(s)" in out

    def test_non_ascii_citing_path_is_not_octal_escaped(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Same round: core.quotePath (default true) octal-escapes a
        # non-ASCII path in the +++ header, so the citing file stops
        # matching its HEAD path; pinned off, the finding names the
        # real file.
        root = _repo(tmp_path)
        _add_doc(root, "docs/nötes.md", f"See `{TARGET}:2` (`magic_token`).\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert f"{'docs/nötes.md'}:1:" in out

    def test_unicode_line_separator_does_not_shift_line_numbers(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot, PR #5338): splitlines() breaks on U+2028, so
        # a separator whose tail begins "+ " minted a phantom added line and
        # shifted every following line number by one.
        root = _repo(tmp_path)
        doc = f"a + x\nSee `{TARGET}:2` (`magic_token`).\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 1
        # Composed, not literal: a literal expected-finding string is
        # itself a citation to an untracked path, and the gate flagged
        # these two assertions when they were first written literally.
        assert f"{'docs/notes.md'}:2:" in out



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



class TestPrePrWiring:
    """testing.md SHOULD 6: prove the consumer is wired, not only the guard."""

    def test_gate_is_registered_and_reexported_identically(self) -> None:
        from scripts.validation import pre_pr, pre_pr_sequence

        labels = [gate.name for gate in pre_pr_sequence._SEQUENCE]
        assert "Citation Freshness (added lines)" in labels
        # Identity is asserted between the two flat-imported modules (the
        # registry promise); ``checker`` here is the package-imported module,
        # a distinct module object for the same file, so it is compared by
        # source file rather than by function identity.
        assert pre_pr_sequence.validate_citation_freshness is pre_pr.validate_citation_freshness
        assert (
            pre_pr_sequence.validate_citation_freshness.__code__.co_filename
            == checker.validate_citation_freshness.__code__.co_filename
        )

    def test_gate_verdict_reaches_the_runner(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Drive run_all_validations twice, differing only in the gate's verdict.

        A registration-only assertion passes even when the callback is
        replaced with an always-true stub (Copilot, PR #5338); calling the
        real runner with a monkeypatched validator proves the by-name
        resolution in _root_only actually reaches this gate's verdict, with
        the passing run as the control.
        """
        import argparse
        from types import SimpleNamespace

        from scripts.validation import pre_pr_sequence

        repo_root = Path(__file__).resolve().parents[2]
        verdicts: dict[str, bool] = {}

        def fake_run_validation(
            name: str, _state: object, callback: object, skip: bool = False
        ) -> bool:
            if name == "Citation Freshness (added lines)" and callable(callback):
                verdicts["gate"] = bool(callback())
            return True

        state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
        args = argparse.Namespace(quick=True, skip_tests=False, verbose=False)

        monkeypatch.setattr(pre_pr_sequence, "validate_citation_freshness", lambda _root: False)
        pre_pr_sequence.run_all_validations(repo_root, args, state, fake_run_validation)
        assert verdicts["gate"] is False

        monkeypatch.setattr(pre_pr_sequence, "validate_citation_freshness", lambda _root: True)
        pre_pr_sequence.run_all_validations(repo_root, args, state, fake_run_validation)
        assert verdicts["gate"] is True

