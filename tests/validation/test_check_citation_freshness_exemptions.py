"""Fence-level ignore and test-string scope for the citation gate.

Issue #6556 (defect D45): a JSON fence cannot hold the line-scoped marker,
and test data shaped like a citation is not a claim about the repository.
Fixture citations are composed from ``GONE``/``TARGET`` so this file's own
added lines never present a repo-relative citation to the gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import citation_scope
from tests.validation.citation_freshness_helpers import (
    GONE,
    TARGET,
    _add_doc,
    _repo,
    _run,
    checker,
)

MARKER = f"<!-- {checker.IGNORE_MARKER} -- illustrative JSON example -->"


def _json_fence(marker_line: str, fence: str = "```", body_ref: str = GONE) -> str:
    return f'{marker_line}\n{fence}json\n{{\n  "ref": "{body_ref}:7"\n}}\n{fence}\n'


class TestFenceLevelIgnore:
    def test_marker_above_a_backtick_fence_exempts_the_citation_inside(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "skills/x/SKILL.md", _json_fence(MARKER))

        code, _out = _run(root, capsys)

        assert code == 0

    def test_marker_above_a_tilde_fence_exempts_the_citation_inside(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "skills/x/SKILL.md", _json_fence(MARKER, fence="~~~"))

        code, _out = _run(root, capsys)

        assert code == 0

    def test_marker_exempts_every_citation_in_the_fence(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = f'{MARKER}\n```json\n{{\n  "a": "{GONE}:7",\n  "b": "{GONE}:9"\n}}\n```\n'
        _add_doc(root, "skills/x/SKILL.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0

    def test_fence_without_a_marker_is_still_policed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "skills/x/SKILL.md", _json_fence("Example:"))

        code, out = _run(root, capsys)

        assert code == 1
        assert f"{GONE}:7" in out

    def test_reasonless_marker_above_a_fence_does_not_exempt(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        bare = f"<!-- {checker.IGNORE_MARKER} -->"
        _add_doc(root, "skills/x/SKILL.md", _json_fence(bare))

        code, _out = _run(root, capsys)

        assert code == 1

    def test_blank_line_between_marker_and_fence_does_not_exempt(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Same adjacency rule as the line-scoped marker: directly above.
        root = _repo(tmp_path)
        _add_doc(root, "skills/x/SKILL.md", _json_fence(MARKER + "\n"))

        code, _out = _run(root, capsys)

        assert code == 1

    def test_marker_does_not_leak_past_the_closing_fence(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = _json_fence(MARKER) + f"\nAfter the fence, see {GONE}:3.\n"
        _add_doc(root, "skills/x/SKILL.md", doc)

        code, out = _run(root, capsys)

        assert code == 1
        assert f"{GONE}:3" in out
        assert f"{GONE}:7" not in out

    def test_shorter_inner_fence_does_not_end_the_outer_fence(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = f"{MARKER}\n````md\n```json\nsee {GONE}:7\n```\nsee {GONE}:8\n````\n"
        _add_doc(root, "skills/x/SKILL.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0

    def test_unclosed_fence_keeps_the_exemption_to_the_end_of_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "skills/x/SKILL.md", f"{MARKER}\n```json\nsee {GONE}:7\n")

        code, _out = _run(root, capsys)

        assert code == 0

    def test_marker_above_a_fence_is_markdown_only(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # In a .py file a triple-backtick line is not a fence.
        root = _repo(tmp_path)
        src = f'# {checker.IGNORE_MARKER} -- not a fence\n"""\n```\nsee {GONE}:7\n"""\n'
        _add_doc(root, "scripts/mod.py", src)

        code, _out = _run(root, capsys)

        assert code == 1

    def test_citation_to_a_real_file_inside_a_marked_fence_is_not_checked(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        doc = f'{MARKER}\n```json\n"{TARGET}:99"\n```\n'
        _add_doc(root, "skills/x/SKILL.md", doc)

        code, _out = _run(root, capsys)

        assert code == 0


class TestTestStringScope:
    def test_assertion_string_in_a_test_file_is_not_a_citation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "tests/test_x.py", f'def test_x():\n    assert out == "{GONE}:7"\n')

        code, _out = _run(root, capsys)

        assert code == 0

    def test_multiline_string_data_in_a_test_file_is_not_a_citation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        src = f'DOC = """\nline one\nsee {GONE}:7\n"""\n'
        _add_doc(root, "tests/test_x.py", src)

        code, _out = _run(root, capsys)

        assert code == 0

    def test_nested_tests_directory_counts_as_tests(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "pkg/tests/test_x.py", f'VALUE = "{GONE}:7"\n')

        code, _out = _run(root, capsys)

        assert code == 0

    def test_comment_in_a_test_file_is_still_policed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "tests/test_x.py", f"# Regression: see {GONE}:7\nVALUE = 1\n")

        code, out = _run(root, capsys)

        assert code == 1
        assert f"{GONE}:7" in out

    def test_docstring_in_a_test_file_is_still_policed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        src = f'def test_x():\n    """Covers {GONE}:7."""\n    assert True\n'
        _add_doc(root, "tests/test_x.py", src)

        code, out = _run(root, capsys)

        assert code == 1
        assert f"{GONE}:7" in out

    def test_module_docstring_in_a_test_file_is_still_policed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "tests/test_x.py", f'"""Covers {GONE}:7."""\n')

        code, _out = _run(root, capsys)

        assert code == 1

    def test_same_string_outside_tests_is_still_policed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "scripts/mod.py", f'VALUE = "{GONE}:7"\n')

        code, _out = _run(root, capsys)

        assert code == 1

    def test_unparseable_test_file_falls_back_to_policing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "tests/test_x.py", f'def broken(:\n    "{GONE}:7"\n')

        code, _out = _run(root, capsys)

        assert code == 1

    def test_markdown_under_tests_is_still_policed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _repo(tmp_path)
        _add_doc(root, "tests/README.md", f"See {GONE}:7.\n")

        code, _out = _run(root, capsys)

        assert code == 1


class TestScopeHelpers:
    def test_line_outside_every_fence_has_no_enclosing_fence(self) -> None:
        assert citation_scope.enclosing_fence_start(["a", "```", "b", "```", "c"], 5) is None

    def test_line_inside_a_fence_reports_the_opener_line(self) -> None:
        assert citation_scope.enclosing_fence_start(["a", "```", "b", "```", "c"], 3) == 2

    def test_closer_of_the_other_character_does_not_close(self) -> None:
        assert citation_scope.enclosing_fence_start(["```", "~~~", "x"], 3) == 1

    def test_closer_with_trailing_text_does_not_close(self) -> None:
        assert citation_scope.enclosing_fence_start(["```", "``` js", "x"], 3) == 1

    def test_empty_test_module_has_no_string_lines(self) -> None:
        assert citation_scope.string_literal_lines("tests/test_x.py", []) == frozenset()

    def test_non_python_file_has_no_string_lines(self) -> None:
        assert citation_scope.string_literal_lines("tests/data.md", ['"a"']) == frozenset()

    def test_multiline_string_covers_every_line_it_spans(self) -> None:
        lines = ["X = 1", 'Y = """', "a", '"""', "Z = 2"]
        assert citation_scope.string_literal_lines("tests/test_x.py", lines) == {2, 3, 4}
