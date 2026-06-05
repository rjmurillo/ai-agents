"""Tests for the vendor-portable path helper at .claude/lib/paths.py.

Issue #2050. Covers both resolution policies:

resolve_skill_resource (read path):
  - CLAUDE_PLUGIN_ROOT candidate wins when the file exists there
  - .claude/skills/<skill>/<rel> candidate (Claude project layout)
  - plugin-install-root candidate (walk-up to .claude-plugin/plugin.json)
  - candidate order (env beats cwd beats install-root)
  - returns None when no candidate exists
  - rejects empty skill, absolute relpath, and `..` traversal

resolve_artifact_root (write path):
  - default <cwd>/.agents/<subdir>, created lazily
  - AI_AGENTS_ARTIFACT_ROOT override
  - idempotent when the directory already exists
  - rejects empty subdir, absolute subdir, and `..` traversal

The module lives outside any importable package, so it is loaded directly
via importlib.util (same approach as tests/test_bootstrap.py).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PATHS_MODULE = REPO_ROOT / ".claude" / "lib" / "paths.py"


def _load_paths():
    spec = importlib.util.spec_from_file_location("paths_under_test", PATHS_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def paths():
    return _load_paths()


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure neither env var leaks in from the runner's environment."""
    monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.delenv("AI_AGENTS_ARTIFACT_ROOT", raising=False)


# --- resolve_skill_resource: positive -------------------------------------


def test_skill_resource_prefers_plugin_root_env(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = tmp_path / "plugin"
    target = plugin_root / "skills" / "review" / "references" / "analyst.md"
    target.parent.mkdir(parents=True)
    target.write_text("axis", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_skill_resource("review", "references/analyst.md")

    assert result == target.resolve()


def test_skill_resource_claude_project_layout(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / ".claude" / "skills" / "review" / "references" / "qa.md"
    target.parent.mkdir(parents=True)
    target.write_text("axis", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_skill_resource("review", "references/qa.md")

    assert result == target.resolve()


def test_skill_resource_env_beats_cwd(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both candidates exist; CLAUDE_PLUGIN_ROOT must win.
    plugin_root = tmp_path / "plugin"
    env_target = plugin_root / "skills" / "review" / "x.md"
    env_target.parent.mkdir(parents=True)
    env_target.write_text("env", encoding="utf-8")
    cwd_target = tmp_path / ".claude" / "skills" / "review" / "x.md"
    cwd_target.parent.mkdir(parents=True)
    cwd_target.write_text("cwd", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_skill_resource("review", "x.md")

    assert result == env_target.resolve()


def test_skill_resource_prefers_copilot_plugin_root(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copilot_root = tmp_path / "copilot"
    claude_root = tmp_path / "claude"
    copilot_target = copilot_root / "skills" / "review" / "x.md"
    claude_target = claude_root / "skills" / "review" / "x.md"
    copilot_target.parent.mkdir(parents=True)
    claude_target.parent.mkdir(parents=True)
    copilot_target.write_text("copilot", encoding="utf-8")
    claude_target.write_text("claude", encoding="utf-8")
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(copilot_root))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude_root))
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_skill_resource("review", "x.md")

    assert result == copilot_target.resolve()


def test_skill_resource_env_miss_falls_back_to_install_root(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_skill_resource("review", "SKILL.md")

    assert result == (REPO_ROOT / ".claude" / "skills" / "review" / "SKILL.md").resolve()


def test_skill_resource_accepts_path_relpath(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / ".claude" / "skills" / "memory" / "scripts" / "s.py"
    target.parent.mkdir(parents=True)
    target.write_text("# s", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_skill_resource("memory", Path("scripts/s.py"))

    assert result == target.resolve()


# --- resolve_skill_resource: negative / edge -------------------------------


def test_skill_resource_returns_none_when_missing(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_skill_resource("nope", "references/missing.md")

    assert result is None


def test_skill_resource_rejects_empty_skill(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_skill_resource("", "references/x.md")


def test_skill_resource_rejects_blank_skill(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_skill_resource("   ", "references/x.md")


def test_skill_resource_rejects_absolute_skill(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_skill_resource("/etc", "passwd")


def test_skill_resource_rejects_skill_parent_traversal(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_skill_resource("../escape", "secret.md")


def test_skill_resource_rejects_dot_skill(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_skill_resource(".", "secret.md")


def test_skill_resource_rejects_absolute_relpath(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_skill_resource("review", "/etc/passwd")


def test_skill_resource_rejects_parent_traversal(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_skill_resource("review", "../../secrets.md")


# --- resolve_artifact_root: positive ---------------------------------------


def test_artifact_root_default_under_cwd(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_artifact_root("analysis")

    expected = (tmp_path / ".agents" / "analysis").resolve()
    assert result == expected
    assert result.is_dir()


def test_artifact_root_creates_nested_subdir(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_artifact_root("sessions/logs")

    assert result == (tmp_path / ".agents" / "sessions" / "logs").resolve()
    assert result.is_dir()


def test_artifact_root_base_anchors_under_base_not_cwd(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # cwd is a different directory; base must win over cwd.
    cwd_dir = tmp_path / "cwd"
    base_dir = tmp_path / "repo"
    cwd_dir.mkdir()
    base_dir.mkdir()
    monkeypatch.chdir(cwd_dir)

    result = paths.resolve_artifact_root("sessions", base=base_dir)

    assert result == (base_dir / ".agents" / "sessions").resolve()
    assert result.is_dir()
    # The cwd default location must NOT be created when base is supplied.
    assert not (cwd_dir / ".agents" / "sessions").exists()


def test_artifact_root_relative_base_anchors_under_resolved_base(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_dir = tmp_path / "repo"
    work_dir = tmp_path / "work"
    repo_dir.mkdir()
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    result = paths.resolve_artifact_root("sessions", base="../repo")

    assert result == (repo_dir / ".agents" / "sessions").resolve()
    assert result.is_dir()
    assert not (work_dir / ".agents" / "sessions").exists()


def test_artifact_root_env_override_beats_base(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "custom_root"
    base_dir = tmp_path / "repo"
    base_dir.mkdir()
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(override))
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_artifact_root("sessions", base=base_dir)

    assert result == (override / "sessions").resolve()
    assert result.is_dir()
    # base location must NOT be used when the override is set.
    assert not (base_dir / ".agents" / "sessions").exists()


def test_artifact_root_rejects_missing_base(paths, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="base must be an existing directory"):
        paths.resolve_artifact_root("sessions", base=tmp_path / "missing")


def test_artifact_root_rejects_file_base(paths, tmp_path: Path) -> None:
    base_file = tmp_path / "repo.txt"
    base_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="base must be an existing directory"):
        paths.resolve_artifact_root("sessions", base=base_file)


def test_artifact_root_env_override(paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "custom_root"
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(override))
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_artifact_root("metrics")

    assert result == (override / "metrics").resolve()
    assert result.is_dir()
    # Default location must NOT be used when the override is set.
    assert not (tmp_path / ".agents" / "metrics").exists()


def test_artifact_root_idempotent_when_exists(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    first = paths.resolve_artifact_root("analysis")
    marker = first / "keep.txt"
    marker.write_text("data", encoding="utf-8")

    second = paths.resolve_artifact_root("analysis")

    assert second == first
    assert marker.read_text(encoding="utf-8") == "data"


# --- resolve_artifact_root: negative / edge --------------------------------


def test_artifact_root_blank_override_falls_back_to_default(
    paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", "   ")
    monkeypatch.chdir(tmp_path)

    result = paths.resolve_artifact_root("analysis")

    assert result == (tmp_path / ".agents" / "analysis").resolve()


def test_artifact_root_rejects_empty_subdir(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_artifact_root("")


def test_artifact_root_rejects_dot_subdir(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_artifact_root(".")


def test_artifact_root_rejects_absolute_subdir(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_artifact_root("/var/tmp/evil")


def test_artifact_root_rejects_parent_traversal(paths) -> None:
    with pytest.raises(ValueError):
        paths.resolve_artifact_root("../escape")
