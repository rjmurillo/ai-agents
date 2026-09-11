"""Tests for build/scripts/skill_templates.py and its generate_skills.py wiring.

Covers ``discover``, ``discover_errors``, ``owned_targets``, ``compile_all``,
the ``generate_skills.py`` wiring, and the CLI: DESIGN-020's Tests table
(``.agents/specs/design/DESIGN-020-skill-guidance-excerpt-sync.md``), plus
NO-REGEN-fails-closed and partial-trailing-newline cases from later ADR
review rounds for #5706 (see ``compile_all``'s own docstring). Grammar,
partial-tree validation, and ``render`` are in the sibling
``test_skill_template_grammar.py`` (taste-lint file-size ceiling); every
case is kept. Fixture helpers live in ``_skill_template_helpers.py``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import generate_skills  # noqa: E402
import skill_templates  # noqa: E402
from _skill_template_helpers import (  # noqa: E402
    NO_REGEN_SENTINEL_APPLIERS,
    NO_REGEN_SENTINEL_IDS,
    minimal_platform_config,
    run_cli,
    seed_target_dir,
    target,
    write_partial,
    write_template,
)

_NO_REGEN_SENTINEL_FORMS = pytest.mark.parametrize(
    "apply_sentinel", NO_REGEN_SENTINEL_APPLIERS, ids=NO_REGEN_SENTINEL_IDS
)


def test_discover_returns_empty_mapping_when_templates_dir_absent(tmp_path: Path) -> None:
    assert skill_templates.discover(tmp_path) == {}


def test_discover_finds_templates_by_stripped_filename(tmp_path: Path) -> None:
    write_template(tmp_path, "sync", "body\n")
    write_template(tmp_path, "test", "body\n")
    seed_target_dir(tmp_path, "sync")
    seed_target_dir(tmp_path, "test")

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
    """A name outside ``^[a-z0-9]+(-[a-z0-9]+)*$`` never reaches discover()'s mapping."""
    write_template(tmp_path, "Bad_Name", "body\n")
    (tmp_path / ".claude" / "skills" / "Bad_Name").mkdir(parents=True)

    assert skill_templates.discover(tmp_path) == {}


def test_discover_excludes_a_name_with_no_skill_directory(tmp_path: Path) -> None:
    """A valid name with no existing skill dir never reaches discover()'s
    mapping: every template-owned skill converts an EXISTING skill.
    """
    write_template(tmp_path, "sync", "body\n")
    # No .claude/skills/sync/ directory created at all.

    assert skill_templates.discover(tmp_path) == {}


def test_discover_excludes_a_symlinked_skill_directory_outside_the_root(
    tmp_path: Path,
) -> None:
    """CWE-22 defense: a symlinked skill dir outside .claude/skills/ is exit
    2, never template-owned. Skipped where symlinks are unsupported.
    """
    write_template(tmp_path, "sync", "body\n")
    outside = tmp_path / "outside-the-skills-root"
    outside.mkdir()
    skills_root = tmp_path / ".claude" / "skills"
    skills_root.mkdir(parents=True)
    link = skills_root / "sync"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create a symlink on this platform/permission set")

    assert skill_templates.discover(tmp_path) == {}
    errors = skill_templates.discover_errors(tmp_path)
    assert len(errors) == 1
    assert "sync" in errors[0]
    assert "symlink" in errors[0].lower()
    assert skill_templates.owned_targets(tmp_path) == set()


def test_discover_errors_reports_the_bad_name_with_template_path(tmp_path: Path) -> None:
    tmpl = write_template(tmp_path, "Bad_Name", "body\n")
    (tmp_path / ".claude" / "skills" / "Bad_Name").mkdir(parents=True)

    errors = skill_templates.discover_errors(tmp_path)

    assert len(errors) == 1
    assert str(tmpl) in errors[0]
    assert "Bad_Name" in errors[0]


def test_discover_errors_reports_the_missing_skill_directory_with_template_path(
    tmp_path: Path,
) -> None:
    tmpl = write_template(tmp_path, "sync", "body\n")

    errors = skill_templates.discover_errors(tmp_path)

    assert len(errors) == 1
    assert str(tmpl) in errors[0]
    assert ".claude/skills/sync" in errors[0]


def test_discover_errors_empty_on_a_clean_tree(tmp_path: Path) -> None:
    write_template(tmp_path, "sync", "body\n")
    seed_target_dir(tmp_path, "sync")

    assert skill_templates.discover_errors(tmp_path) == []


def test_compile_all_reports_a_bad_name_as_exit_2_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tmpl = write_template(tmp_path, "Bad_Name", "body\n")
    (tmp_path / ".claude" / "skills" / "Bad_Name").mkdir(parents=True)

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert result.written == []
    assert str(tmpl) in capsys.readouterr().err


def test_compile_all_reports_a_missing_skill_directory_as_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tmpl = write_template(tmp_path, "sync", "body\n")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert result.written == []
    assert str(tmpl) in capsys.readouterr().err


def test_owned_targets_excludes_an_invalid_name(tmp_path: Path) -> None:
    write_template(tmp_path, "Bad_Name", "body\n")
    (tmp_path / ".claude" / "skills" / "Bad_Name").mkdir(parents=True)

    assert skill_templates.owned_targets(tmp_path) == set()


def test_owned_targets_empty_when_no_templates(tmp_path: Path) -> None:
    assert skill_templates.owned_targets(tmp_path) == set()


def test_owned_targets_maps_each_template_to_its_claude_skills_path(tmp_path: Path) -> None:
    write_template(tmp_path, "sync", "body\n")
    seed_target_dir(tmp_path, "sync")

    assert skill_templates.owned_targets(tmp_path) == {
        tmp_path / ".claude" / "skills" / "sync" / "SKILL.md"
    }


def test_compile_all_writes_rendered_bytes_when_target_missing(tmp_path: Path) -> None:
    """Positive (DESIGN-020 case 1, end to end): exit 0, file written. The
    skill directory already exists but carries no ``SKILL.md`` yet.
    """
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "# sync\n{{> greet}}\ndone\n")
    seed_target_dir(tmp_path, "sync")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 0
    dst = target(tmp_path, "sync")
    assert str(dst) in result.written
    assert dst.read_text(encoding="utf-8") == "# sync\nhi\ndone\n"


def test_compile_all_missing_partial_leaves_target_untouched(tmp_path: Path) -> None:
    write_template(tmp_path, "sync", "{{> nope}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("original\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert dst.read_text(encoding="utf-8") == "original\n"


def test_compile_all_partial_missing_trailing_newline_leaves_target_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Eleventh case: a partial missing its trailing newline is exit 2,
    reported with the partial path, target untouched.
    """
    partial_path = write_partial(tmp_path, "no-newline", "no trailing newline")
    write_template(tmp_path, "sync", "{{> no-newline}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("original\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert dst.read_text(encoding="utf-8") == "original\n"
    assert result.written == []
    assert str(partial_path) in capsys.readouterr().err


def test_compile_all_disallowed_tag_leaves_target_untouched(tmp_path: Path) -> None:
    write_template(tmp_path, "sync", "{{var}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("original\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert dst.read_text(encoding="utf-8") == "original\n"


def test_compile_all_skips_skill_with_no_template(tmp_path: Path) -> None:
    """Edge (case 5): a hand-maintained skill with no template is untouched."""
    other_target = seed_target_dir(tmp_path, "other")
    other_target.write_text("hand maintained\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 0
    assert result.written == []
    assert other_target.read_text(encoding="utf-8") == "hand maintained\n"


@_NO_REGEN_SENTINEL_FORMS
def test_compile_all_skips_no_regen_target_with_warn_and_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    apply_sentinel: Callable[[Path], None],
) -> None:
    """Edge (DESIGN-020 case 6, diverged): NO-REGEN sentinel -> unchanged,
    WARN (not NOTICE), exit 1 (not DESIGN-020's exit 0; see compile_all's
    "Stricter/looser/different than canonical" section). All three sentinel
    forms (MINOR 1, ADR review).
    """
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    apply_sentinel(dst)
    original = dst.read_text(encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 1
    assert str(dst) in result.skipped
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "template-owned file exempt from drift gate" in out
    assert dst.read_text(encoding="utf-8") == original


def test_compile_all_validate_mode_never_writes_on_missing_target(tmp_path: Path) -> None:
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    seed_target_dir(tmp_path, "sync")

    result = skill_templates.compile_all(tmp_path, validate=True)

    assert result.exit_code == 1
    assert not target(tmp_path, "sync").exists()


def test_compile_all_validate_on_hand_edited_target(tmp_path: Path) -> None:
    """Negative (case 7): --validate on a hand-edited target: exit 1, target untouched."""
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("hand edited, not the template render\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=True)

    assert result.exit_code == 1
    assert str(dst) in result.drifted
    assert dst.read_text(encoding="utf-8") == "hand edited, not the template render\n"


@_NO_REGEN_SENTINEL_FORMS
def test_compile_all_validate_skips_no_regen_target_not_counted_as_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    apply_sentinel: Callable[[Path], None],
) -> None:
    """Tenth case: validate mode honors NO-REGEN too -- WARN, unchanged, NOT
    drift (a declared divergence), still exit 1 (fails closed). All three
    sentinel forms (MINOR 1, ADR review).
    """
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    apply_sentinel(dst)
    original = dst.read_text(encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=True)

    assert result.exit_code == 1
    assert result.drifted == []
    assert str(dst) in result.skipped
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "template-owned file exempt from drift gate" in out
    assert dst.read_text(encoding="utf-8") == original


def test_compile_all_validate_on_clean_tree(tmp_path: Path) -> None:
    """Positive (DESIGN-020 case 8): --validate on a clean tree -> exit 0."""
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("hi\n", encoding="utf-8")

    result = skill_templates.compile_all(tmp_path, validate=True)

    assert result.exit_code == 0
    assert result.drifted == []
    assert result.written == []


def test_compile_all_missing_target_directory_is_a_config_error(tmp_path: Path) -> None:
    """No skill dir at all: caught by discover_errors(), not the removed,
    now-unreachable per-template target.parent.is_dir() check.
    """
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    # No .claude/skills/sync/ directory created at all.

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert not target(tmp_path, "sync").exists()


def test_compile_all_what_if_reports_without_writing(tmp_path: Path) -> None:
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    seed_target_dir(tmp_path, "sync")

    result = skill_templates.compile_all(tmp_path, validate=False, what_if=True)

    assert result.exit_code == 0
    assert result.written == []
    assert not target(tmp_path, "sync").exists()


def test_compile_all_worst_exit_code_wins_across_templates(tmp_path: Path) -> None:
    """Edge: one clean template and one grammar-broken template in one run."""
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "clean", "{{> greet}}\n")
    seed_target_dir(tmp_path, "clean")
    write_template(tmp_path, "broken", "{{var}}\n")
    seed_target_dir(tmp_path, "broken")

    result = skill_templates.compile_all(tmp_path, validate=False)

    assert result.exit_code == 2
    assert str(target(tmp_path, "clean")) in result.written


def test_generate_skills_runs_compile_before_copy_and_writes_rendered_target(
    tmp_path: Path,
) -> None:
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "# sync\n{{> greet}}\n")
    skill_dir = tmp_path / ".claude" / "skills" / "sync"
    skill_dir.mkdir(parents=True)
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 0
    dst = target(tmp_path, "sync")
    assert dst.read_text(encoding="utf-8") == "# sync\nhi\n"
    # Copy loop still ran: the rendered file reached the mirror output too.
    assert (tmp_path / "out" / "skills" / "sync" / "SKILL.md").is_file()


def test_generate_skills_nonzero_compile_returns_before_copy(tmp_path: Path) -> None:
    write_template(tmp_path, "sync", "{{var}}\n")
    skill_dir = tmp_path / ".claude" / "skills" / "sync"
    skill_dir.mkdir(parents=True)
    skill_dir_md = skill_dir / "SKILL.md"
    skill_dir_md.write_text("# sync\n", encoding="utf-8")
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 2
    assert not (tmp_path / "out" / "skills" / "sync").exists()


def test_generate_skills_validate_true_compares_without_writing_then_still_copies(
    tmp_path: Path,
) -> None:
    """build_all.py --check shape: validate=True skips the write but still copies."""
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("hi\n", encoding="utf-8")
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path, validate=True)

    assert rc == 0
    assert (tmp_path / "out" / "skills" / "sync" / "SKILL.md").is_file()


def test_generate_skills_validate_true_with_drift_returns_one_and_skips_copy(
    tmp_path: Path,
) -> None:
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("hand edited\n", encoding="utf-8")
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path, validate=True)

    assert rc == 1
    assert dst.read_text(encoding="utf-8") == "hand edited\n"
    assert not (tmp_path / "out" / "skills" / "sync").exists()


def test_cli_validate_exit_0_on_clean_tree(tmp_path: Path) -> None:
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("hi\n", encoding="utf-8")

    result = run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 0, result.stderr


def test_cli_validate_exit_1_on_drift(tmp_path: Path) -> None:
    write_partial(tmp_path, "greet", "hi\n")
    write_template(tmp_path, "sync", "{{> greet}}\n")
    dst = seed_target_dir(tmp_path, "sync")
    dst.write_text("hand edited\n", encoding="utf-8")

    result = run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 1
    assert "DRIFTED" in result.stdout
    assert dst.read_text(encoding="utf-8") == "hand edited\n"


def test_cli_validate_exit_2_on_disallowed_tag(tmp_path: Path) -> None:
    write_template(tmp_path, "sync", "{{var}}\n")
    seed_target_dir(tmp_path, "sync")

    result = run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 2
    assert "{{var}}" in result.stderr


def test_cli_validate_needs_no_platform_config(tmp_path: Path) -> None:
    """--validate never resolves a platform config (main()'s own contract)."""
    result = run_cli("--repo-root", str(tmp_path), "--validate")

    assert result.returncode == 0
