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
    path.write_text(
        f"---\nname: {name}\ndescription: Test skill {name}.\n---\n\n# {name}\n", encoding="utf-8"
    )
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
        try:
            alias.symlink_to(root, target_is_directory=True)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable on this platform: {exc}")
        sources = ds.build_skill_sources(extra_roots=[root, alias], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert [s["name"] for s in result.data["skills"]].count("dup") == 1
        assert result.data["total_count"] == 1

    def test_same_name_in_two_roots_keeps_higher_ranked_source(
        self, fake_script: Path, tmp_path: Path
    ) -> None:
        first = tmp_path / "first"
        second = tmp_path / "second"
        winner = _write_skill(first, "dup")
        loser = _write_skill(second, "dup")
        sources = ds.build_skill_sources(
            extra_roots=[first, second], env={}, script_path=fake_script
        )
        result = ds.discover_skills(sources=sources)
        entries = [s for s in result.data["skills"] if s["name"] == "dup"]
        assert len(entries) == 1
        assert entries[0]["source"] == "extra-1"
        assert entries[0]["path"] == str(winner)
        assert entries[0]["shadowed_paths"] == [str(loser)]
        assert result.data["domains"]["general"].count("dup") == 1

    def test_reversed_root_order_flips_the_winner(self, fake_script: Path, tmp_path: Path) -> None:
        first = tmp_path / "first"
        second = tmp_path / "second"
        _write_skill(first, "dup")
        winner = _write_skill(second, "dup")
        sources = ds.build_skill_sources(
            extra_roots=[second, first], env={}, script_path=fake_script
        )
        result = ds.discover_skills(sources=sources)
        entries = [s for s in result.data["skills"] if s["name"] == "dup"]
        assert [e["path"] for e in entries] == [str(winner)]

    def test_fixed_source_beats_runtime_root_with_same_name(
        self,
        isolated_fixed_sources: None,
        fake_script: Path,
        tmp_path: Path,
    ) -> None:
        custom = tmp_path / "home" / ".claude" / "skills"
        winner = _write_skill(custom, "dup")
        extra = tmp_path / "extra"
        _write_skill(extra, "dup")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        entries = [s for s in result.data["skills"] if s["name"] == "dup"]
        assert len(entries) == 1
        assert entries[0]["source"] == "custom"
        assert entries[0]["path"] == str(winner)

    def test_name_match_ignores_case_and_whitespace(
        self, fake_script: Path, tmp_path: Path
    ) -> None:
        first = tmp_path / "first"
        second = tmp_path / "second"
        _write_skill(first, "dup")
        other = second / "other-folder"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text(
            "---\nname: ' DUP '\ndescription: Same skill.\n---\n", encoding="utf-8"
        )
        sources = ds.build_skill_sources(
            extra_roots=[first, second], env={}, script_path=fake_script
        )
        result = ds.discover_skills(sources=sources)
        names = [s["name"] for s in result.data["skills"] if s["name"].strip().lower() == "dup"]
        assert names == ["dup"]

    def test_distinct_names_are_not_deduped(self, fake_script: Path, tmp_path: Path) -> None:
        first = tmp_path / "first"
        second = tmp_path / "second"
        _write_skill(first, "alpha")
        _write_skill(second, "beta")
        sources = ds.build_skill_sources(
            extra_roots=[first, second], env={}, script_path=fake_script
        )
        result = ds.discover_skills(sources=sources)
        by_name = {s["name"]: s for s in result.data["skills"]}
        assert {"alpha", "beta"} <= set(by_name)
        assert by_name["alpha"]["shadowed_paths"] == []
        assert by_name["beta"]["shadowed_paths"] == []

    def test_verbose_reports_shadowed_copy(
        self, fake_script: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        first = tmp_path / "first"
        second = tmp_path / "second"
        _write_skill(first, "dup")
        _write_skill(second, "dup")
        sources = ds.build_skill_sources(
            extra_roots=[first, second], env={}, script_path=fake_script
        )
        ds.discover_skills(verbose=True, sources=sources)
        assert "Shadowed: dup (extra-2) by extra-1" in capsys.readouterr().err

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
        (extra / "real" / "references" / "SKILL.md").write_text("# nested\n", encoding="utf-8")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert result.data["total_count"] == 1

    def test_skill_md_beats_sibling_markdown_in_a_glob_source(self, tmp_path: Path) -> None:
        """A */*.md source parses every file; sibling notes must not shadow SKILL.md."""
        root = tmp_path / "plugin"
        folder = root / "systematic-debugging"
        folder.mkdir(parents=True)
        real = folder / "SKILL.md"
        real.write_text(
            "---\ndescription: Real skill description\n---\n\n# Real\n", encoding="utf-8"
        )
        (folder / "CREATION-LOG.md").write_text(
            "Notes about how this was made.\n", encoding="utf-8"
        )
        (folder / "README.md").write_text("Readme text.\n", encoding="utf-8")
        source = {"name": "glob", "path": root, "pattern": "*/*.md", "priority": 1}
        result = ds.discover_skills(sources=[source])
        entries = result.data["skills"]
        assert len(entries) == 1
        assert entries[0]["path"] == str(real)
        assert entries[0]["description"] == "Real skill description"
        assert sorted(Path(p).name for p in entries[0]["shadowed_paths"]) == [
            "CREATION-LOG.md",
            "README.md",
        ]

    def test_lowercase_skill_md_beats_sibling_markdown(self, tmp_path: Path) -> None:
        root = tmp_path / "plugin"
        folder = root / "alpha"
        folder.mkdir(parents=True)
        real = folder / "skill.md"
        real.write_text("---\ndescription: Lowercase real\n---\n", encoding="utf-8")
        (folder / "AAA-notes.md").write_text("Notes.\n", encoding="utf-8")
        source = {"name": "glob", "path": root, "pattern": "*/*.md", "priority": 1}
        result = ds.discover_skills(sources=[source])
        assert [s["path"] for s in result.data["skills"]] == [str(real)]

    def test_folder_without_skill_md_still_indexes_its_markdown(self, tmp_path: Path) -> None:
        root = tmp_path / "plugin"
        (root / "only-notes").mkdir(parents=True)
        (root / "only-notes" / "README.md").write_text("Just a readme.\n", encoding="utf-8")
        source = {"name": "glob", "path": root, "pattern": "*/*.md", "priority": 1}
        result = ds.discover_skills(sources=[source])
        assert [s["name"] for s in result.data["skills"]] == ["only-notes"]

    def test_skill_md_preference_applies_across_case_variants_of_a_name(
        self, tmp_path: Path
    ) -> None:
        """Dedupe folds case, so the SKILL.md preference must sort on the folded name."""
        root = tmp_path / "plugin"
        (root / "Dup").mkdir(parents=True)
        (root / "dup").mkdir(parents=True)
        (root / "Dup" / "notes.md").write_text("No frontmatter.\n", encoding="utf-8")
        real = root / "dup" / "SKILL.md"
        real.write_text("---\nname: dup\ndescription: Real\n---\n", encoding="utf-8")
        source = {"name": "glob", "path": root, "pattern": "*/*.md", "priority": 1}
        result = ds.discover_skills(sources=[source])
        assert [s["path"] for s in result.data["skills"]] == [str(real)]

    def test_skill_folder_passed_as_root_warns_with_fix(
        self, fake_script: Path, tmp_path: Path
    ) -> None:
        solo = tmp_path / "solo-skill"
        solo.mkdir()
        (solo / "SKILL.md").write_text(
            "---\nname: solo\ndescription: One.\n---\n", encoding="utf-8"
        )
        sources = ds.build_skill_sources(extra_roots=[solo], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert "solo" not in [s["name"] for s in result.data["skills"]]
        matching = [w for w in result.warnings if str(solo) in w]
        assert len(matching) == 1
        assert "extra-1" in matching[0]
        assert "pass its parent directory" in matching[0]

    def test_empty_existing_root_warns(self, fake_script: Path, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        sources = ds.build_skill_sources(extra_roots=[empty], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        matching = [w for w in result.warnings if str(empty) in w]
        assert len(matching) == 1
        assert "subfolder holding SKILL.md" in matching[0]

    def test_root_with_skills_does_not_warn_empty(self, fake_script: Path, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        _write_skill(extra, "fine")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert not [w for w in result.warnings if str(extra) in w]

    def test_empty_fixed_source_does_not_warn(self, tmp_path: Path) -> None:
        """Only runtime roots warn; a bare fixed source is normal on a clean host."""
        root = tmp_path / "fixed"
        root.mkdir()
        source = {"name": "fixed", "path": root, "pattern": ds.RUNTIME_SKILL_PATTERN, "priority": 1}
        result = ds.discover_skills(sources=[source])
        assert not [w for w in result.warnings if "No skills found" in w]

    def test_unlistable_root_still_warns(
        self, fake_script: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empty = tmp_path / "locked"
        empty.mkdir()

        def boom(self: Path):
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "iterdir", boom)
        warning = ds._empty_root_warning({"name": "extra-1", "path": empty})
        assert "No skills found in extra-1" in warning
        assert "subfolder holding SKILL.md" in warning

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
class TestMalformedName:
    """A bad `name:` in one third-party SKILL.md must not abort the whole run."""

    @staticmethod
    def _write_raw(root: Path, folder: str, frontmatter: str) -> Path:
        path = root / folder / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\n{frontmatter}\ndescription: Raw {folder}.\n---\n\n# {folder}\n", encoding="utf-8"
        )
        return path

    def test_blank_and_integer_names_fall_back_to_folder_name(
        self, fake_script: Path, tmp_path: Path
    ) -> None:
        extra = tmp_path / "extra"
        self._write_raw(extra, "blank-one", "name:")
        self._write_raw(extra, "int-one", "name: 42")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert result.success
        assert not result.errors
        names = [s["name"] for s in result.data["skills"]]
        assert "blank-one" in names
        assert "int-one" in names

    def test_malformed_names_are_not_folded_under_one_key(
        self, fake_script: Path, tmp_path: Path
    ) -> None:
        extra = tmp_path / "extra"
        self._write_raw(extra, "first", "name:")
        self._write_raw(extra, "second", "name:")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert sorted(s["name"] for s in result.data["skills"]) == ["first", "second"]
        assert result.data["total_count"] == 2

    def test_whitespace_only_and_list_names_fall_back(
        self, fake_script: Path, tmp_path: Path
    ) -> None:
        extra = tmp_path / "extra"
        self._write_raw(extra, "spaces", 'name: "   "')
        self._write_raw(extra, "listy", "name: [a, b]")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert sorted(s["name"] for s in result.data["skills"]) == ["listy", "spaces"]

    def test_valid_name_is_kept_over_folder_name(self, fake_script: Path, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        self._write_raw(extra, "folder-name", "name: declared-name")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        assert [s["name"] for s in result.data["skills"]] == ["declared-name"]

    def test_parse_skill_file_does_not_raise_on_blank_name(self, tmp_path: Path) -> None:
        path = self._write_raw(tmp_path, "solo", "name:")
        parsed = ds.parse_skill_file(path, "extra-1", 9)
        assert parsed is not None
        assert parsed["name"] == "solo"
        assert "solo" in parsed["keywords"]


@pytest.mark.usefixtures("isolated_fixed_sources")
class TestNonStringDescription:
    """A bare YAML date or number in `description:` must not break save_index."""

    @staticmethod
    def _write_raw(root: Path, folder: str, description_line: str) -> Path:
        path = root / folder / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nname: {folder}\n{description_line}\n---\n\n# {folder}\n", encoding="utf-8"
        )
        return path

    def test_date_description_becomes_text(self, tmp_path: Path) -> None:
        path = self._write_raw(tmp_path, "dated", "description: 2024-01-01")
        parsed = ds.parse_skill_file(path, "extra-1", 9)
        assert parsed is not None
        assert parsed["description"] == "2024-01-01"

    def test_numeric_and_list_descriptions_become_text(self, tmp_path: Path) -> None:
        number = ds.parse_skill_file(self._write_raw(tmp_path, "num", "description: 42"), "x", 9)
        listy = ds.parse_skill_file(self._write_raw(tmp_path, "lst", "description: [a, b]"), "x", 9)
        assert number is not None and listy is not None
        assert number["description"] == "42"
        assert isinstance(listy["description"], str)

    def test_blank_description_still_falls_back_to_first_paragraph(self, tmp_path: Path) -> None:
        path = self._write_raw(tmp_path, "blank", "description:")
        parsed = ds.parse_skill_file(path, "x", 9)
        assert parsed is not None
        assert parsed["description"] == "name: blank"

    def test_save_index_writes_index_for_date_description(
        self, fake_script: Path, tmp_path: Path
    ) -> None:
        extra = tmp_path / "extra"
        self._write_raw(extra, "dated", "description: 2024-01-01")
        sources = ds.build_skill_sources(extra_roots=[extra], env={}, script_path=fake_script)
        result = ds.discover_skills(sources=sources)
        out = tmp_path / "index.json"
        ds.save_index(result, out)
        index = json.loads(out.read_text(encoding="utf-8"))
        assert [s["description"] for s in index["skills"]] == ["2024-01-01"]


@pytest.mark.usefixtures("isolated_fixed_sources")
class TestMain:
    @pytest.fixture(autouse=True)
    def _hermetic_main(self, monkeypatch: pytest.MonkeyPatch, fake_script: Path) -> None:
        """Keep main() off the real repo skills and the host plugin env.

        main() builds the plugin-local root from this module's own path, which
        is the repo's .claude/skills. Route it to the fake script folder, and
        clear every env var that adds a root.
        """
        for var in (ds.EXTRA_ROOTS_ENV, "CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"):
            monkeypatch.delenv(var, raising=False)
        real = ds.build_skill_sources
        monkeypatch.setattr(
            ds,
            "build_skill_sources",
            lambda extra_roots=None: real(extra_roots=extra_roots, env={}, script_path=fake_script),
        )

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
        index = json.loads(out.read_text(encoding="utf-8"))
        entries = {s["name"]: s for s in index["skills"]}
        assert entries["flagged"]["source"] == "extra-1"

    def test_extra_root_flag_is_repeatable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        a, b = tmp_path / "a", tmp_path / "b"
        _write_skill(a, "alpha")
        _write_skill(b, "beta")
        monkeypatch.delenv(ds.EXTRA_ROOTS_ENV, raising=False)
        code, out = self._run(monkeypatch, tmp_path, "--extra-root", str(a), "--extra-root", str(b))
        entries = {s["name"]: s for s in json.loads(out.read_text(encoding="utf-8"))["skills"]}
        assert code == 0
        assert entries["alpha"]["source"] == "extra-1"
        assert entries["beta"]["source"] == "extra-2"

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


@pytest.mark.usefixtures("isolated_fixed_sources")
class TestMainEmptyRoot:
    def test_skill_folder_as_extra_root_prints_warning_and_exits_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        solo = tmp_path / "solo"
        solo.mkdir()
        (solo / "SKILL.md").write_text(
            "---\nname: solo\ndescription: One.\n---\n", encoding="utf-8"
        )
        home_skills = tmp_path / "home" / ".claude" / "skills"
        _write_skill(home_skills, "present")
        monkeypatch.delenv(ds.EXTRA_ROOTS_ENV, raising=False)
        out = tmp_path / "index.json"
        monkeypatch.setattr(
            sys, "argv", ["discover_skills.py", "-o", str(out), "--json", "--extra-root", str(solo)]
        )
        with pytest.raises(SystemExit) as exc:
            ds.main()
        payload = json.loads(capsys.readouterr().out)
        assert exc.value.code == 0
        assert any(str(solo) in w and "parent directory" in w for w in payload["warnings"])

    def test_help_describes_extra_root_as_parent_directory(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["discover_skills.py", "--help"])
        with pytest.raises(SystemExit):
            ds.main()
        text = " ".join(capsys.readouterr().out.split())
        assert "subfolders hold SKILL.md" in text
