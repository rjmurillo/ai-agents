"""Tests for multi-line Task() handling in copilot_body_translation (issue #5657)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

from copilot_body_translation import (  # noqa: E402
    _find_matching_paren,
    translate_body,
    translate_reference_file,
)
from copilot_support_translation import (  # noqa: E402
    SupportTranslationError,
    is_reference_markdown,
    translated_text,
)

_OUT = Path("/nonexistent/skills")
_PLUGIN = "project-toolkit"
_PROMPT_BODY = (
    "Review this ADR.\n"
    "\n"
    '**Role**: say "hello" (with a paren and an apostrophe: it\'s fine.\n'
    "| Claim | Result |\n"
    "|-------|--------|\n"
    "| x | y |\n"
)


def _multiline_task(subagent: str = "architect") -> str:
    return f'```python\nTask(subagent_type="{subagent}", prompt="""\n{_PROMPT_BODY}""")\n```\n'


# Positive: the block survives ------------------------------------------------


def test_triple_quoted_prompt_body_survives() -> None:
    translated = translate_body(_multiline_task(), _OUT)
    assert _PROMPT_BODY in translated
    assert translated.count("\n") == _multiline_task().count("\n")


def test_triple_quoted_call_is_rewritten_to_task_syntax() -> None:
    translated = translate_body(_multiline_task("critic"), _OUT)
    assert f'task(agent_type="{_PLUGIN}:critic", prompt="""' in translated
    assert "subagent_type" not in translated
    assert "Task(" not in translated


def test_keyword_arguments_on_separate_lines() -> None:
    source = (
        'Task(\n    subagent_type="orchestrator",\n    prompt="""\nTrigger the review.\n""",\n)\n'
    )
    translated = translate_body(source, _OUT)
    assert translated == (
        "task(\n"
        f'    agent_type="{_PLUGIN}:orchestrator",\n'
        '    prompt="""\n'
        "Trigger the review.\n"
        '""",\n'
        ")\n"
    )


def test_single_quoted_triple_delimiter_survives() -> None:
    source = "Task(subagent_type='critic', prompt='''\nbody (open paren\n''')\n"
    translated = translate_body(source, _OUT)
    assert "body (open paren\n" in translated
    assert f'agent_type="{_PLUGIN}:critic"' in translated


def test_call_inside_prompt_body_is_translated() -> None:
    source = (
        'Task(subagent_type="orchestrator", prompt="""\n'
        'Verify with Skill(skill="reviewer-findings") first.\n'
        '""")\n'
    )
    translated = translate_body(source, _OUT)
    assert 'Verify with `skill: "reviewer-findings"` first.' in translated
    assert "Skill(skill=" not in translated


def test_two_blocks_in_one_body_both_survive() -> None:
    source = _multiline_task("architect") + "\nprose between\n\n" + _multiline_task("critic")
    translated = translate_body(source, _OUT)
    assert translated.count(_PROMPT_BODY) == 2
    assert "prose between" in translated


# Negative: shapes that must not change -----------------------------------------


def test_single_line_task_keeps_inline_span_form() -> None:
    source = 'Run Task(subagent_type="analyst", prompt="check it") now.\n'
    translated = translate_body(source, _OUT)
    assert translated == f'Run `agent_type: "{_PLUGIN}:analyst"` with prompt "check it" now.\n'


def test_block_without_subagent_type_is_left_alone() -> None:
    source = 'Task(prompt="""\nbody\n""")\n'
    assert translate_body(source, _OUT) == source


def test_skill_call_with_triple_quoted_argument_is_left_alone() -> None:
    source = 'Skill(skill="memory", args="""\nbody\n""")\n'
    assert translate_body(source, _OUT) == source


def test_unterminated_triple_quote_is_left_alone() -> None:
    source = 'Task(subagent_type="critic", prompt="""\nnever closed\n'
    assert translate_body(source, _OUT) == source


def test_triple_quotes_inside_single_quoted_value_are_not_a_block() -> None:
    source = 'Task(subagent_type="critic", prompt=\'say """ now\')\n'
    translated = translate_body(source, _OUT)
    assert translated == f'`agent_type: "{_PLUGIN}:critic"` with prompt "say """ now"\n'


# Edge cases ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('f("""a)b""")', 11),
        ("f('''a)b''')", 11),
        ('f("")', 4),
        ('f("a)")', 6),
        ('f("""a)b""", 1)', 14),
        ('f("""unterminated)', -1),
    ],
)
def test_find_matching_paren_is_string_aware(text: str, expected: int) -> None:
    assert _find_matching_paren(text, 1) == expected


def test_escaped_triple_quote_does_not_close_block() -> None:
    source = 'Task(subagent_type="critic", prompt="""\nbody \\""" still body\n""")\n'
    translated = translate_body(source, _OUT)
    assert "still body" in translated
    assert f'agent_type="{_PLUGIN}:critic"' in translated


# Reference files -----------------------------------------------------------------


def test_reference_frontmatter_is_preserved_verbatim() -> None:
    source = "---\ntitle: $ARGUMENTS\n---\n" + _multiline_task()
    translated = translate_reference_file(source, _OUT)
    assert translated.startswith("---\ntitle: $ARGUMENTS\n---\n")
    assert _PROMPT_BODY in translated


def test_reference_without_frontmatter_is_translated() -> None:
    translated = translate_reference_file("Run $ARGUMENTS here.\n", _OUT)
    assert "$ARGUMENTS" not in translated


def test_reference_file_without_calls_is_unchanged() -> None:
    source = "# Notes\n\nPlain prose.\n"
    assert translate_reference_file(source, _OUT) == source


# Support-file dispatch ------------------------------------------------------------


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("references/steps.md", True),
        ("references/nested/steps.md", True),
        ("SKILL.md", False),
        ("references/data.txt", False),
        ("scripts/notes.md", False),
        ("notes.md", False),
        ("assets/references/steps.md", False),
    ],
)
def test_is_reference_markdown(rel: str, expected: bool) -> None:
    assert is_reference_markdown(Path(rel)) is expected


def test_translated_text_returns_none_for_plain_copy(tmp_path: Path) -> None:
    src = tmp_path / "run.py"
    src.write_text("print('hi')\n")
    assert translated_text(Path("scripts/run.py"), src, None, _OUT, frozenset()) is None


def test_translated_text_translates_reference_on_copilot_branch(tmp_path: Path) -> None:
    src = tmp_path / "steps.md"
    src.write_text("Run $ARGUMENTS.\n")
    result = translated_text(Path("references/steps.md"), src, None, _OUT, frozenset())
    assert result is not None
    assert "$ARGUMENTS" not in result


def test_translated_text_keeps_reference_verbatim_off_copilot_branch(tmp_path: Path) -> None:
    src = tmp_path / "steps.md"
    src.write_text("Run $ARGUMENTS.\n")
    assert translated_text(Path("references/steps.md"), src, None, None, frozenset({"x"})) is None


def test_translated_text_leaves_skill_md_alone_when_target_does_not_render(
    tmp_path: Path,
) -> None:
    src = tmp_path / "SKILL.md"
    src.write_text("source $ARGUMENTS\n")
    assert translated_text(Path("SKILL.md"), src, None, None, frozenset()) is None


def test_translated_text_prefers_plugin_skill_md(tmp_path: Path) -> None:
    src = tmp_path / "SKILL.md"
    src.write_text("source $ARGUMENTS\n")
    rendered = tmp_path / "rendered.md"
    rendered.write_text("rendered body\n")
    result = translated_text(Path("SKILL.md"), src, rendered, _OUT, frozenset())
    assert result == "rendered body\n"


def test_translated_text_wraps_frontmatter_errors(tmp_path: Path) -> None:
    src = tmp_path / "SKILL.md"
    src.write_text("---\nmodel: {a: 1,\nb: 2}\nname: x\n---\nbody\n")
    with pytest.raises(SupportTranslationError, match="SKILL.md"):
        translated_text(Path("SKILL.md"), src, None, _OUT, frozenset({"model"}))
