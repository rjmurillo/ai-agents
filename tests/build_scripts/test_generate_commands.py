"""Tests for build/scripts/generate_commands.py (REQ-003-001, M4-T1)."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_commands  # noqa: E402

# Helpers --------------------------------------------------------------------


def _write_command(
    commands_dir: Path, name: str, *, frontmatter: str | None = None, body: str = "Body line.\n"
) -> Path:
    commands_dir.mkdir(parents=True, exist_ok=True)
    path = commands_dir / f"{name}.md"
    if frontmatter is not None:
        content = f"---\n{frontmatter}---\n{body}"
    else:
        content = body
    path.write_text(content, encoding="utf-8")
    return path


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  commands:
    sourceDir: "cmds"
    outputDir: "out_skills"
    transform: "command-to-skill"
    appendFrontmatter:
      user-invocable: true
"""
    )
    return cfg


def _read_output(tmp_path: Path, name: str) -> str:
    return (tmp_path / "out_skills" / name / "SKILL.md").read_text(encoding="utf-8")


# Happy path -----------------------------------------------------------------


def test_command_with_frontmatter_emits_user_invocable(tmp_path: Path) -> None:
    """A command's frontmatter should be merged with user-invocable: true."""
    _write_command(
        tmp_path / "cmds",
        "spec",
        frontmatter='description: "Define what to build."\n',
        body="# Spec\n\nBody content.\n",
    )
    cfg = _write_config(tmp_path)

    rc = generate_commands.generate_commands(cfg, tmp_path)
    assert rc == 0

    out = _read_output(tmp_path, "spec")
    # parse_simple_frontmatter strips quotes; format_frontmatter_yaml emits
    # the bare value, so the round-trip lands as `description: <text>`.
    assert "user-invocable: true" in out
    assert "description: Define what to build." in out
    assert "name: spec" in out
    assert "Body content." in out
    # Closing fence must sit on its own line; format_frontmatter_yaml does
    # not append the trailing newline so the generator must insert one.
    assert "true---" not in out
    assert "\n---\n" in out


def test_command_without_frontmatter_backfills_description(tmp_path: Path) -> None:
    """A command lacking frontmatter gets name + description backfilled from body."""
    _write_command(
        tmp_path / "cmds",
        "build",
        frontmatter=None,
        body="# Build\n\nBuild incrementally with TDD.\n",
    )
    cfg = _write_config(tmp_path)

    rc = generate_commands.generate_commands(cfg, tmp_path)
    assert rc == 0

    out = _read_output(tmp_path, "build")
    assert "name: build" in out
    assert "description: Build incrementally with TDD." in out
    assert "user-invocable: true" in out


def test_command_argument_hint_inline_array_emits_scalar_string(tmp_path: Path) -> None:
    _write_command(
        tmp_path / "cmds",
        "ship",
        frontmatter=(
            'description: "Ship changes."\n'
            "argument-hint: [target-branch]\n"
        ),
        body="# Ship\n\nShip changes.\n",
    )
    cfg = _write_config(tmp_path)

    rc = generate_commands.generate_commands(cfg, tmp_path)
    assert rc == 0

    out = _read_output(tmp_path, "ship")
    assert "argument-hint: '[target-branch]'" in out
    assert "argument-hint:\n  - target-branch" not in out


def test_claude_md_excluded(tmp_path: Path) -> None:
    """CLAUDE.md is a passive context import, not a slash command — must be skipped."""
    _write_command(tmp_path / "cmds", "real", body="real cmd\n")
    (tmp_path / "cmds" / "CLAUDE.md").write_text("# noop\n")
    cfg = _write_config(tmp_path)

    assert generate_commands.generate_commands(cfg, tmp_path) == 0
    assert (tmp_path / "out_skills" / "real" / "SKILL.md").is_file()
    assert not (tmp_path / "out_skills" / "CLAUDE" / "SKILL.md").exists()


def test_subdirectories_skipped(tmp_path: Path) -> None:
    """Sub-command directories (pr-quality/) are out of scope."""
    _write_command(tmp_path / "cmds", "alpha", body="alpha\n")
    sub = tmp_path / "cmds" / "subdir"
    sub.mkdir()
    (sub / "nested.md").write_text("nested\n")
    cfg = _write_config(tmp_path)

    assert generate_commands.generate_commands(cfg, tmp_path) == 0
    assert (tmp_path / "out_skills" / "alpha" / "SKILL.md").is_file()
    assert not (tmp_path / "out_skills" / "nested" / "SKILL.md").exists()


def test_command_resources_copy_to_configured_output_dir(tmp_path: Path) -> None:
    """A command resource needed at runtime should ship with the plugin."""
    _write_command(tmp_path / "cmds", "pr-review", body="Review PRs.\n")
    resource = tmp_path / "cmds" / "pr-review-config.yaml"
    resource.write_text("completion_criteria: []\n", encoding="utf-8")
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  commands:
    sourceDir: "cmds"
    outputDir: "out_skills"
    resourceOutputDir: "out_commands"
    resourceSuffixes: [".yaml"]
    transform: "command-to-skill"
    appendFrontmatter:
      user-invocable: true
""",
        encoding="utf-8",
    )

    rc = generate_commands.generate_commands(cfg, tmp_path)

    assert rc == 0
    copied = tmp_path / "out_commands" / "pr-review-config.yaml"
    assert copied.read_text(encoding="utf-8") == "completion_criteria: []\n"


def test_committed_pr_review_config_mirror_matches_claude_config() -> None:
    source = REPO_ROOT / ".claude" / "commands" / "pr-review-config.yaml"
    mirror = REPO_ROOT / "src" / "copilot-cli" / "commands" / "pr-review-config.yaml"

    assert mirror.is_file()
    assert mirror.read_bytes() == source.read_bytes()


# Collision detection --------------------------------------------------------


def test_collision_with_authored_skill_returns_1(tmp_path: Path) -> None:
    """An existing .claude/skills/<name>/SKILL.md must abort the bridge."""
    _write_command(tmp_path / "cmds", "memory-documentary", body="cmd body\n")
    skill_dir = tmp_path / ".claude" / "skills" / "memory-documentary"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("authored skill content\n")
    cfg = _write_config(tmp_path)

    rc = generate_commands.generate_commands(cfg, tmp_path)
    assert rc == 1
    # Output must NOT have been written for the colliding name.
    assert not (tmp_path / "out_skills" / "memory-documentary" / "SKILL.md").exists()


# Configuration errors -------------------------------------------------------


def test_missing_artifacts_commands_returns_2(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text('schemaVersion: "1.0"\nprovider: "x"\n')
    assert generate_commands.generate_commands(cfg, tmp_path) == 2


def test_unsupported_transform_returns_2(tmp_path: Path) -> None:
    _write_command(tmp_path / "cmds", "alpha", body="alpha\n")
    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "x"
artifacts:
  commands:
    sourceDir: "cmds"
    outputDir: "out_skills"
    transform: "magic-mode"
"""
    )
    assert generate_commands.generate_commands(cfg, tmp_path) == 2


def test_no_commands_found_returns_1(tmp_path: Path) -> None:
    (tmp_path / "cmds").mkdir()
    cfg = _write_config(tmp_path)
    assert generate_commands.generate_commands(cfg, tmp_path) == 1


def test_absolute_source_dir_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "x"
artifacts:
  commands:
    sourceDir: "/etc/passwd"
    outputDir: "out_skills"
    transform: "command-to-skill"
"""
    )
    assert generate_commands.generate_commands(cfg, tmp_path) == 2


def test_resource_output_dir_requires_resource_suffixes(tmp_path: Path) -> None:
    _write_command(tmp_path / "cmds", "alpha", body="alpha\n")
    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "x"
artifacts:
  commands:
    sourceDir: "cmds"
    outputDir: "out_skills"
    resourceOutputDir: "out_commands"
    transform: "command-to-skill"
"""
    )
    assert generate_commands.generate_commands(cfg, tmp_path) == 2


def test_resource_suffixes_must_be_non_empty_dotted_list(tmp_path: Path) -> None:
    _write_command(tmp_path / "cmds", "alpha", body="alpha\n")
    cases = ("[]", '["yaml"]', '["."]')
    for index, suffixes in enumerate(cases, start=1):
        cfg = tmp_path / f"p-{index}.yaml"
        cfg.write_text(
            f"""\
schemaVersion: "1.0"
provider: "x"
artifacts:
  commands:
    sourceDir: "cmds"
    outputDir: "out_skills"
    resourceOutputDir: "out_commands"
    resourceSuffixes: {suffixes}
    transform: "command-to-skill"
"""
        )
        assert generate_commands.generate_commands(cfg, tmp_path) == 2


# NO-REGEN sentinel ----------------------------------------------------------


def test_sidecar_protected_skill_not_overwritten(tmp_path: Path) -> None:
    _write_command(
        tmp_path / "cmds",
        "spec",
        frontmatter='description: "fresh"\n',
        body="generated body\n",
    )
    target_dir = tmp_path / "out_skills" / "spec"
    target_dir.mkdir(parents=True)
    target = target_dir / "SKILL.md"
    target.write_text("hand-edited; do not overwrite\n")
    (target.parent / "SKILL.md.noregen").write_text("")

    cfg = _write_config(tmp_path)
    assert generate_commands.generate_commands(cfg, tmp_path) == 0
    assert target.read_text() == "hand-edited; do not overwrite\n"


def test_what_if_does_not_write(tmp_path: Path) -> None:
    _write_command(tmp_path / "cmds", "spec", body="ok\n")
    cfg = _write_config(tmp_path)
    assert generate_commands.generate_commands(cfg, tmp_path, what_if=True) == 0
    assert not (tmp_path / "out_skills").exists()


# CLI entry point ------------------------------------------------------------


def test_main_invokes_generation(tmp_path: Path) -> None:
    _write_command(tmp_path / "cmds", "spec", body="ok\n")
    cfg = _write_config(tmp_path)
    rc = generate_commands.main([
        "--config", str(cfg), "--repo-root", str(tmp_path),
    ])
    assert rc == 0


def test_main_missing_config_returns_2(tmp_path: Path) -> None:
    rc = generate_commands.main([
        "--config", str(tmp_path / "nope.yaml"), "--repo-root", str(tmp_path),
    ])
    assert rc == 2


# Committed-mirror drift -----------------------------------------------------


def test_committed_command_mirrors_match_the_generator() -> None:
    """The shipped mirror must equal what this generator writes from the command.

    `_skip_skillforge_path` in scripts/validation/git_hook_policy.py exempts
    these mirrors from skill validation on the reasoning that they are derived
    from `.claude/commands/<name>.md` and so "cannot drift". Nothing
    regenerates them at commit time, so they can and did: an edit to
    `.claude/commands/pr-autofix.md` left the Copilot mirror prescribing a
    force push without `FORCE_PUSH_OK=1`, which the repository's own pre-push
    guard exits 1 on. Every Copilot CLI agent following the shipped skill hit
    that.
    """
    staged = Path(tempfile.mkdtemp())
    try:
        shutil.copytree(REPO_ROOT / ".claude" / "commands", staged / ".claude" / "commands")
        config = REPO_ROOT / "templates" / "platforms" / "copilot-cli.yaml"

        assert generate_commands.generate_commands(config, staged) == 0

        produced = sorted((staged / "src" / "copilot-cli" / "skills").glob("*/SKILL.md"))
        assert produced, "generator wrote no mirror; the comparison would be vacuous"
        committed_root = REPO_ROOT / "src" / "copilot-cli" / "skills"
        drifted = [
            path.parent.name
            for path in produced
            if not (committed_root / path.parent.name / "SKILL.md").is_file()
            or (committed_root / path.parent.name / "SKILL.md").read_text(encoding="utf-8")
            != path.read_text(encoding="utf-8")
        ]

        assert drifted == [], (
            f"{len(drifted)} of {len(produced)} command mirrors are stale: "
            f"{drifted}. Run uv run --frozen python build/scripts/generate_commands.py"
        )
    finally:
        shutil.rmtree(staged, ignore_errors=True)


# excludeFilenames / _DEFAULT_EXCLUDES union behaviour -----------------------


def _write_config_with_excludes(tmp_path: Path, exclude_filenames: list[str] | None) -> Path:
    """Write a minimal platform config, optionally setting ``excludeFilenames``."""
    exclude_block = ""
    if exclude_filenames is not None:
        items = ", ".join(f'"{f}"' for f in exclude_filenames)
        exclude_block = f"    excludeFilenames: [{items}]\n"
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        f"""\
schemaVersion: "1.0"
provider: "test"
artifacts:
  commands:
    sourceDir: "cmds"
    outputDir: "out_skills"
    transform: "command-to-skill"
{exclude_block}"""
    )
    return cfg


def test_exclude_filenames_unions_with_defaults(tmp_path: Path) -> None:
    """When ``excludeFilenames`` omits a default-excluded file, it is still excluded."""
    cmds = tmp_path / "cmds"
    # Create a file whose name matches a _DEFAULT_EXCLUDES entry ("CLAUDE.md")
    _write_command(cmds, "CLAUDE", body="Should be excluded.\n")
    # Create a normal command that should be generated
    _write_command(cmds, "hello", body="Hello world.\n")

    # Config excludes only "AGENTS.md" — deliberately omits "CLAUDE.md"
    cfg = _write_config_with_excludes(tmp_path, ["AGENTS.md"])

    rc = generate_commands.generate_commands(cfg, tmp_path)
    assert rc == 0

    out_dir = tmp_path / "out_skills"
    generated = sorted(p.parent.name for p in out_dir.glob("*/SKILL.md"))
    assert "CLAUDE" not in generated, "CLAUDE.md must be excluded via _DEFAULT_EXCLUDES union"
    assert "hello" in generated


def test_exclude_filenames_absent_uses_defaults(tmp_path: Path) -> None:
    """When ``excludeFilenames`` is absent, only ``_DEFAULT_EXCLUDES`` applies."""
    cmds = tmp_path / "cmds"
    _write_command(cmds, "CLAUDE", body="Should be excluded.\n")
    _write_command(cmds, "hello", body="Hello world.\n")

    cfg = _write_config_with_excludes(tmp_path, None)

    rc = generate_commands.generate_commands(cfg, tmp_path)
    assert rc == 0

    out_dir = tmp_path / "out_skills"
    generated = sorted(p.parent.name for p in out_dir.glob("*/SKILL.md"))
    assert "CLAUDE" not in generated, "CLAUDE.md must be excluded by _DEFAULT_EXCLUDES"
    assert "hello" in generated
