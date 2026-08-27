"""Unified-diff parsing regressions for the citation gate.

Issue #5337; split from the scope test file at the taste file-size
ceiling, along the class seam. Regression provenance is per comment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.citation_freshness_helpers import (
    TARGET,
    _add_doc,
    _git,
    _repo,
    _run,
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

    def test_a_type_change_to_regular_file_is_scanned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 6, PR #5338): --diff-filter=ACMR
        # omitted type changes, so a symlink replaced by a regular file
        # carried its whole content as unscanned added lines.
        root = _repo(tmp_path)
        _git(root, "checkout", "-q", "main")
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / "link.md").symlink_to("../README.md")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "link")
        _git(root, "checkout", "-q", "feature")
        _git(root, "merge", "-q", "main")
        (root / "docs" / "link.md").unlink()
        (root / "docs" / "link.md").write_text(
            f"See `{TARGET}:2` (`magic_token`).\n", encoding="utf-8"
        )
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "replace")

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

    def test_c_quoted_citing_path_is_decoded(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Regression (Copilot round 5, PR #5338): git C-quotes a header
        # path carrying a quote even with core.quotePath=false, so the
        # citing file stopped matching its HEAD path and its stale
        # citation could pass unread. The shared unquoter decodes it.
        root = _repo(tmp_path)
        _add_doc(root, 'docs/od"d.md', f"See `{TARGET}:2` (`magic_token`).\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert 'od"d.md' in out

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
