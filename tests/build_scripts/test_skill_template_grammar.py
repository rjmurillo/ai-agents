"""Tests for build/scripts/skill_template_grammar.py: grammar, partial-tree
validation, and render().

Split out of ``test_generate_skills_template_compile.py`` (taste-lint
file-size ceiling; ADR review round for #5706) along the same seam the
production module split uses: this file covers ``check_grammar`` and
``render`` (grammar, partial existence, partial trailing newlines, partial
cycles, and the post-render unresolved-tag scan); its sibling covers
``discover``, ``owned_targets``, ``compile_all``, the ``generate_skills.py``
wiring, and the CLI. Every case from the original file is kept; none was
dropped in the split. Tests reach ``check_grammar`` and ``render`` through
``skill_templates.<name>`` (the public re-export), proving that surface
still works, not through ``skill_template_grammar`` directly, except where a
test needs to patch something only that module's own globals resolve (see
the ``chevron`` monkeypatch below).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import skill_template_grammar  # noqa: E402
import skill_templates  # noqa: E402
from _skill_template_helpers import (  # noqa: E402
    seed_target_dir,
    target,
    write_partial,
    write_template,
)

# check_grammar() ----------------------------------------------------------------


def test_check_grammar_accepts_partial_and_comment_tags() -> None:
    text = "# X\n{{> hello-world}}\n{{! rule-source: voice.md }}\ndone\n"

    assert skill_templates.check_grammar(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "x {{var}} y",
        "x {{{raw}}} y",
        "x {{#section}} y {{/section}} z",
        "x {{^inverted}} y {{/inverted}} z",
        "x {{=<% %>=}} y",
        "x {{>Bad_Slug}} y",
    ],
)
def test_check_grammar_rejects_every_disallowed_construct(text: str) -> None:
    assert skill_templates.check_grammar(text) != []


def test_check_grammar_empty_text_is_clean() -> None:
    assert skill_templates.check_grammar("") == []


def test_check_grammar_accepts_an_indented_standalone_partial() -> None:
    """Grammar allows a partial "optionally indented" (module docstring)."""
    assert skill_templates.check_grammar("  {{> greet}}\n") == []


def test_check_grammar_rejects_a_partial_sharing_its_line_with_other_text() -> None:
    """CodeRabbit review, PR #5726: the own-line rule is part of the grammar
    the module docstring quotes from DESIGN-024, but a partial tag whose own
    syntax is valid previously passed even mid-sentence.
    """
    assert skill_templates.check_grammar("See {{> greet}} for details.\n") != []


def test_check_grammar_rejects_two_partials_sharing_one_line() -> None:
    assert skill_templates.check_grammar("{{> a}}{{> b}}\n") != []


# render() -------------------------------------------------------------------


def test_render_byte_identical_to_fixture_with_two_partials(tmp_path: Path) -> None:
    """Positive (DESIGN-024 case 1): template with two partials renders clean."""
    write_partial(tmp_path, "greet", "hello\n")
    write_partial(tmp_path, "farewell", "bye\n")
    tmpl = write_template(
        tmp_path,
        "sync",
        "# sync\n{{> greet}}\nmiddle\n{{> farewell}}\n",
    )

    rendered = skill_templates.render(tmpl, tmp_path / "templates" / "skills" / "partials")

    assert rendered == "# sync\nhello\nmiddle\nbye\n"


def test_render_preserves_crlf_line_endings(tmp_path: Path) -> None:
    """MINOR 3 (ADR review): a CRLF template is not normalized to LF on read.

    ``Path.read_text()`` with no ``newline=`` argument performs universal-
    newline translation (CRLF -> LF) regardless of platform; render() must
    read with ``newline=""`` so a template's original line endings pass
    through unchanged. Verified separately that chevron itself returns a
    tag-free CRLF string byte-identical, so this isolates render()'s own
    read behavior rather than chevron's.
    """
    templates_dir = tmp_path / "templates" / "skills"
    (templates_dir / "partials").mkdir(parents=True)
    tmpl = templates_dir / "sync.SKILL.md.tmpl"
    tmpl.write_bytes(b"first line\r\nsecond line\r\n")

    rendered = skill_templates.render(tmpl, templates_dir / "partials")

    assert rendered == "first line\r\nsecond line\r\n"


def test_compile_all_write_preserves_crlf_bytes_on_disk(tmp_path: Path) -> None:
    """MINOR 3 (ADR review), end to end through compile_all: write does not
    re-expand newlines to ``os.linesep`` on Windows (``newline="\\n"``
    forces exactly what the string contains onto disk). Asserted via raw
    bytes, not a text-mode re-read, which would mask the translation this
    test exists to catch.
    """
    templates_dir = tmp_path / "templates" / "skills"
    (templates_dir / "partials").mkdir(parents=True)
    (templates_dir / "sync.SKILL.md.tmpl").write_bytes(b"first line\r\nsecond line\r\n")
    seed_target_dir(tmp_path, "sync")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 0
    dst = target(tmp_path, "sync")
    assert dst.read_bytes() == b"first line\r\nsecond line\r\n"


def test_compile_all_partial_grammar_violation_leaves_target_untouched(
    tmp_path: Path,
) -> None:
    """compile_all-level, end to end: a grammar defect inside a partial
    exits 2 and never writes.
    """
    write_partial(tmp_path, "greet", "Hello {{name}}!\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("original\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert dst.read_text(encoding="utf-8") == "original\n"
    assert result.written == []


def test_render_missing_partial_raises_with_slug_and_path(tmp_path: Path) -> None:
    """Config error (DESIGN-024 case 2): exit 2, slug and path printed."""
    tmpl = write_template(tmp_path, "sync", "{{> nope}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"
    partials_dir.mkdir(parents=True)

    with pytest.raises(skill_templates.MissingPartialError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert "nope" in str(excinfo.value)
    assert str(tmpl) in str(excinfo.value)


def test_render_partial_missing_trailing_newline_raises_with_partial_path(
    tmp_path: Path,
) -> None:
    """Eleventh case (ADR review round 4): a partial with no exactly-one
    trailing newline is a config error, exit 2, reported with the partial
    path, before chevron ever runs.

    Reproduced against chevron==0.14.0 (skill_template_grammar's module
    docstring): without this check,
    ``chevron.render("Line before.\\n{{> p}}\\nLine after.\\n", {},
    partials_dict={"p": "X"})`` returns ``'Line before.\\nXLine after.\\n'``,
    silently gluing "Line after." onto the partial with no error and no
    leftover ``{{`` for the post-render scan to catch.
    """
    partial_path = write_partial(tmp_path, "no-newline", "no trailing newline")
    tmpl = write_template(tmp_path, "sync", "before\n{{> no-newline}}\nafter\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.PartialNewlineError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert str(partial_path) in str(excinfo.value)


def test_render_partial_with_two_trailing_newlines_also_raises(tmp_path: Path) -> None:
    """Edge: "exactly one" trailing newline, not "at least one"."""
    write_partial(tmp_path, "double-newline", "content\n\n")
    tmpl = write_template(tmp_path, "sync", "{{> double-newline}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.PartialNewlineError):
        skill_templates.render(tmpl, partials_dir)


def test_render_partial_with_exactly_one_trailing_newline_separates_lines(
    tmp_path: Path,
) -> None:
    """Positive control: a well-formed partial does not glue the next line."""
    write_partial(tmp_path, "ok", "content\n")
    tmpl = write_template(tmp_path, "sync", "before\n{{> ok}}\nafter\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    rendered = skill_templates.render(tmpl, partials_dir)

    assert rendered == "before\ncontent\nafter\n"


def test_render_disallowed_tag_raises_with_tag_text(tmp_path: Path) -> None:
    """Config error (DESIGN-024 case 3): exit 2, tag printed."""
    tmpl = write_template(tmp_path, "sync", "before {{var}} after\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"
    partials_dir.mkdir(parents=True)

    with pytest.raises(skill_templates.TemplateGrammarError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert "{{var}}" in str(excinfo.value)


def test_render_unclosed_tag_in_partial_raises_grammar_error_not_a_traceback(
    tmp_path: Path,
) -> None:
    """chevron raises ChevronError on a malformed partial (probed 2026-09-11
    against chevron==0.14.0: an unclosed tag with trailing content anywhere
    in a document chevron tokenizes propagates as
    ``chevron.tokenizer.ChevronError``, not silent empty text). This proves
    render() converts that into the module's own exit-2 exception instead of
    letting a raw chevron traceback escape.
    """
    write_partial(tmp_path, "leaky", "has {{ an unclosed tag\n")
    tmpl = write_template(tmp_path, "sync", "{{> leaky}}\n")

    with pytest.raises(skill_templates.TemplateGrammarError):
        skill_templates.render(tmpl, tmp_path / "templates" / "skills" / "partials")


# Recursive partial validation (BLOCKING, ADR review) -----------------------
#
# Probe that motivated this section, reproduced against this branch before
# the fix: partial greet.mustache = "Hello {{name}} and {{> nonexistent}}!\n",
# template = "{{> greet}}\n" rendered "Hello  and !\n" at exit 0, file
# written. The grammar and missing-partial checks ran on the template's own
# text only; a defect inside a partial's content was invisible to both.


def test_render_grammar_violation_inside_partial_raises_with_partial_path(
    tmp_path: Path,
) -> None:
    """A partial carrying {{var}} (a disallowed tag) exits 2, target untouched.

    Reproduces the BLOCKING probe's grammar half: greet.mustache containing
    a plain variable tag must fail exactly like a template containing one,
    not render as empty text.
    """
    partial_path = write_partial(tmp_path, "greet", "Hello {{name}}!\n")
    tmpl = write_template(tmp_path, "sync", "{{> greet}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.TemplateGrammarError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert str(partial_path) in str(excinfo.value)
    assert "{{name}}" in str(excinfo.value)


def test_render_partial_referencing_missing_nested_partial_raises(tmp_path: Path) -> None:
    """A partial referencing a nonexistent nested partial exits 2.

    Reproduces the BLOCKING probe's missing-partial half: greet.mustache
    naming a partial that does not exist must fail the same way a template
    naming one directly does, not render the reference away as empty text.
    """
    partial_path = write_partial(tmp_path, "greet", "Hello\n{{> nonexistent}}\n")
    tmpl = write_template(tmp_path, "sync", "{{> greet}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.MissingPartialError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert str(partial_path) in str(excinfo.value)
    assert "nonexistent" in str(excinfo.value)


def test_render_nested_partial_grammar_violation_two_levels_deep(tmp_path: Path) -> None:
    """Recursion goes past one level: a violation inside a partial's own
    included partial is caught too, not only one level below the template.
    """
    inner_path = write_partial(tmp_path, "inner", "bad {{var}}\n")
    write_partial(tmp_path, "outer", "wraps:\n{{> inner}}\n")
    tmpl = write_template(tmp_path, "sync", "{{> outer}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.TemplateGrammarError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert str(inner_path) in str(excinfo.value)


def test_render_partial_cycle_raises_config_error(tmp_path: Path) -> None:
    """A partial that transitively includes itself is a config error, exit 2.

    a -> b -> a. Without cycle detection this would recurse until Python's
    call-stack limit raised RecursionError, an unrelated crash rather than a
    controlled exit code.
    """
    write_partial(tmp_path, "a", "{{> b}}\n")
    write_partial(tmp_path, "b", "{{> a}}\n")
    tmpl = write_template(tmp_path, "sync", "{{> a}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.TemplateGrammarError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert "cycle" in str(excinfo.value)


def test_render_partial_self_cycle_raises_config_error(tmp_path: Path) -> None:
    """Edge: a partial referencing itself directly is also a cycle."""
    write_partial(tmp_path, "loop", "{{> loop}}\n")
    tmpl = write_template(tmp_path, "sync", "{{> loop}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.TemplateGrammarError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert "cycle" in str(excinfo.value)


def test_render_diamond_shaped_partial_reuse_is_not_a_cycle(tmp_path: Path) -> None:
    """Positive control: two siblings both including the same leaf partial
    is legitimate reuse, not a cycle, and must render cleanly.
    """
    write_partial(tmp_path, "leaf", "shared\n")
    write_partial(tmp_path, "a", "{{> leaf}}\n")
    write_partial(tmp_path, "b", "{{> leaf}}\n")
    tmpl = write_template(tmp_path, "sync", "{{> a}}\n{{> b}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    rendered = skill_templates.render(tmpl, partials_dir)

    assert rendered == "shared\nshared\n"


def test_render_raises_unresolved_tag_error_when_output_still_carries_braces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative (DESIGN-024 case 4): rendered output containing '{{' -> exit 1.

    No naturally occurring chevron document was found (probed 2026-09-11)
    that both renders successfully AND leaves a literal '{{' in its output;
    every attempt either raised ChevronError or had the brace consumed. The
    post-render scan is defense in depth against a future chevron version or
    an unforeseen input shape, so this test drives it directly by stubbing
    chevron.render's return value, isolating the scan from chevron's own
    (verified-safe) behavior.
    """
    tmpl = write_template(tmp_path, "sync", "{{! a comment }}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"
    partials_dir.mkdir(parents=True)
    # render() is defined in skill_template_grammar (skill_templates
    # re-exports it), so its `chevron` global resolves there.
    monkeypatch.setattr(
        skill_template_grammar.chevron, "render", lambda *a, **k: "still has {{ a tag\n"
    )

    with pytest.raises(skill_templates.UnresolvedTagError):
        skill_templates.render(tmpl, partials_dir)
