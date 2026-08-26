"""Citation freshness gate: added ``path:line`` claims verified against HEAD.

Issue #5337. The positive/negative pairs below reproduce the real stale
shapes PR #5336 repaired (a comment citation whose content moved down, a
docstring citation with an indented verbatim quote) and the plain-comment
identifier shape from the same incident.

Every fixture citation is composed with f-strings over the ``TARGET`` /
``GONE`` constants rather than written literally, so this test file's own
added lines never present a repo-relative citation to the gate under test
when it scans the branch that introduces them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_citation_freshness as checker

TARGET = "lib/util.py"
GONE = "lib/missing.py"

TARGET_CONTENT = "\n".join(
    [
        "# helper module",
        "PLACEHOLDER = 0",
        "def magic_token():",
        "    return 1",
        "TAIL = 2",
    ]
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "commit.gpgsign=false", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _repo(tmp_path: Path) -> Path:
    """Create a repo whose main branch tracks the cited target file."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    target = root / TARGET
    target.parent.mkdir(parents=True)
    target.write_text(TARGET_CONTENT + "\n", encoding="utf-8")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "feature")
    return root


def _add_doc(root: Path, relpath: str, text: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "docs")


def _run(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = checker.main(["--repo-root", str(root), "--base", "main"])
    return code, capsys.readouterr().out


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
        # the first cut excluded any such span, flagging a correct citation
        # found live in tests/test_model_pin_manifest.py (the `model` span
        # against a check_model_pins.py citation).
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"A truthy `PLACEHOLDER` or pin ({TARGET}:2).\n")

        code, _out = _run(root, capsys)

        assert code == 0

    def test_dotted_prose_anchor_matches_on_its_final_segment(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Prose says `mod.magic_token()` where the file only spells
        # `def magic_token`.
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", f"`mod.magic_token()` collects it ({TARGET}:3).\n")

        code, _out = _run(root, capsys)

        assert code == 0

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

    def test_plain_comment_identifier_anchor_fails_when_absent_from_range(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.py", f"# Matches {TARGET}:2's magic_token derivation\n")

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
        assert "docs/notes.md:1" in out

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

    def test_historical_roots_are_never_scanned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = f"See `{TARGET}:2` (`magic_token`).\n"
        _add_doc(root, ".agents/retrospective/2020-01-01-note.md", doc)

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

    def test_pathless_snippet_like_prose_never_matches(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "docs/notes.md", "Fix the null check at auth.ts:47 first.\n")

        code, out = _run(root, capsys)

        assert code == 0
        assert "examined 0 citation(s)" in out


class TestCliContract:
    def test_main_exits_2_outside_a_repository(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert checker.main(["--repo-root", str(tmp_path)]) == 2

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
