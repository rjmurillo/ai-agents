"""Tests for build/scripts/skill_templates.py and its generate_skills.py wiring.

Covers the nine cases in DESIGN-020's Tests table
(``.agents/specs/design/DESIGN-020-skill-guidance-excerpt-sync.md``, "Tests")
for the ADR-108 compile module, plus positive/negative/edge unit coverage on
each exported function per ``.agents/governance/TESTING-RIGOR.md``, plus a
tenth case added in ADR review for #5706, before merge: a NO-REGEN-protected
target must be left unchanged, not counted as drift, for both sentinel forms
``regen_guard.detect_reason`` recognizes -- and, per a final review-round
change, must fail closed with exit 1 in every mode (write, validate), not
exit 0. See ``skill_templates.compile_all``'s "Stricter/looser/different
than canonical" docstring section for why this diverges from DESIGN-020's
own "skipped, NOTICE printed, exit 0" table entry.

An eleventh case, added in ADR review round 4: a referenced partial missing
exactly one trailing newline is a config error, exit 2, reported with the
partial's path, target untouched -- chevron glues a newline-less partial
onto the template text that follows its tag with no error and no ``{{`` left
over, so nothing else in this module would have caught it. See
``skill_templates``'s module docstring for the reproduction.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import generate_skills  # noqa: E402
import skill_templates  # noqa: E402

_GENERATE_SKILLS_PATH = REPO_ROOT / "build" / "scripts" / "generate_skills.py"

# Helpers ---------------------------------------------------------------------


def _write_template(repo: Path, name: str, body: str) -> Path:
    templates_dir = repo / "templates" / "skills"
    templates_dir.mkdir(parents=True, exist_ok=True)
    path = templates_dir / f"{name}.SKILL.md.tmpl"
    path.write_text(body, encoding="utf-8")
    return path


def _write_partial(repo: Path, slug: str, body: str) -> Path:
    partials_dir = repo / "templates" / "skills" / "partials"
    partials_dir.mkdir(parents=True, exist_ok=True)
    path = partials_dir / f"{slug}.mustache"
    path.write_text(body, encoding="utf-8")
    return path


def _target(repo: Path, name: str) -> Path:
    return repo / ".claude" / "skills" / name / "SKILL.md"


def _seed_target_dir(repo: Path, name: str) -> Path:
    target = _target(repo, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


# discover() -------------------------------------------------------------------


def test_discover_returns_empty_mapping_when_templates_dir_absent(tmp_path: Path) -> None:
    assert skill_templates.discover(tmp_path) == {}


def test_discover_finds_templates_by_stripped_filename(tmp_path: Path) -> None:
    _write_template(tmp_path, "sync", "body\n")
    _write_template(tmp_path, "test", "body\n")
    _seed_target_dir(tmp_path, "sync")
    _seed_target_dir(tmp_path, "test")

    found = skill_templates.discover(tmp_path)

    assert set(found) == {"sync", "test"}
    assert found["sync"] == tmp_path / "templates" / "skills" / "sync.SKILL.md.tmpl"


def test_discover_ignores_files_without_the_exact_suffix(tmp_path: Path) -> None:
    templates_dir = tmp_path / "templates" / "skills"
    templates_dir.mkdir(parents=True)
    (templates_dir / "README.md").write_text("not a template\n")
    (templates_dir / "sync.SKILL.md").write_text("missing .tmpl suffix\n")

    assert skill_templates.discover(tmp_path) == {}


def test_discover_excludes_a_bad_name(tmp_path: Path) -> None:
    """PR review of ADR-108: a name that does not match
    ``^[a-z0-9]+(-[a-z0-9]+)*$`` never reaches discover()'s mapping.
    """
    _write_template(tmp_path, "Bad_Name", "body\n")
    (tmp_path / ".claude" / "skills" / "Bad_Name").mkdir(parents=True)

    assert skill_templates.discover(tmp_path) == {}


def test_discover_excludes_a_name_with_no_skill_directory(tmp_path: Path) -> None:
    """PR review of ADR-108: a valid-shaped name with no existing
    ``.claude/skills/<name>/`` never reaches discover()'s mapping. Every
    template-owned skill converts an EXISTING skill; nothing in this class
    creates one from nothing.
    """
    _write_template(tmp_path, "sync", "body\n")
    # No .claude/skills/sync/ directory created at all.

    assert skill_templates.discover(tmp_path) == {}


def test_discover_errors_reports_the_bad_name_with_template_path(tmp_path: Path) -> None:
    tmpl = _write_template(tmp_path, "Bad_Name", "body\n")
    (tmp_path / ".claude" / "skills" / "Bad_Name").mkdir(parents=True)

    errors = skill_templates.discover_errors(tmp_path)

    assert len(errors) == 1
    assert str(tmpl) in errors[0]
    assert "Bad_Name" in errors[0]


def test_discover_errors_reports_the_missing_skill_directory_with_template_path(
    tmp_path: Path,
) -> None:
    tmpl = _write_template(tmp_path, "sync", "body\n")

    errors = skill_templates.discover_errors(tmp_path)

    assert len(errors) == 1
    assert str(tmpl) in errors[0]
    assert ".claude/skills/sync" in errors[0]


def test_discover_errors_empty_on_a_clean_tree(tmp_path: Path) -> None:
    _write_template(tmp_path, "sync", "body\n")
    _seed_target_dir(tmp_path, "sync")

    assert skill_templates.discover_errors(tmp_path) == []


def test_compile_all_reports_a_bad_name_as_exit_2_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tmpl = _write_template(tmp_path, "Bad_Name", "body\n")
    (tmp_path / ".claude" / "skills" / "Bad_Name").mkdir(parents=True)

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert result.written == []
    assert str(tmpl) in capsys.readouterr().err


def test_compile_all_reports_a_missing_skill_directory_as_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tmpl = _write_template(tmp_path, "sync", "body\n")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert result.written == []
    assert str(tmpl) in capsys.readouterr().err


def test_owned_targets_excludes_an_invalid_name(tmp_path: Path) -> None:
    _write_template(tmp_path, "Bad_Name", "body\n")
    (tmp_path / ".claude" / "skills" / "Bad_Name").mkdir(parents=True)

    assert skill_templates.owned_targets(tmp_path) == set()


# owned_targets() ---------------------------------------------------------------


def test_owned_targets_empty_when_no_templates(tmp_path: Path) -> None:
    assert skill_templates.owned_targets(tmp_path) == set()


def test_owned_targets_maps_each_template_to_its_claude_skills_path(tmp_path: Path) -> None:
    _write_template(tmp_path, "sync", "body\n")
    _seed_target_dir(tmp_path, "sync")

    assert skill_templates.owned_targets(tmp_path) == {
        tmp_path / ".claude" / "skills" / "sync" / "SKILL.md"
    }


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


# render() -------------------------------------------------------------------


def test_render_byte_identical_to_fixture_with_two_partials(tmp_path: Path) -> None:
    """Positive (DESIGN-020 case 1): template with two partials renders clean."""
    _write_partial(tmp_path, "greet", "hello\n")
    _write_partial(tmp_path, "farewell", "bye\n")
    tmpl = _write_template(
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
    """MINOR 3 (ADR review): compile_all's write does not re-expand newlines.

    ``Path.write_text()`` with no ``newline=`` argument substitutes
    ``os.linesep`` for every ``\\n`` in the string, a no-op on POSIX but a
    CRLF re-expansion on Windows. Writing with ``newline="\\n"`` forces
    exactly what the string contains onto disk. Asserted via the target's
    raw bytes, not a text-mode re-read, which would mask the very
    translation this test exists to catch (mirrors
    ``generate_pr_quality_prompts.py``'s ``open(..., newline="\\n")`` write).
    """
    templates_dir = tmp_path / "templates" / "skills"
    (templates_dir / "partials").mkdir(parents=True)
    (templates_dir / "sync.SKILL.md.tmpl").write_bytes(b"first line\r\nsecond line\r\n")
    _seed_target_dir(tmp_path, "sync")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 0
    target = _target(tmp_path, "sync")
    assert target.read_bytes() == b"first line\r\nsecond line\r\n"


def test_render_missing_partial_raises_with_slug_and_path(tmp_path: Path) -> None:
    """Config error (DESIGN-020 case 2): exit 2, slug and path printed."""
    tmpl = _write_template(tmp_path, "sync", "{{> nope}}\n")
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

    Reproduced against chevron==0.14.0 (module docstring): without this
    check, ``chevron.render("Line before.\\n{{> p}}\\nLine after.\\n", {},
    partials_dict={"p": "X"})`` returns ``'Line before.\\nXLine after.\\n'``,
    silently gluing "Line after." onto the partial with no error and no
    leftover ``{{`` for the post-render scan to catch.
    """
    partial_path = _write_partial(tmp_path, "no-newline", "no trailing newline")
    tmpl = _write_template(tmp_path, "sync", "before\n{{> no-newline}}\nafter\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.PartialNewlineError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert str(partial_path) in str(excinfo.value)


def test_render_partial_with_two_trailing_newlines_also_raises(tmp_path: Path) -> None:
    """Edge: "exactly one" trailing newline, not "at least one"."""
    _write_partial(tmp_path, "double-newline", "content\n\n")
    tmpl = _write_template(tmp_path, "sync", "{{> double-newline}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.PartialNewlineError):
        skill_templates.render(tmpl, partials_dir)


def test_render_partial_with_exactly_one_trailing_newline_separates_lines(
    tmp_path: Path,
) -> None:
    """Positive control: a well-formed partial does not glue the next line."""
    _write_partial(tmp_path, "ok", "content\n")
    tmpl = _write_template(tmp_path, "sync", "before\n{{> ok}}\nafter\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    rendered = skill_templates.render(tmpl, partials_dir)

    assert rendered == "before\ncontent\nafter\n"


def test_render_disallowed_tag_raises_with_tag_text(tmp_path: Path) -> None:
    """Config error (DESIGN-020 case 3): exit 2, tag printed."""
    tmpl = _write_template(tmp_path, "sync", "before {{var}} after\n")
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
    _write_partial(tmp_path, "leaky", "has {{ an unclosed tag\n")
    tmpl = _write_template(tmp_path, "sync", "{{> leaky}}\n")

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
    partial_path = _write_partial(tmp_path, "greet", "Hello {{name}}!\n")
    tmpl = _write_template(tmp_path, "sync", "{{> greet}}\n")
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
    partial_path = _write_partial(tmp_path, "greet", "Hello {{> nonexistent}}!\n")
    tmpl = _write_template(tmp_path, "sync", "{{> greet}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.MissingPartialError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert str(partial_path) in str(excinfo.value)
    assert "nonexistent" in str(excinfo.value)


def test_render_nested_partial_grammar_violation_two_levels_deep(tmp_path: Path) -> None:
    """Recursion goes past one level: a violation inside a partial's own
    included partial is caught too, not only one level below the template.
    """
    inner_path = _write_partial(tmp_path, "inner", "bad {{var}}\n")
    _write_partial(tmp_path, "outer", "wraps: {{> inner}}\n")
    tmpl = _write_template(tmp_path, "sync", "{{> outer}}\n")
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
    _write_partial(tmp_path, "a", "{{> b}}\n")
    _write_partial(tmp_path, "b", "{{> a}}\n")
    tmpl = _write_template(tmp_path, "sync", "{{> a}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.TemplateGrammarError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert "cycle" in str(excinfo.value)


def test_render_partial_self_cycle_raises_config_error(tmp_path: Path) -> None:
    """Edge: a partial referencing itself directly is also a cycle."""
    _write_partial(tmp_path, "loop", "{{> loop}}\n")
    tmpl = _write_template(tmp_path, "sync", "{{> loop}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    with pytest.raises(skill_templates.TemplateGrammarError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert "cycle" in str(excinfo.value)


def test_render_diamond_shaped_partial_reuse_is_not_a_cycle(tmp_path: Path) -> None:
    """Positive control: two siblings both including the same leaf partial
    is legitimate reuse, not a cycle, and must render cleanly.
    """
    _write_partial(tmp_path, "leaf", "shared\n")
    _write_partial(tmp_path, "a", "{{> leaf}}\n")
    _write_partial(tmp_path, "b", "{{> leaf}}\n")
    tmpl = _write_template(tmp_path, "sync", "{{> a}}{{> b}}")
    partials_dir = tmp_path / "templates" / "skills" / "partials"

    rendered = skill_templates.render(tmpl, partials_dir)

    assert rendered == "shared\nshared\n"


def test_compile_all_partial_grammar_violation_leaves_target_untouched(
    tmp_path: Path,
) -> None:
    """compile_all-level: a defect inside a partial exits 2 and never writes."""
    _write_partial(tmp_path, "greet", "Hello {{name}}!\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("original\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert target.read_text(encoding="utf-8") == "original\n"
    assert result.written == []


def test_render_raises_unresolved_tag_error_when_output_still_carries_braces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative (DESIGN-020 case 4): rendered output containing '{{' -> exit 1.

    No naturally occurring chevron document was found (probed 2026-09-11)
    that both renders successfully AND leaves a literal '{{' in its output;
    every attempt either raised ChevronError or had the brace consumed. The
    post-render scan is defense in depth against a future chevron version or
    an unforeseen input shape, so this test drives it directly by stubbing
    chevron.render's return value, isolating the scan from chevron's own
    (verified-safe) behavior.
    """
    tmpl = _write_template(tmp_path, "sync", "{{! a comment }}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"
    partials_dir.mkdir(parents=True)
    monkeypatch.setattr(
        skill_templates.chevron, "render", lambda *a, **k: "still has {{ a tag\n"
    )

    with pytest.raises(skill_templates.UnresolvedTagError):
        skill_templates.render(tmpl, partials_dir)


# compile_all() ----------------------------------------------------------------


def test_compile_all_writes_rendered_bytes_when_target_missing(tmp_path: Path) -> None:
    """Positive (DESIGN-020 case 1, end to end): exit 0, file written.

    The skill's directory already exists (as it does for every A2 pilot
    skill, already tracked under ``.claude/skills/``) but carries no
    ``SKILL.md`` yet.
    """
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "# sync\n{{> greet}}\ndone\n")
    _seed_target_dir(tmp_path, "sync")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 0
    target = _target(tmp_path, "sync")
    assert str(target) in result.written
    assert target.read_text(encoding="utf-8") == "# sync\nhi\ndone\n"


def test_compile_all_missing_partial_leaves_target_untouched(tmp_path: Path) -> None:
    _write_template(tmp_path, "sync", "{{> nope}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("original\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert target.read_text(encoding="utf-8") == "original\n"


def test_compile_all_partial_missing_trailing_newline_leaves_target_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Eleventh case (ADR review round 4): a referenced partial with no
    exactly-one trailing newline is a config error, exit 2, reported with
    the partial path, target untouched.
    """
    partial_path = _write_partial(tmp_path, "no-newline", "no trailing newline")
    _write_template(tmp_path, "sync", "{{> no-newline}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("original\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert target.read_text(encoding="utf-8") == "original\n"
    assert result.written == []
    assert str(partial_path) in capsys.readouterr().err


def test_compile_all_disallowed_tag_leaves_target_untouched(tmp_path: Path) -> None:
    _write_template(tmp_path, "sync", "{{var}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("original\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert target.read_text(encoding="utf-8") == "original\n"


def test_compile_all_skips_skill_with_no_template(tmp_path: Path) -> None:
    """Edge (DESIGN-020 case 5): a skill with no template is untouched.

    ``.claude/skills/other/SKILL.md`` exists on disk (a hand-maintained
    skill) but has no matching ``templates/skills/other.SKILL.md.tmpl``, so
    compile_all never visits it: discover() only enumerates templates.
    """
    other_target = _seed_target_dir(tmp_path, "other")
    other_target.write_text("hand maintained\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 0
    assert result.written == []
    assert other_target.read_text(encoding="utf-8") == "hand maintained\n"


def _apply_html_comment_sentinel(target: Path) -> None:
    target.write_text("<!-- NO-REGEN: manual edit -->\nhand edited\n", encoding="utf-8")


def _apply_hash_comment_sentinel(target: Path) -> None:
    target.write_text("# NO-REGEN: manual edit\nhand edited\n", encoding="utf-8")


def _apply_sidecar_sentinel(target: Path) -> None:
    target.write_text("hand edited\n", encoding="utf-8")
    target.with_suffix(target.suffix + ".noregen").write_text("", encoding="utf-8")


_NO_REGEN_SENTINEL_FORMS = pytest.mark.parametrize(
    "apply_sentinel",
    [_apply_html_comment_sentinel, _apply_hash_comment_sentinel, _apply_sidecar_sentinel],
    ids=["html-comment", "hash-comment", "sidecar"],
)


@_NO_REGEN_SENTINEL_FORMS
def test_compile_all_skips_no_regen_target_with_warn_and_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    apply_sentinel: Callable[[Path], None],
) -> None:
    """Edge (DESIGN-020 case 6, diverged in ADR review): NO-REGEN sentinel
    on a template-owned target -> unchanged, WARN, exit 1 (not exit 0).

    Covers all three sentinel forms ``regen_guard.detect_reason`` recognizes
    (MINOR 1, ADR review): an in-file ``<!-- NO-REGEN`` HTML comment, an
    in-file ``# NO-REGEN`` hash comment, and a ``.noregen`` sidecar file.

    WARN, not NOTICE: the sentinel exempts a template-owned file from this
    class's only gate (ADR-108 section 4), so the skip is louder than the
    NOTICE ``generate_skills._copy_skill_tree`` prints for an ordinary
    non-generated skill file. Exit 1, not DESIGN-020's exit 0: a sentinel
    that could silence the drift gate and still report a clean run would
    make the gate advisory (see compile_all's "Stricter/looser/different
    than canonical" docstring section).
    """
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    apply_sentinel(target)
    original = target.read_text(encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 1
    assert str(target) in result.skipped
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "template-owned file exempt from drift gate" in out
    assert target.read_text(encoding="utf-8") == original


def test_compile_all_validate_mode_never_writes_on_missing_target(tmp_path: Path) -> None:
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    _seed_target_dir(tmp_path, "sync")

    result = skill_templates.compile_all(tmp_path, validate=True)

    assert result.exit_code == 1
    assert not _target(tmp_path, "sync").exists()


def test_compile_all_validate_on_hand_edited_target(tmp_path: Path) -> None:
    """Negative (DESIGN-020 case 7): --validate on a hand-edited target.

    exit 1, path printed, target untouched.
    """
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("hand edited, not the template render\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=True)

    assert result.exit_code == 1
    assert str(target) in result.drifted
    assert target.read_text(encoding="utf-8") == "hand edited, not the template render\n"


@_NO_REGEN_SENTINEL_FORMS
def test_compile_all_validate_skips_no_regen_target_not_counted_as_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    apply_sentinel: Callable[[Path], None],
) -> None:
    """Tenth case (ADR review, final round): validate mode honors NO-REGEN
    too: skipped with the same WARN as the write path, NOT reported as
    drift, target left unchanged -- and, per the final review-round
    decision, exit 1 rather than exit 0, since the sentinel must fail
    closed in every mode.

    Covers all three sentinel forms regen_guard.detect_reason recognizes
    (MINOR 1, ADR review): an in-file ``<!-- NO-REGEN`` HTML comment, an
    in-file ``# NO-REGEN`` hash comment, and a ``.noregen`` sidecar file.

    The sentinel is the author's declared intent to diverge from the
    template; validate mode's job is to catch an UNDECLARED divergence, so
    treating a NO-REGEN target as drift-in-the-``drifted``-list sense would
    flag exactly the case the sentinel exists to silence. It still has to
    surface as a non-zero exit, or a target that opted all the way out of
    ADR-108's gate would report success right alongside a target the gate
    actually checked.
    """
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    apply_sentinel(target)
    original = target.read_text(encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=True)

    assert result.exit_code == 1
    assert result.drifted == []
    assert str(target) in result.skipped
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "template-owned file exempt from drift gate" in out
    assert target.read_text(encoding="utf-8") == original


def test_compile_all_validate_on_clean_tree(tmp_path: Path) -> None:
    """Positive (DESIGN-020 case 8): --validate on a clean tree -> exit 0."""
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("hi\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=True)

    assert result.exit_code == 0
    assert result.drifted == []
    assert result.written == []


def test_compile_all_missing_target_directory_is_a_config_error(tmp_path: Path) -> None:
    """No ``.claude/skills/sync/`` at all: caught by ``discover_errors()``
    before this template ever reaches compile_all's per-template loop (PR
    review of ADR-108), not by a separate ``target.parent.is_dir()`` check
    inside that loop, which discover()'s new precondition made unreachable
    and which was removed.
    """
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    # No .claude/skills/sync/ directory created at all.

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert not _target(tmp_path, "sync").exists()


def test_compile_all_what_if_reports_without_writing(tmp_path: Path) -> None:
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    _seed_target_dir(tmp_path, "sync")

    result = skill_templates.compile_all(tmp_path, validate=False, what_if=True)

    assert result.exit_code == 0
    assert result.written == []
    assert not _target(tmp_path, "sync").exists()


def test_compile_all_worst_exit_code_wins_across_templates(tmp_path: Path) -> None:
    """Edge: one clean template and one grammar-broken template in one run."""
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "clean", "{{> greet}}\n")
    _seed_target_dir(tmp_path, "clean")
    _write_template(tmp_path, "broken", "{{var}}\n")
    _seed_target_dir(tmp_path, "broken")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert str(_target(tmp_path, "clean")) in result.written


# generate_skills.generate_skills() wiring --------------------------------------


def _minimal_platform_config(tmp_path: Path) -> Path:
    config = tmp_path / "platform.yaml"
    config.write_text(
        'schemaVersion: "1.0"\n'
        "provider: copilot-cli\n"
        "artifacts:\n"
        "  skills:\n"
        "    mode: directory-copy\n"
        "    sourceDir: .claude/skills\n"
        "    outputDir: out/skills\n",
        encoding="utf-8",
    )
    return config


def test_generate_skills_runs_compile_before_copy_and_writes_rendered_target(
    tmp_path: Path,
) -> None:
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "# sync\n{{> greet}}\n")
    skill_dir = tmp_path / ".claude" / "skills" / "sync"
    skill_dir.mkdir(parents=True)
    config = _minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 0
    target = _target(tmp_path, "sync")
    assert target.read_text(encoding="utf-8") == "# sync\nhi\n"
    # Copy loop still ran: the rendered file reached the mirror output too.
    assert (tmp_path / "out" / "skills" / "sync" / "SKILL.md").is_file()


def test_generate_skills_nonzero_compile_returns_before_copy(tmp_path: Path) -> None:
    _write_template(tmp_path, "sync", "{{var}}\n")
    skill_dir = tmp_path / ".claude" / "skills" / "sync"
    skill_dir.mkdir(parents=True)
    skill_dir_md = skill_dir / "SKILL.md"
    skill_dir_md.write_text("# sync\n", encoding="utf-8")
    config = _minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 2
    assert not (tmp_path / "out" / "skills" / "sync").exists()


def test_generate_skills_validate_true_compares_without_writing_then_still_copies(
    tmp_path: Path,
) -> None:
    """build_all.py --check shape: validate=True must not write .claude/,
    but the copy loop still runs when the compile is clean.
    """
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("hi\n", encoding="utf-8")
    config = _minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path, validate=True)

    assert rc == 0
    assert (tmp_path / "out" / "skills" / "sync" / "SKILL.md").is_file()


def test_generate_skills_validate_true_with_drift_returns_one_and_skips_copy(
    tmp_path: Path,
) -> None:
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("hand edited\n", encoding="utf-8")
    config = _minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path, validate=True)

    assert rc == 1
    assert target.read_text(encoding="utf-8") == "hand edited\n"
    assert not (tmp_path / "out" / "skills" / "sync").exists()


# CLI subprocess (DESIGN-020 case 9) ---------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_GENERATE_SKILLS_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_validate_exit_0_on_clean_tree(tmp_path: Path) -> None:
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("hi\n", encoding="utf-8")

    result = _run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 0, result.stderr


def test_cli_validate_exit_1_on_drift(tmp_path: Path) -> None:
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("hand edited\n", encoding="utf-8")

    result = _run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 1
    assert "DRIFTED" in result.stdout
    assert target.read_text(encoding="utf-8") == "hand edited\n"


def test_cli_validate_exit_2_on_disallowed_tag(tmp_path: Path) -> None:
    _write_template(tmp_path, "sync", "{{var}}\n")
    _seed_target_dir(tmp_path, "sync")

    result = _run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 2
    assert "{{var}}" in result.stderr


def test_cli_validate_needs_no_platform_config(tmp_path: Path) -> None:
    """--validate never resolves a platform config (main()'s own contract)."""
    result = _run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 0
