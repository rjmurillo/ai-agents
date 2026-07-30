"""Tests for scripts/ci/build_retrospective_prompt.py (ADR-006, issue #3523).

The prompt moved out of a bash heredoc with an unquoted delimiter. Two things
must hold: the rendered text carries the same content lines the heredoc
produced, in the same order, and the template can no longer smuggle an
unsubstituted placeholder or an early delimiter into the step output.

Identity is compared on content lines rather than bytes because markdownlint
reshapes the extracted template: MD041 requires a top-level heading and MD032
requires blank lines around lists. Those are cosmetic. Comparing the ordered
non-blank lines still catches every regression that matters (a dropped line, a
mangled backtick, an unsubstituted placeholder).
"""

from __future__ import annotations

import string
from pathlib import Path

import pytest

from scripts.ci import build_retrospective_prompt as builder

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / ".github/prompts/post-pr-retrospective.md"


class TestRender:
    def test_every_placeholder_is_substituted(self) -> None:
        out = builder.render(
            "pr=$PR_NUMBER merged=$MERGED deep=$ESCALATE",
            {
                "PR_NUMBER": "42",
                "MERGED": "true",
                "ESCALATE": "false",
            },
        )
        assert out == "pr=42 merged=true deep=false"

    def test_braced_placeholders_are_substituted(self) -> None:
        assert builder.render("${PR_NUMBER}x", {"PR_NUMBER": "9"}) == "9x"

    def test_an_unsupplied_placeholder_raises_rather_than_leaking(self) -> None:
        with pytest.raises(KeyError):
            builder.render("$UNKNOWN", {"PR_NUMBER": "1"})

    def test_a_doubled_dollar_renders_as_a_literal_dollar(self) -> None:
        assert builder.render("cost $$5", {}) == "cost $5"

    def test_backticks_survive_unescaped(self) -> None:
        # The whole point of leaving the heredoc: no backslash needed.
        assert builder.render("use `git log`", {}) == "use `git log`"

    def test_text_with_no_placeholders_is_returned_unchanged(self) -> None:
        assert builder.render("plain text", {}) == "plain text"


class TestAppendMultilineOutput:
    def test_the_heredoc_block_is_well_formed(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        builder.append_multiline_output(out, "PROMPT", "line one\nline two\n")
        assert out.read_text(encoding="utf-8") == (
            "PROMPT<<RETRO_EOF\nline one\nline two\nRETRO_EOF\n"
        )

    def test_a_value_without_a_trailing_newline_gets_one(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        builder.append_multiline_output(out, "PROMPT", "no newline")
        assert out.read_text(encoding="utf-8").endswith("no newline\nRETRO_EOF\n")

    def test_appending_preserves_earlier_content(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        out.write_text("first=1\n", encoding="utf-8")
        builder.append_multiline_output(out, "PROMPT", "x")
        assert out.read_text(encoding="utf-8").startswith("first=1\nPROMPT<<RETRO_EOF\n")

    def test_a_value_carrying_the_delimiter_is_refused(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        with pytest.raises(ValueError, match="RETRO_EOF"):
            builder.append_multiline_output(out, "PROMPT", "before\nRETRO_EOF\nafter")

    def test_the_delimiter_check_ignores_surrounding_whitespace(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        with pytest.raises(ValueError):
            builder.append_multiline_output(out, "PROMPT", "a\n  RETRO_EOF  \nb")

    def test_the_delimiter_inside_a_longer_line_is_allowed(self, tmp_path: Path) -> None:
        # Only a line that is exactly the delimiter closes a heredoc.
        out = tmp_path / "out.txt"
        builder.append_multiline_output(out, "PROMPT", "see RETRO_EOF marker")
        assert "see RETRO_EOF marker" in out.read_text(encoding="utf-8")


class TestShippedTemplate:
    def test_the_template_exists_where_the_script_defaults_to(self) -> None:
        assert TEMPLATE.is_file()
        assert builder.TEMPLATE_PATH == Path(".github/prompts/post-pr-retrospective.md")

    def test_the_template_carries_no_backslash_escapes(self) -> None:
        # The heredoc needed `\`` on every backtick. A file needs none.
        assert "\\`" not in TEMPLATE.read_text(encoding="utf-8")

    def test_the_template_uses_exactly_the_declared_placeholders(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        found = {
            m.group("named") or m.group("braced")
            for m in string.Template.pattern.finditer(text)
            if m.group("named") or m.group("braced")
        }
        assert found == set(builder.PLACEHOLDERS)

    def test_the_shipped_template_renders_with_the_declared_placeholders(self) -> None:
        values = dict.fromkeys(builder.PLACEHOLDERS, "X")
        rendered = builder.render(TEMPLATE.read_text(encoding="utf-8"), values)
        assert "$" not in rendered

    def test_the_rendered_prompt_never_contains_the_output_delimiter(self, tmp_path: Path) -> None:
        values = dict.fromkeys(builder.PLACEHOLDERS, "X")
        rendered = builder.render(TEMPLATE.read_text(encoding="utf-8"), values)
        out = tmp_path / "out.txt"
        builder.append_multiline_output(out, "PROMPT", rendered)
        assert out.read_text(encoding="utf-8").count("RETRO_EOF") == 2


class TestWorkflowWiring:
    """The workflow must supply every placeholder the template declares.

    ``substitute`` raises ``KeyError`` on a name the caller did not pass, and
    the script turns that into a red step. Catching the mismatch here means a
    template edit fails review instead of failing production.
    """

    WORKFLOW = REPO_ROOT / ".github/workflows/post-pr-retrospective.yml"

    def _prompt_step(self) -> dict:
        import yaml

        data = yaml.safe_load(self.WORKFLOW.read_text(encoding="utf-8"))
        for job in data["jobs"].values():
            for step in job.get("steps", []):
                if step.get("id") == "prompt":
                    return step
        raise AssertionError("no step with id 'prompt' in the workflow")

    def test_the_workflow_still_invokes_the_extracted_builder(self) -> None:
        assert "build_retrospective_prompt.py" in self._prompt_step()["run"]

    def test_the_workflow_env_covers_every_declared_placeholder(self) -> None:
        supplied = set(self._prompt_step().get("env", {}))
        assert set(builder.PLACEHOLDERS) <= supplied

    def test_the_template_declares_nothing_the_workflow_cannot_supply(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        used = {
            m.group("named") or m.group("braced")
            for m in string.Template.pattern.finditer(text)
            if m.group("named") or m.group("braced")
        }
        assert used <= set(self._prompt_step().get("env", {}))


class TestMain:
    def _template(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "tpl.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_a_missing_github_output_is_a_config_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert builder.main([], env={}) == builder.EXIT_CONFIG
        assert "GITHUB_OUTPUT is required" in capsys.readouterr().err

    def test_a_missing_template_is_a_config_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = builder.main(
            ["--template", str(tmp_path / "nope.md")],
            env={"GITHUB_OUTPUT": str(tmp_path / "out.txt")},
        )
        assert rc == builder.EXIT_CONFIG
        assert "Prompt template not found" in capsys.readouterr().err

    def test_a_directory_passed_as_a_template_is_a_config_error(self, tmp_path: Path) -> None:
        rc = builder.main(
            ["--template", str(tmp_path)], env={"GITHUB_OUTPUT": str(tmp_path / "out.txt")}
        )
        assert rc == builder.EXIT_CONFIG

    def test_an_unknown_placeholder_in_the_template_is_a_config_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        tpl = self._template(tmp_path, "hello $NOT_DECLARED")
        rc = builder.main(
            ["--template", str(tpl)], env={"GITHUB_OUTPUT": str(tmp_path / "out.txt")}
        )
        assert rc == builder.EXIT_CONFIG
        assert "unknown placeholder" in capsys.readouterr().err

    def test_an_unknown_placeholder_writes_nothing_to_the_output(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        tpl = self._template(tmp_path, "hello $NOT_DECLARED")
        builder.main(["--template", str(tpl)], env={"GITHUB_OUTPUT": str(out)})
        assert not out.exists()

    def test_missing_environment_values_render_as_empty_not_as_a_crash(
        self, tmp_path: Path
    ) -> None:
        out = tmp_path / "out.txt"
        tpl = self._template(tmp_path, "pr=$PR_NUMBER!")
        assert builder.main(["--template", str(tpl)], env={"GITHUB_OUTPUT": str(out)}) == (
            builder.EXIT_OK
        )
        assert "pr=!" in out.read_text(encoding="utf-8")

    def test_the_happy_path_writes_the_substituted_prompt(self, tmp_path: Path) -> None:
        out = tmp_path / "out.txt"
        tpl = self._template(tmp_path, "pr=$PR_NUMBER merged=$MERGED deep=$ESCALATE")
        rc = builder.main(
            ["--template", str(tpl)],
            env={
                "GITHUB_OUTPUT": str(out),
                "PR_NUMBER": "77",
                "MERGED": "true",
                "ESCALATE": "false",
            },
        )
        assert rc == builder.EXIT_OK
        assert out.read_text(encoding="utf-8") == (
            "PROMPT<<RETRO_EOF\npr=77 merged=true deep=false\nRETRO_EOF\n"
        )

    def test_main_reads_the_process_environment_when_none_is_supplied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "out.txt"
        tpl = self._template(tmp_path, "pr=$PR_NUMBER")
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setenv("PR_NUMBER", "31")
        assert builder.main(["--template", str(tpl)]) == builder.EXIT_OK
        assert "pr=31" in out.read_text(encoding="utf-8")

    def test_the_default_template_path_resolves_from_the_repo_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The workflow runs with the repo root as cwd; prove the default works
        # there with no --template argument.
        out = tmp_path / "out.txt"
        monkeypatch.chdir(REPO_ROOT)
        rc = builder.main(
            [],
            env={
                "GITHUB_OUTPUT": str(out),
                "PR_NUMBER": "1",
                "MERGED": "true",
                "ESCALATE": "false",
            },
        )
        assert rc == builder.EXIT_OK
        assert out.read_text(encoding="utf-8").startswith("PROMPT<<RETRO_EOF\n")
