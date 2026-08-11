"""PR body content validation tests for ``new_pr.py``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.new_pr_test_support import _completed, run_validations


class TestValidation5DashCheck:
    """Tests for Validation 5: em/en-dash guard on PR title and body."""

    def test_clean_title_and_body_passes(self, tmp_path, capsys):
        """No dashes in either title or body, run_validations completes."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(
                str(tmp_path),
                "main",
                "feat/branch",
                title="feat: clean title",
                body="body without dashes",
            )
        out = capsys.readouterr()
        assert "No prohibited characters" in out.out

    def test_em_dash_in_title_blocks(self, tmp_path):
        """Em-dash in title raises SystemExit(1)."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path),
                    "main",
                    "feat/branch",
                    title=f"feat: bad {chr(0x2014)} title",
                    body="clean body",
                )
            except SystemExit as exc:
                assert exc.code == 1
                return
            raise AssertionError("Expected SystemExit(1)")

    def test_en_dash_in_body_blocks(self, tmp_path):
        """En-dash in body raises SystemExit(1)."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path),
                    "main",
                    "feat/branch",
                    title="feat: clean",
                    body=f"range {chr(0x2013)} 10",
                )
            except SystemExit as exc:
                assert exc.code == 1
                return
            raise AssertionError("Expected SystemExit(1)")

    def test_dash_in_body_file_blocks(self, tmp_path):
        """Em-dash in body-file path raises SystemExit(1)."""
        body_file = tmp_path / "body.md"
        body_file.write_text(
            f"# Body\n\nLine with em-dash {chr(0x2014)} here\n",
            encoding="utf-8",
        )
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path),
                    "main",
                    "feat/branch",
                    title="feat: clean",
                    body_file=str(body_file),
                )
            except SystemExit as exc:
                assert exc.code == 1
                return
            raise AssertionError("Expected SystemExit(1)")

    def test_em_dash_error_message_includes_line_number(self, tmp_path, capsys):
        """Error stderr includes specific line numbers for actionable output."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path),
                    "main",
                    "feat/branch",
                    title="feat: clean",
                    body=(
                        f"line 1 clean\nline 2 has {chr(0x2014)} dash\n"
                        "line 3 clean\n"
                    ),
                )
            except SystemExit:
                pass
            stderr = capsys.readouterr().err
            assert "line 2" in stderr
            assert "U+2014" in stderr or "U+2013" in stderr


class TestValidation6EscapedNewlineCheck:
    """Validation 6 rejects bodies whose line breaks are literal escapes."""

    @staticmethod
    def _validate(tmp_path, *, body, body_file=None):
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(
                str(tmp_path),
                "main",
                "feat/branch",
                title="feat: clean title",
                body=body,
                body_file=body_file,
            )

    def test_escaped_newlines_with_no_real_break_blocks(self, tmp_path):
        with pytest.raises(SystemExit) as excinfo:
            self._validate(tmp_path, body="## Summary\\n\\nDetail\\n- item")
        assert excinfo.value.code == 1

    def test_error_names_the_count_and_the_remedy(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            self._validate(tmp_path, body="a\\nb\\nc")
        err = capsys.readouterr().err
        assert "2 literal backslash-n" in err
        assert "--body-file" in err

    def test_trailing_newline_only_body_still_blocks(self, tmp_path):
        """The measured shape of #3598: 15 escapes plus 1 real newline."""
        with pytest.raises(SystemExit) as excinfo:
            self._validate(tmp_path, body="## Summary\\n\\nDetail\\n" + "\n")
        assert excinfo.value.code == 1

    def test_escaped_newline_inside_a_real_multiline_body_passes(
        self, tmp_path, capsys
    ):
        self._validate(
            tmp_path,
            body='## Notes\n\n```python\nprint("a\\nb")\n```\n',
        )
        assert "Body line breaks are real newlines" in capsys.readouterr().out

    def test_normal_body_passes(self, tmp_path, capsys):
        self._validate(tmp_path, body="## Summary\n\nDetail\n")
        assert "Body line breaks are real newlines" in capsys.readouterr().out

    def test_single_line_body_without_escapes_passes(self, tmp_path, capsys):
        self._validate(tmp_path, body="Just one line.")
        assert "Body line breaks are real newlines" in capsys.readouterr().out

    def test_body_file_contents_are_checked_too(self, tmp_path):
        """--body-file is the recommended remedy, so it must not be a bypass."""
        path = tmp_path / "body.md"
        path.write_text("## Summary\\n\\nDetail", encoding="utf-8")
        with pytest.raises(SystemExit) as excinfo:
            self._validate(tmp_path, body="", body_file=str(path))
        assert excinfo.value.code == 1

    def test_quoted_canonical_predicate_is_verbatim(self):
        """The copied predicate documentation must match its canonical source."""
        import ast
        import textwrap

        repo_root = Path(__file__).resolve().parent.parent
        canonical = repo_root / "scripts" / "github_core" / "validation.py"
        tree = ast.parse(canonical.read_text(encoding="utf-8"))
        func = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "escaped_newline_body_error"
        )
        body_start = func.body[1].lineno
        lines = canonical.read_text(encoding="utf-8").splitlines()

        for mirror in (
            ".claude/skills/github/scripts/pr/validate_pr_description.py",
            "src/copilot-cli/skills/github/scripts/pr/validate_pr_description.py",
        ):
            module = ast.parse((repo_root / mirror).read_text(encoding="utf-8"))
            copy = next(
                node
                for node in ast.walk(module)
                if isinstance(node, ast.FunctionDef)
                and node.name == "validate_no_escaped_newlines"
            )
            doc = ast.get_docstring(copy, clean=False)
            assert doc is not None, mirror
            marker = "body::"
            assert marker in doc, f"{mirror}: citation marker missing"
            quoted = textwrap.dedent(
                doc.split(marker, 1)[1].split("\n\n", 2)[1]
            ).strip("\n")
            quoted_lines = quoted.splitlines()
            assert len(quoted_lines) >= 5, (
                f"{mirror}: quote too short to be the guard plus predicate: "
                f"{quoted_lines!r}"
            )
            actual = [
                line[4:]
                for line in lines[
                    body_start - 1 : body_start - 1 + len(quoted_lines)
                ]
            ]
            assert quoted_lines == actual, (
                f"{mirror}: quote is not verbatim.\n"
                f"quoted={quoted_lines!r}\nactual={actual!r}"
            )

    def test_chain_is_renumbered_to_six_steps(self, tmp_path, capsys):
        self._validate(tmp_path, body="## Summary\n\nDetail\n")
        out = capsys.readouterr().out
        for step in range(1, 7):
            assert f"[{step}/6]" in out, f"missing step {step}/6"
