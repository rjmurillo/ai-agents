"""Tests for the command references/ mirror in build/scripts/generate_commands.py.

Split from test_generate_commands.py to keep both files under the 500-line
taste ceiling. The bridge's own behavior (frontmatter merge, collisions,
excludes, committed-mirror drift) stays there; this file covers only the
progressive-disclosure tree a command may carry alongside its body.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_commands  # noqa: E402


def _write_command(commands_dir: Path, name: str, *, body: str = "Body line.\n") -> Path:
    commands_dir.mkdir(parents=True, exist_ok=True)
    path = commands_dir / f"{name}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _write_config_with_references(
    tmp_path: Path, *, references_output_dir: str | None = "out_commands"
) -> Path:
    """Platform config for the references mirror; omit the key to test the guard."""
    refs_line = (
        f'    referencesOutputDir: "{references_output_dir}"\n'
        if references_output_dir is not None
        else ""
    )
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        "schemaVersion: \"1.0\"\n"
        "provider: \"test\"\n"
        "artifacts:\n"
        "  commands:\n"
        '    sourceDir: "cmds"\n'
        '    outputDir: "out_skills"\n'
        f"{refs_line}"
        '    transform: "command-to-skill"\n'
        "    appendFrontmatter:\n"
        "      user-invocable: true\n",
        encoding="utf-8",
    )
    return cfg


def _write_reference(tmp_path: Path, command: str, relative: str, body: str) -> Path:
    path = tmp_path / "cmds" / command / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_command_references_mirror_at_the_same_plugin_relative_path(
    tmp_path: Path,
) -> None:
    """`<name>/references/**` must land at `<name>/references/**` in the mirror.

    The path has to match on both sides or the single portable spelling
    `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/commands/<name>/
    references/<file>` resolves in one tree and 404s in the other.
    """
    _write_command(tmp_path / "cmds", "spec", body="See references/deep.md\n")
    _write_reference(tmp_path, "spec", "references/deep.md", "# Deep\n\nDetail.\n")
    _write_reference(tmp_path, "spec", "references/nested/more.md", "# More\n")
    cfg = _write_config_with_references(tmp_path)

    assert generate_commands.generate_commands(cfg, tmp_path) == 0

    mirrored = tmp_path / "out_commands" / "spec" / "references"
    assert mirrored.joinpath("deep.md").read_text(encoding="utf-8") == "# Deep\n\nDetail.\n"
    assert mirrored.joinpath("nested", "more.md").read_text(encoding="utf-8") == "# More\n"
    # The command itself still bridges; references are additive.
    assert (tmp_path / "out_skills" / "spec" / "SKILL.md").is_file()


def test_command_references_copy_bytes_verbatim(tmp_path: Path) -> None:
    """Reference bodies are read on demand, so no Copilot body translation runs."""
    _write_command(tmp_path / "cmds", "spec", body="body\n")
    source = _write_reference(
        tmp_path, "spec", "references/deep.md", "Use $ARGUMENTS and @AGENTS.md\n"
    )
    cfg = _write_config_with_references(tmp_path)

    assert generate_commands.generate_commands(cfg, tmp_path) == 0

    copied = tmp_path / "out_commands" / "spec" / "references" / "deep.md"
    assert copied.read_bytes() == source.read_bytes()


def test_references_without_output_dir_configured_returns_2(tmp_path: Path) -> None:
    """Dropping authored depth silently is the failure this guard exists to stop."""
    _write_command(tmp_path / "cmds", "spec", body="body\n")
    _write_reference(tmp_path, "spec", "references/deep.md", "detail\n")
    cfg = _write_config_with_references(tmp_path, references_output_dir=None)

    assert generate_commands.generate_commands(cfg, tmp_path) == 2
    # Nothing is written when the config cannot express where references go.
    assert not (tmp_path / "out_skills").exists()


def test_absent_references_tree_needs_no_output_dir(tmp_path: Path) -> None:
    """The guard fires on content, not on configuration shape."""
    _write_command(tmp_path / "cmds", "spec", body="body\n")
    cfg = _write_config_with_references(tmp_path, references_output_dir=None)

    assert generate_commands.generate_commands(cfg, tmp_path) == 0


def test_references_under_unbridged_subcommand_are_not_mirrored(
    tmp_path: Path,
) -> None:
    """`pr-quality/` gets no bridged skill, so a references mirror would orphan."""
    _write_command(tmp_path / "cmds", "alpha", body="alpha\n")
    _write_reference(tmp_path, "pr-quality", "references/deep.md", "detail\n")
    (tmp_path / "cmds" / "pr-quality" / "all.md").write_text("sub\n", encoding="utf-8")
    cfg = _write_config_with_references(tmp_path)

    assert generate_commands.generate_commands(cfg, tmp_path) == 0
    assert not (tmp_path / "out_commands" / "pr-quality").exists()


def test_references_for_a_collided_command_are_not_mirrored(tmp_path: Path) -> None:
    """A collision writes no SKILL.md, so its references have nothing to serve."""
    _write_command(tmp_path / "cmds", "memory-documentary", body="cmd body\n")
    _write_reference(tmp_path, "memory-documentary", "references/deep.md", "detail\n")
    skill_dir = tmp_path / ".claude" / "skills" / "memory-documentary"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("authored skill content\n", encoding="utf-8")
    cfg = _write_config_with_references(tmp_path)

    assert generate_commands.generate_commands(cfg, tmp_path) == 1
    assert not (tmp_path / "out_commands" / "memory-documentary").exists()


def test_command_references_skip_python_cache_artifacts(tmp_path: Path) -> None:
    """Build-time noise must not ship in a customer-facing plugin install."""
    _write_command(tmp_path / "cmds", "spec", body="body\n")
    _write_reference(tmp_path, "spec", "references/deep.md", "detail\n")
    _write_reference(tmp_path, "spec", "references/__pycache__/x.cpython-314.pyc", "x")
    _write_reference(tmp_path, "spec", "references/helper.pyc", "x")
    cfg = _write_config_with_references(tmp_path)

    assert generate_commands.generate_commands(cfg, tmp_path) == 0

    mirrored = tmp_path / "out_commands" / "spec" / "references"
    assert mirrored.joinpath("deep.md").is_file()
    assert not mirrored.joinpath("__pycache__").exists()
    assert not mirrored.joinpath("helper.pyc").exists()


def test_cache_only_references_tree_does_not_trip_the_config_guard(
    tmp_path: Path,
) -> None:
    """A tree holding only cache artifacts carries no authored depth to lose."""
    _write_command(tmp_path / "cmds", "spec", body="body\n")
    _write_reference(tmp_path, "spec", "references/__pycache__/x.pyc", "x")
    cfg = _write_config_with_references(tmp_path, references_output_dir=None)

    assert generate_commands.generate_commands(cfg, tmp_path) == 0


def test_command_reference_honors_no_regen_sidecar(tmp_path: Path) -> None:
    _write_command(tmp_path / "cmds", "spec", body="body\n")
    _write_reference(tmp_path, "spec", "references/deep.md", "regenerated\n")
    target = tmp_path / "out_commands" / "spec" / "references" / "deep.md"
    target.parent.mkdir(parents=True)
    target.write_text("hand-edited; do not overwrite\n", encoding="utf-8")
    (target.parent / "deep.md.noregen").write_text("", encoding="utf-8")
    cfg = _write_config_with_references(tmp_path)

    assert generate_commands.generate_commands(cfg, tmp_path) == 0
    assert target.read_text(encoding="utf-8") == "hand-edited; do not overwrite\n"


def test_what_if_does_not_write_references(tmp_path: Path) -> None:
    _write_command(tmp_path / "cmds", "spec", body="body\n")
    _write_reference(tmp_path, "spec", "references/deep.md", "detail\n")
    cfg = _write_config_with_references(tmp_path)

    assert generate_commands.generate_commands(cfg, tmp_path, what_if=True) == 0
    assert not (tmp_path / "out_commands").exists()


def test_absolute_references_output_dir_rejected(tmp_path: Path) -> None:
    _write_command(tmp_path / "cmds", "spec", body="body\n")
    cfg = _write_config_with_references(tmp_path, references_output_dir="/etc")

    assert generate_commands.generate_commands(cfg, tmp_path) == 2
