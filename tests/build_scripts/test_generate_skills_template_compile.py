"""Tests for build/scripts/skill_templates.py and its generate_skills.py wiring.

Covers the nine cases in DESIGN-020's Tests table
(``.agents/specs/design/DESIGN-020-skill-guidance-excerpt-sync.md``, "Tests")
for the ADR-108 compile module, plus positive/negative/edge unit coverage on
each exported function per ``.agents/governance/TESTING-RIGOR.md``, plus a
tenth case (ADR review round for #5706, before merge): a NO-REGEN-protected
target must be skipped, not counted as drift, in validate mode too, for both
sentinel forms ``regen_guard.detect_reason`` recognizes.
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

    found = skill_templates.discover(tmp_path)

    assert set(found) == {"sync", "test"}
    assert found["sync"] == tmp_path / "templates" / "skills" / "sync.SKILL.md.tmpl"


def test_discover_ignores_files_without_the_exact_suffix(tmp_path: Path) -> None:
    templates_dir = tmp_path / "templates" / "skills"
    templates_dir.mkdir(parents=True)
    (templates_dir / "README.md").write_text("not a template\n")
    (templates_dir / "sync.SKILL.md").write_text("missing .tmpl suffix\n")

    assert skill_templates.discover(tmp_path) == {}


# owned_targets() ---------------------------------------------------------------


def test_owned_targets_empty_when_no_templates(tmp_path: Path) -> None:
    assert skill_templates.owned_targets(tmp_path) == set()


def test_owned_targets_maps_each_template_to_its_claude_skills_path(tmp_path: Path) -> None:
    _write_template(tmp_path, "sync", "body\n")

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


def test_render_missing_partial_raises_with_slug_and_path(tmp_path: Path) -> None:
    """Config error (DESIGN-020 case 2): exit 2, slug and path printed."""
    tmpl = _write_template(tmp_path, "sync", "{{> nope}}\n")
    partials_dir = tmp_path / "templates" / "skills" / "partials"
    partials_dir.mkdir(parents=True)

    with pytest.raises(skill_templates.MissingPartialError) as excinfo:
        skill_templates.render(tmpl, partials_dir)

    assert "nope" in str(excinfo.value)
    assert str(tmpl) in str(excinfo.value)


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


def test_compile_all_skips_no_regen_target_with_warn(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Edge (DESIGN-020 case 6): NO-REGEN sentinel -> skipped, exit 0.

    WARN, not NOTICE: the sentinel exempts a template-owned file from this
    class's only gate (ADR-108 section 4), so the skip is louder than the
    NOTICE ``generate_skills._copy_skill_tree`` prints for an ordinary
    non-generated skill file.
    """
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    target.write_text("<!-- NO-REGEN: manual edit -->\nhand edited\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 0
    assert str(target) in result.skipped
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "template-owned file exempt from drift gate" in out
    assert target.read_text(encoding="utf-8") == "<!-- NO-REGEN: manual edit -->\nhand edited\n"


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


def _apply_html_comment_sentinel(target: Path) -> None:
    target.write_text("<!-- NO-REGEN: manual edit -->\nhand edited\n", encoding="utf-8")


def _apply_sidecar_sentinel(target: Path) -> None:
    target.write_text("hand edited\n", encoding="utf-8")
    target.with_suffix(target.suffix + ".noregen").write_text("", encoding="utf-8")


@pytest.mark.parametrize(
    "apply_sentinel",
    [_apply_html_comment_sentinel, _apply_sidecar_sentinel],
    ids=["html-comment", "sidecar"],
)
def test_compile_all_validate_skips_no_regen_target_not_counted_as_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    apply_sentinel: Callable[[Path], None],
) -> None:
    """Validate mode honors NO-REGEN too: skipped with the same WARN as the
    write path, and NOT reported as drift (exit stays 0 for that file).

    Covers both sentinel forms regen_guard.detect_reason recognizes: an
    in-file ``<!-- NO-REGEN`` HTML comment, and a ``.noregen`` sidecar file.

    The sentinel is the author's declared intent to diverge from the
    template; validate mode's job is to catch an UNDECLARED divergence, so
    treating a NO-REGEN target as drift would flag exactly the case the
    sentinel exists to silence.
    """
    _write_partial(tmp_path, "greet", "hi\n")
    _write_template(tmp_path, "sync", "{{> greet}}\n")
    target = _seed_target_dir(tmp_path, "sync")
    apply_sentinel(target)
    original = target.read_text(encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=True)

    assert result.exit_code == 0
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
