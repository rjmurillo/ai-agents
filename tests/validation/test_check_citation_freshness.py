"""Citation freshness gate: added ``path:line`` claims verified against HEAD.

Issue #5337. The positive/negative pairs reproduce the real stale shapes PR
#5336 repaired; scope-boundary, diff-parsing, and wiring coverage lives in
the sibling ``test_check_citation_freshness_scope.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import (
    GONE,
    TARGET,
    _add_doc,
    _repo,
    _run,
    checker,
)


class TestFreshCitationsPass:
    def test_anchored_citation_at_the_right_line_exits_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See `{TARGET}:3` (`magic_token`) here.\n")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 1 citation(s)" in out

    def test_range_citation_containing_the_anchor_exits_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See `{TARGET}:2-4` (`magic_token`).\n")

        code, _out = _run(root, capsys)

        assert code == 0

    def test_no_anchor_citation_is_checked_for_existence_and_range_only(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"More context in {TARGET}:2 today.\n")

        code, _out = _run(root, capsys)

        assert code == 0

    def test_anchor_that_is_a_substring_of_the_cited_path_still_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression: `util` is a fragment of the cited path's own name, and
        # the first cut excluded any such span from the anchor set (found
        # live on a `model` span against a check_model_pins.py citation).
        # The discriminating direction (CodeRabbit, PR #5338): a stale
        # citation whose ONLY anchor is that fragment must fail; the old
        # exclusion would leave it anchorless and vacuously passing.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"A `util` helper ({TARGET}:2).\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "'util'" in out

    def test_dotted_prose_anchor_matches_on_its_final_segment(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Prose says `mod.magic_token()` where the file only spells
        # `def magic_token`.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"`mod.magic_token()` collects it ({TARGET}:3).\n")

        code, _out = _run(root, capsys)

        assert code == 0

    def test_heading_with_colon_never_harvests_a_continuation_quote(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot, PR #5341): the markdown flag reached
        # _context_lines only, so a heading ending in a colon still took
        # the indented body below it as a required continuation quote and
        # failed a valid citation. A heading is a complete unit there too.
        root = _repo(tmp_path)
        doc = f"## About {TARGET}:2:\n\n    magic_token\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 1 citation(s)" in out

    def test_indented_continuation_quote_present_in_range_exits_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = f"{TARGET}:3-4 (the token helper):\n\n    def magic_token():\n"
        _add_doc(root, "docs/notes.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0



class TestStaleCitationsFail:
    def test_moved_content_fails_and_reports_the_real_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See `{TARGET}:2` (`magic_token`).\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "'magic_token' first appears at line 3" in out

    def test_relocation_hint_survives_whitespace_differences(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Spec-validation finding (PR #5338): the hint search matched
        # literally, so a re-spaced anchor produced a finding with no
        # relocated line named. The search reuses _anchor_matches now.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f'"PLACEHOLDER  =  0" sits at {TARGET}:4.\n')

        code, out = _run(root, capsys)

        assert code == 1
        assert "first appears at line 2" in out

    def test_relocation_hint_finds_an_anchor_wrapped_across_lines(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 7, PR #5338): the hint searched one
        # line at a time, so an anchor spanning a line break in the cited
        # file produced a finding with no relocated line named. The
        # two-line window pass names it.
        root = _repo(tmp_path)
        doc = f'"PLACEHOLDER = 0 def magic_token():" sits at {TARGET}:5.\n'
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 1
        assert "first appears at line 2" in out

    def test_out_of_range_citation_names_the_relocated_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Same round: an out-of-range citation returned before anchor
        # extraction, so the exact moved-content case the hint exists to
        # repair got only the file length.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See `{TARGET}:9` (`magic_token`).\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "has 5 lines at HEAD; 'magic_token' first appears at line 3" in out

    def test_plain_comment_identifier_anchor_fails_when_absent_from_range(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.py", f"# Matches {TARGET}:2's magic_token derivation\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "magic_token" in out

    def test_comment_continuation_anchor_still_joins_in_code_files(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The heading boundary is Markdown-only (Copilot, PR #5341): in a
        # code file a hash prefix is a comment, and a wrapped comment
        # sentence still hands its identifier to the citation below, so
        # this stale citation must keep failing on that anchor.
        root = _repo(tmp_path)
        doc = f"# The magic_token helper is defined at\n# {TARGET}:2 in the tree.\n"
        _add_doc(root, "docs/notes.py", doc)

        code, out = _run(root, capsys)

        assert code == 1
        assert "magic_token" in out

    def test_indented_continuation_quote_absent_from_range_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = f"{TARGET}:1-2 (the token helper):\n\n    def magic_token():\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 1
        # Composed, not literal: a literal expected-finding string is itself
        # a citation to an untracked path, and the gate flagged this very
        # line when it was first written literally.
        assert f"{'docs/notes.md'}:1" in out

    def test_untracked_file_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See {GONE}:1 for details.\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "not tracked at HEAD" in out

    def test_out_of_range_line_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See {TARGET}:999 for details.\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "has 5 lines at HEAD" in out

    def test_reversed_range_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See {TARGET}:4-2 for details.\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "reversed" in out

    def test_one_bad_citation_among_good_ones_still_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = f"See {TARGET}:3 (`magic_token`) and {GONE}:1 too.\n"
        _add_doc(root, "docs/notes.md", doc)

        code, out = _run(root, capsys)

        assert code == 1
        assert out.count("not tracked at HEAD") == 1

    def test_line_zero_citation_fails_instead_of_slicing_to_empty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot, PR #5338): cited_lines[-1:0] is empty, so an
        # anchorless line-zero citation sailed past range validation.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"More context in {TARGET}:0 today.\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert "1-based" in out



class TestCliContract:
    def test_main_exits_2_outside_a_repository(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert checker.main(["--repo-root", str(tmp_path)]) == 2

    def test_git_show_failure_is_exit_2_not_a_finding(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Regression (Copilot round 7, PR #5338): a mid-run git show
        # failure was reported as a stale-citation finding (exit 1); an
        # operational failure is the documented config-error exit 2.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See `{TARGET}:2` (`magic_token`).\n")
        import citation_head_state

        def boom(_self: object, path: str) -> list[str]:
            raise citation_head_state.HeadReadError(path)

        monkeypatch.setattr(citation_head_state._HeadFileCache, "lines", boom)

        code, _out = _run(root, capsys)

        assert code == 2

    def test_main_exits_2_when_git_fails_mid_run(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 3, PR #5338): the diff-collection
        # failure branch was untested, so a git failure after the repo
        # check could have silently passed instead of exiting 2.
        root = _repo(tmp_path)

        code = checker.main(["--repo-root", str(root), "--base", "does-not-exist"])

        assert code == 2
        assert "git failed" in capsys.readouterr().err

    def test_main_skips_cleanly_when_no_base_resolves(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _repo(tmp_path)
        monkeypatch.setattr(checker, "_resolve_default_base_ref", lambda _root: None)

        code = checker.main(["--repo-root", str(root)])

        assert code == 0
        assert "[SKIP]" in capsys.readouterr().out

    def test_validate_wrapper_returns_false_on_git_failure(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Spec-validation nit (PR #5338): the boolean wrapper's git-failure
        # branch is the one pre_pr actually calls; pin it directly.
        root = _repo(tmp_path)
        monkeypatch.setattr(
            checker, "_resolve_default_base_ref", lambda _root: "does-not-exist"
        )

        assert checker.validate_citation_freshness(root) is False

    def test_validate_wrapper_returns_false_on_findings(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See `{TARGET}:2` (`magic_token`).\n")
        monkeypatch.setattr(checker, "_resolve_default_base_ref", lambda _root: "main")

        assert checker.validate_citation_freshness(root) is False

    def test_validate_wrapper_returns_true_when_clean(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"See `{TARGET}:3` (`magic_token`).\n")
        monkeypatch.setattr(checker, "_resolve_default_base_ref", lambda _root: "main")

        assert checker.validate_citation_freshness(root) is True


