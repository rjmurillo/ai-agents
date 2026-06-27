"""Tests for build/scripts/generate_skills.py (REQ-003-001, REQ-003-008)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import generate_skills  # noqa: E402

_GATED_SKILL_TREE_MIRRORS = (
    "review",
    "cva-analysis",
    "orphan-ref-validator",
    "security-detection",
    "slashcommandcreator",
)


# Helpers --------------------------------------------------------------------


def _write_minimal_skill(skills_dir: Path, name: str, *, body: str = "ok\n") -> Path:
    skill = skills_dir / name
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(f"# {name}\n{body}")
    return skill


def _write_config(
    tmp_path: Path,
    *,
    source_dir: str,
    output_dir: str,
    mode: str = "directory-copy",
    extra_artifacts: bool = False,
) -> Path:
    extra = ""
    if extra_artifacts:
        extra = """
  agents:
    sourceDir: ".claude/agents"
    outputDir: "src/copilot-cli/agents"
"""
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        f"""\
schemaVersion: "1.0"
provider: "test"
artifacts:
  skills:
    sourceDir: "{source_dir}"
    outputDir: "{output_dir}"
    mode: "{mode}"
{extra}
"""
    )
    return cfg


def _skillforge_validation(skill_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / ".claude" / "skills" / "SkillForge" / "scripts" / "validate-skill.py"),
            str(skill_dir.relative_to(REPO_ROOT)),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


# Happy path -----------------------------------------------------------------


def test_directory_copy_writes_skill_md_to_output(tmp_path: Path) -> None:
    repo_root = tmp_path
    skills_src = repo_root / "skills_src"
    _write_minimal_skill(skills_src, "alpha")
    _write_minimal_skill(skills_src, "beta")

    cfg = _write_config(
        tmp_path, source_dir="skills_src", output_dir="skills_out"
    )

    rc = generate_skills.generate_skills(cfg, repo_root)
    assert rc == 0
    assert (repo_root / "skills_out" / "alpha" / "SKILL.md").is_file()
    assert (repo_root / "skills_out" / "beta" / "SKILL.md").is_file()


@pytest.mark.parametrize("skill_name", _GATED_SKILL_TREE_MIRRORS)
def test_committed_skill_tree_mirror_matches_source_skill_md(skill_name: str) -> None:
    """Committed Copilot skill-tree mirrors stay byte-for-byte in sync."""
    source = REPO_ROOT / ".claude" / "skills" / skill_name / "SKILL.md"
    mirror = REPO_ROOT / "src" / "copilot-cli" / "skills" / skill_name / "SKILL.md"

    assert source.is_file(), f"missing source skill: {source}"
    assert mirror.is_file(), f"missing Copilot skill mirror: {mirror}"
    assert mirror.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


@pytest.mark.parametrize("skill_name", _GATED_SKILL_TREE_MIRRORS)
def test_committed_skill_tree_source_and_mirror_pass_skillforge(skill_name: str) -> None:
    """Committed source skills and Copilot mirrors must pass SkillForge."""
    for skill_dir in (
        REPO_ROOT / ".claude" / "skills" / skill_name,
        REPO_ROOT / "src" / "copilot-cli" / "skills" / skill_name,
    ):
        result = _skillforge_validation(skill_dir)

        assert result.returncode == 0, (
            f"SkillForge failed for {skill_dir.relative_to(REPO_ROOT)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def test_nested_files_preserved(tmp_path: Path) -> None:
    """Skills carry scripts/, references/, etc.; directory copy must keep them."""
    repo_root = tmp_path
    src = repo_root / "skills"
    skill = _write_minimal_skill(src, "gamma")
    nested_dir = skill / "scripts"
    nested_dir.mkdir()
    (nested_dir / "run.py").write_text("print('hi')\n")
    cfg = _write_config(tmp_path, source_dir="skills", output_dir="out")

    rc = generate_skills.generate_skills(cfg, repo_root)
    assert rc == 0
    assert (repo_root / "out" / "gamma" / "scripts" / "run.py").is_file()


def test_pycache_artifacts_excluded(tmp_path: Path) -> None:
    """Build-time cruft must not land in plugin installs."""
    repo_root = tmp_path
    src = repo_root / "skills"
    skill = _write_minimal_skill(src, "delta")
    cache = skill / "__pycache__"
    cache.mkdir()
    (cache / "x.cpython-314.pyc").write_bytes(b"")
    cfg = _write_config(tmp_path, source_dir="skills", output_dir="out")

    assert generate_skills.generate_skills(cfg, repo_root) == 0
    assert not (repo_root / "out" / "delta" / "__pycache__").exists()


def test_excluded_top_level_files_not_treated_as_skills(tmp_path: Path) -> None:
    """A bare AGENTS.md at .claude/skills/ root must not break enumeration."""
    repo_root = tmp_path
    src = repo_root / "skills"
    src.mkdir()
    (src / "AGENTS.md").write_text("# header\n")
    (src / "CLAUDE.md").write_text("# header\n")
    _write_minimal_skill(src, "epsilon")
    cfg = _write_config(tmp_path, source_dir="skills", output_dir="out")

    assert generate_skills.generate_skills(cfg, repo_root) == 0
    assert (repo_root / "out" / "epsilon" / "SKILL.md").is_file()
    assert not (repo_root / "out" / "AGENTS.md").exists()


def test_directory_without_skill_md_is_skipped(tmp_path: Path) -> None:
    """REQ-003 says SKILL.md is the marker; bare dirs are not skills."""
    repo_root = tmp_path
    src = repo_root / "skills"
    src.mkdir()
    (src / "not-a-skill").mkdir()
    (src / "not-a-skill" / "README.md").write_text("# nope\n")
    _write_minimal_skill(src, "real")
    cfg = _write_config(tmp_path, source_dir="skills", output_dir="out")

    assert generate_skills.generate_skills(cfg, repo_root) == 0
    assert not (repo_root / "out" / "not-a-skill").exists()
    assert (repo_root / "out" / "real" / "SKILL.md").is_file()


# Negative path: configuration ----------------------------------------------


def test_missing_artifacts_skills_returns_2(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text('schemaVersion: "1.0"\nprovider: "x"\n')
    assert generate_skills.generate_skills(cfg, tmp_path) == 2


def test_unsupported_mode_returns_2(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write_minimal_skill(repo_root / "skills", "alpha")
    cfg = _write_config(
        tmp_path, source_dir="skills", output_dir="out", mode="symlink"
    )
    assert generate_skills.generate_skills(cfg, repo_root) == 2


def test_no_skills_found_returns_1(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "skills").mkdir()
    cfg = _write_config(tmp_path, source_dir="skills", output_dir="out")
    assert generate_skills.generate_skills(cfg, repo_root) == 1


def test_absolute_source_dir_rejected(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path, source_dir="/etc/passwd", output_dir="out")
    assert generate_skills.generate_skills(cfg, tmp_path) == 2


def test_traversal_output_dir_rejected(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write_minimal_skill(repo_root / "skills", "alpha")
    cfg = _write_config(tmp_path, source_dir="skills", output_dir="../escape")
    assert generate_skills.generate_skills(cfg, repo_root) == 2


# NO-REGEN sentinel ---------------------------------------------------------


def test_sidecar_protected_file_is_not_overwritten(tmp_path: Path) -> None:
    repo_root = tmp_path
    src = repo_root / "skills"
    _write_minimal_skill(src, "zeta", body="generated body\n")
    out = repo_root / "out"
    (out / "zeta").mkdir(parents=True)
    target_file = out / "zeta" / "SKILL.md"
    target_file.write_text("hand-edited; do not overwrite\n")
    (target_file.parent / "SKILL.md.noregen").write_text("")

    cfg = _write_config(tmp_path, source_dir="skills", output_dir="out")
    assert generate_skills.generate_skills(cfg, repo_root) == 0
    assert target_file.read_text() == "hand-edited; do not overwrite\n"


def test_what_if_does_not_write(tmp_path: Path) -> None:
    repo_root = tmp_path
    _write_minimal_skill(repo_root / "skills", "alpha")
    cfg = _write_config(tmp_path, source_dir="skills", output_dir="out")
    assert generate_skills.generate_skills(cfg, repo_root, what_if=True) == 0
    assert not (repo_root / "out").exists()


# CLI entry point -----------------------------------------------------------


def test_main_missing_config_returns_2(tmp_path: Path) -> None:
    rc = generate_skills.main([
        "--config",
        str(tmp_path / "nope.yaml"),
        "--repo-root",
        str(tmp_path),
    ])
    assert rc == 2


@pytest.mark.parametrize("argv", [["--what-if"], []])
def test_main_invokes_generation(tmp_path: Path, argv: list[str]) -> None:
    repo_root = tmp_path
    _write_minimal_skill(repo_root / "skills", "alpha")
    cfg = _write_config(tmp_path, source_dir="skills", output_dir="out")
    rc = generate_skills.main([
        "--config", str(cfg), "--repo-root", str(repo_root), *argv,
    ])
    assert rc == 0
