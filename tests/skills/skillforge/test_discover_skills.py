"""Tests for SkillForge discover_skills.py runtime skill roots.

Regression for issue #6646: the Phase 0 index only scanned five hard-coded
``~/.claude`` paths, so skills installed through a plugin cache were never
indexed. Covers plugin-root env vars, the folder holding the script,
``--extra-root``, and ``SKILLFORGE_EXTRA_ROOTS``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# .claude/skills/<name>/scripts is the hand-maintained source; build_all.py mirrors it.
_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "skillforge"
    / "scripts"
    / "discover_skills.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("skillforge_discover_skills", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ds = _load_module()


def _write_skill(root: Path, name: str, filename: str = "SKILL.md") -> Path:
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_text(f"---\nname: {name}\ndescription: Test skill {name}.\n---\n\n# {name}\n")
    return path


@pytest.fixture
def fake_script(tmp_path: Path) -> Path:
    """A script path laid out as <skills>/skillforge/scripts/discover_skills.py."""
    scripts = tmp_path / "plugin_local" / "skills" / "skillforge" / "scripts"
    scripts.mkdir(parents=True)
    return scripts / "discover_skills.py"


@pytest.fixture
def isolated_fixed_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the fixed sources at an empty home so tests never see real skills."""
    home = tmp_path / "home"
    monkeypatch.setattr(
        ds,
        "SKILL_SOURCES",
        [
            {
                "name": "custom",
                "path": home / ".claude" / "skills",
                "pattern": ds.RUNTIME_SKILL_PATTERN,
                "priority": 1,
            }
        ],
    )
    monkeypatch.setattr(ds, "RUNTIME_PRIORITY_START", 2)


def _names(sources: list[dict]) -> list[str]:
    return [s["name"] for s in sources]


class TestBuildSkillSources:
    def test_includes_fixed_sources_first(self, fake_script: Path) -> None:
        sources = ds.build_skill_sources(env={}, script_path=fake_script)
        fixed = [s["name"] for s in ds.SKILL_SOURCES]
        assert _names(sources)[: len(fixed)] == fixed

    def test_script_folder_is_a_source(self, fake_script: Path) -> None:
        sources = ds.build_skill_sources(env={}, script_path=fake_script)
        local = next(s for s in sources if s["name"] == "plugin-local")
        assert local["path"] == fake_script.resolve().parents[2]

    def test_plugin_root_env_vars_add_skills_dirs(self, fake_script: Path, tmp_path: Path) -> None:
        env = {
            "CLAUDE_PLUGIN_ROOT": str(tmp_path / "claude_root"),
            "COPILOT_PLUGIN_ROOT": str(tmp_path / "copilot_root"),
        }
        sources = {s["name"]: s for s in ds.build_skill_sources(env=env, script_path=fake_script)}
        assert sources["plugin-claude"]["path"] == tmp_path / "claude_root" / "skills"
        assert sources["plugin-copilot"]["path"] == tmp_path / "copilot_root" / "skills"

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_plugin_root_env_is_ignored(self, fake_script: Path, value: str) -> None:
        env = {"CLAUDE_PLUGIN_ROOT": value, "COPILOT_PLUGIN_ROOT": value}
        names = _names(ds.build_skill_sources(env=env, script_path=fake_script))
        assert "plugin-claude" not in names
        assert "plugin-copilot" not in names

    def test_unset_env_adds_nothing_but_local(self, fake_script: Path) -> None:
        names = _names(ds.build_skill_sources(env={}, script_path=fake_script))
        assert names == [s["name"] for s in ds.SKILL_SOURCES] + ["plugin-local"]

    def test_extra_roots_are_repeatable_and_numbered(
        self, fake_script: Path, tmp_path: Path
    ) -> None:
        extras = [tmp_path / "a", tmp_path / "b"]
        sources = ds.build_skill_sources(extra_roots=extras, env={}, script_path=fake_script)
        by_name = {s["name"]: s for s in sources}
        assert by_name["extra-1"]["path"] == extras[0]
        assert by_name["extra-2"]["path"] == extras[1]

    def test_env_extra_roots_split_on_pathsep_and_skip_blanks(
        self, fake_script: Path, tmp_path: Path
    ) -> None:
        value = os.pathsep.join([str(tmp_path / "x"), "", "  ", str(tmp_path / "y")])
        env = {ds.EXTRA_ROOTS_ENV: value}
        sources = ds.build_skill_sources(env=env, script_path=fake_script)
        env_sources = [s for s in sources if s["name"].startswith("env-extra-")]
        assert [s["path"] for s in env_sources] == [tmp_path / "x", tmp_path / "y"]

    def test_duplicate_root_is_dropped(self, fake_script: Path) -> None:
        local = fake_script.resolve().parents[2]
        sources = ds.build_skill_sources(extra_roots=[local], env={}, script_path=fake_script)
        assert _names(sources).count("plugin-local") == 1
        assert not any(n.startswith("extra-") for n in _names(sources))

    def test_runtime_priorities_rank_after_fixed_and_are_unique(
        self, fake_script: Path, tmp_path: Path
    ) -> None:
        sources = ds.build_skill_sources(
            extra_roots=[tmp_path / "a"],
            env={"CLAUDE_PLUGIN_ROOT": str(tmp_path / "c")},
            script_path=fake_script,
        )
        priorities = [s["priority"] for s in sources]
        assert len(set(priorities)) == len(priorities)
        fixed_max = max(s["priority"] for s in ds.SKILL_SOURCES)
        runtime = [s["priority"] for s in sources if s["priority"] > fixed_max]
        assert len(runtime) == 3

    def test_does_not_mutate_module_constant(self, fake_script: Path, tmp_path: Path) -> None:
        before = [dict(s) for s in ds.SKILL_SOURCES]
        ds.build_skill_sources(extra_roots=[tmp_path], env={}, script_path=fake_script)
        assert before == ds.SKILL_SOURCES

    def test_reads_process_environment_by_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "from_env"))
        sources = {s["name"]: s for s in ds.build_skill_sources()}
        assert sources["plugin-claude"]["path"] == tmp_path / "from_env" / "skills"


@pytest.mark.usefixtures("isolated_fixed_sources")
class TestDiscoverSkills:
    def test_extra_root_skill_is_indexed(self, fake_script: Path, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        _write_skill(extra, "plugin-skill")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        names = [s["name"] for s in result.data["skills"]]
        assert "plugin-skill" in names
        skill = next(s for s in result.data["skills"] if s["name"] == "plugin-skill")
        assert skill["source"] == "extra-1"

    def test_plugin_root_skills_are_indexed(self, fake_script: Path, tmp_path: Path) -> None:
        _write_skill(tmp_path / "plug" / "skills", "from-plugin")
        env = {"COPILOT_PLUGIN_ROOT": str(tmp_path / "plug")}
        sources = ds.build_skill_sources(env=env, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert "from-plugin" in [s["name"] for s in result.data["skills"]]

    def test_script_folder_skills_are_indexed(self, fake_script: Path) -> None:
        _write_skill(fake_script.resolve().parents[2], "sibling")
        sources = ds.build_skill_sources(env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert "sibling" in [s["name"] for s in result.data["skills"]]

    def test_missing_root_warns_without_crashing(self, fake_script: Path, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        sources = ds.build_skill_sources(extra_roots=[missing], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert result.success
        assert any("extra-1" in w and str(missing) in w for w in result.warnings)
        assert "extra-1" in result.data["missing_sources"]

    def test_same_skill_via_two_roots_counts_once(self, fake_script: Path, tmp_path: Path) -> None:
        root = tmp_path / "shared"
        _write_skill(root, "dup")
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        sources = ds.build_skill_sources(extra_roots=[root, alias], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert [s["name"] for s in result.data["skills"]].count("dup") == 1
        assert result.data["total_count"] == 1

    def test_lowercase_skill_md_is_found(self, fake_script: Path, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        _write_skill(extra, "lower", filename="skill.md")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert "lower" in [s["name"] for s in result.data["skills"]]

    def test_nested_non_skill_files_are_ignored(self, fake_script: Path, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        _write_skill(extra, "real")
        (extra / "real" / "references").mkdir()
        (extra / "real" / "references" / "SKILL.md").write_text("# nested\n")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert result.data["total_count"] == 1

    def test_unreadable_skill_file_warns(self, fake_script: Path, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        folder = extra / "bad"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_bytes(b"\xff\xfe\x00invalid utf8 \xc3\x28")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert any("Failed to parse" in w for w in result.warnings)

    def test_result_reports_sources_and_counts(self, fake_script: Path, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        _write_skill(extra, "one")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert result.data["source_count"] == len(sources)
        assert set(result.data["sources"]) == set(_names(sources))
        assert f"from {len(sources)} sources" in result.message

    def test_default_sources_come_from_build_skill_sources(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        extra = tmp_path / "extra"
        _write_skill(extra, "env-skill")
        monkeypatch.setenv(ds.EXTRA_ROOTS_ENV, str(extra))
        result = ds.discover_skills()
        assert "env-skill" in [s["name"] for s in result.data["skills"]]


@pytest.mark.usefixtures("isolated_fixed_sources")
class TestMain:
    def _run(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *argv: str) -> tuple[int, Path]:
        out = tmp_path / "index.json"
        monkeypatch.setattr(sys, "argv", ["discover_skills.py", "-o", str(out), *argv])
        with pytest.raises(SystemExit) as exc:
            ds.main()
        return int(exc.value.code or 0), out

    def test_extra_root_flag_indexes_skill_and_exits_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        extra = tmp_path / "extra"
        _write_skill(extra, "flagged")
        monkeypatch.delenv(ds.EXTRA_ROOTS_ENV, raising=False)
        code, out = self._run(monkeypatch, tmp_path, "--extra-root", str(extra))
        assert code == 0
        index = json.loads(out.read_text())
        assert "flagged" in [s["name"] for s in index["skills"]]

    def test_extra_root_flag_is_repeatable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        _write_skill(a, "alpha")
        _write_skill(b, "beta")
        monkeypatch.delenv(ds.EXTRA_ROOTS_ENV, raising=False)
        code, out = self._run(monkeypatch, tmp_path, "--extra-root", str(a), "--extra-root", str(b))
        names = [s["name"] for s in json.loads(out.read_text())["skills"]]
        assert code == 0
        assert {"alpha", "beta"} <= set(names)

    def test_exit_3_when_every_source_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv(ds.EXTRA_ROOTS_ENV, raising=False)
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        # Force every runtime source to be missing, including the script folder.
        monkeypatch.setattr(
            ds,
            "build_skill_sources",
            lambda extra_roots=None: [
                {
                    "name": "gone",
                    "path": tmp_path / "gone",
                    "pattern": ds.RUNTIME_SKILL_PATTERN,
                    "priority": 1,
                }
            ],
        )
        code, _ = self._run(monkeypatch, tmp_path)
        assert code == 3

    def test_exit_0_when_some_sources_exist_but_hold_no_skills(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr(
            ds,
            "build_skill_sources",
            lambda extra_roots=None: [
                {
                    "name": "empty",
                    "path": empty,
                    "pattern": ds.RUNTIME_SKILL_PATTERN,
                    "priority": 1,
                },
                {
                    "name": "gone",
                    "path": tmp_path / "gone",
                    "pattern": ds.RUNTIME_SKILL_PATTERN,
                    "priority": 2,
                },
            ],
        )
        code, _ = self._run(monkeypatch, tmp_path)
        assert code == 0

    def test_json_output_lists_runtime_sources(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        extra = tmp_path / "extra"
        _write_skill(extra, "j")
        monkeypatch.delenv(ds.EXTRA_ROOTS_ENV, raising=False)
        code, _ = self._run(monkeypatch, tmp_path, "--json", "--extra-root", str(extra))
        payload = json.loads(capsys.readouterr().out)
        assert code == 0
        assert payload["data"]["sources"]["extra-1"] == str(extra)
