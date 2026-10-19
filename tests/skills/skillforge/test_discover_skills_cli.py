"""Tests for SkillForge discover_skills.py frontmatter handling and main().

Regression for issue #6646. Split from test_discover_skills.py to stay under the
500-line taste-lint ceiling. Covers malformed ``name:`` and ``description:``
values and the command-line entry point.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# src/claude/skills/<name>/scripts is the hand-maintained source (ADR-119).
_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "claude"
    / "skills"
    / "skillforge"
    / "scripts"
    / "discover_skills.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("skillforge_discover_skills_cli", _SCRIPT)
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
