"""CLI contract tests for the SkillForge validator scripts (Issue #6648).

Covers the shared skill-directory argument, --help, and the rule that a run
which audits nothing exits non-zero instead of passing a gate by mistake.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_DIR = _PROJECT_ROOT / ".claude" / "skills" / "skillforge" / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPT_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


audit = _load("skillforge_modularity_audit_cli", "skill_modularity_audit.py")
docs_safety = _load("skillforge_check_docs_safety_cli", "check_docs_safety.py")

SAFE_DOC = '---\nname: ok\n---\n## P\ncommand: run "$TOOL_INPUT"\n'
UNSAFE_DOC = "---\nname: bad\n---\n## P\ncommand: run $TOOL_INPUT\n"


def _make_skill(root: Path, name: str, body: str = SAFE_DOC) -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(body, encoding="utf-8")
    return skill


class TestModularityAuditEmptyInput:
    """An audit of zero skills is a config error (exit 2), never a pass."""

    def test_empty_dir_exits_2_text(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        assert audit.main(["--path", str(tmp_path)]) == 2
        err = capsys.readouterr().err
        assert "0 examined" in err

    def test_empty_dir_exits_2_json(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        assert audit.main(["--path", str(tmp_path), "--json"]) == 2
        captured = capsys.readouterr()
        assert json.loads(captured.out) == []
        assert "0 examined" in captured.err

    def test_empty_dir_exits_2_in_ci_mode(self, tmp_path: Path):
        assert audit.main(["--path", str(tmp_path), "--ci"]) == 2

    def test_dir_of_non_skills_exits_2(self, tmp_path: Path):
        (tmp_path / "not-a-skill").mkdir()
        (tmp_path / "not-a-skill" / "README.md").write_text("x", encoding="utf-8")
        assert audit.main(["--path", str(tmp_path)]) == 2

    def test_missing_path_still_exits_2(self, tmp_path: Path):
        assert audit.main(["--path", str(tmp_path / "missing")]) == 2

    def test_only_unreadable_skill_md_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        skill = tmp_path / "skills" / "binary"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(b"\xff\xfe\x00bad")
        # Nothing was audited, so the run must not pass, with or without --ci.
        assert audit.main([str(skill)]) == 2
        assert "could not be read" in capsys.readouterr().err

    def test_only_unreadable_skill_md_exits_2_in_ci_mode(self, tmp_path: Path):
        skill = tmp_path / "skills" / "binary"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_bytes(b"\xff\xfe\x00bad")
        assert audit.main([str(skill), "--ci"]) == 2

    def test_one_unreadable_among_readable_passes_without_ci(self, tmp_path: Path):
        _make_skill(tmp_path, "good")
        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "SKILL.md").write_bytes(b"\xff\xfe\x00bad")
        # Something was audited, so the non-gate run still succeeds.
        assert audit.main([str(tmp_path)]) == 0

    def test_one_unreadable_among_readable_fails_ci(self, tmp_path: Path):
        _make_skill(tmp_path, "good")
        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "SKILL.md").write_bytes(b"\xff\xfe\x00bad")
        assert audit.main([str(tmp_path), "--ci"]) == 2

    def test_oversized_without_ci_exits_0(self, tmp_path: Path):
        lines = ["---", "name: huge", "---"] + ["line"] * 600
        skill = _make_skill(tmp_path, "huge", "\n".join(lines))
        # Documents why the checklist command carries --ci.
        assert audit.main([str(skill)]) == 0


class TestModularityAuditSkillDirectory:
    """A single skill directory works as --path and as a positional."""

    def test_path_naming_one_skill_audits_that_skill(self, tmp_path: Path):
        skill = _make_skill(tmp_path, "my-skill")
        assert audit.main(["--path", str(skill)]) == 0

    def test_positional_skill_dir_audits_that_skill(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        skill = _make_skill(tmp_path, "my-skill")
        assert audit.main([str(skill), "--json"]) == 0
        rows = json.loads(capsys.readouterr().out)
        assert [row["name"] for row in rows] == ["my-skill"]

    def test_positional_parent_dir_audits_children(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        _make_skill(tmp_path, "one")
        _make_skill(tmp_path, "two")
        assert audit.main([str(tmp_path), "--json"]) == 0
        rows = json.loads(capsys.readouterr().out)
        assert sorted(row["name"] for row in rows) == ["one", "two"]

    def test_single_oversized_skill_fails_ci(self, tmp_path: Path):
        lines = ["---", "name: huge", "---"] + ["line"] * 600
        skill = _make_skill(tmp_path, "huge", "\n".join(lines))
        assert audit.main([str(skill), "--ci"]) == 1

    def test_positional_and_path_together_is_rejected(self, tmp_path: Path):
        skill = _make_skill(tmp_path, "my-skill")
        with pytest.raises(SystemExit) as excinfo:
            audit.main([str(skill), "--path", str(tmp_path)])
        assert excinfo.value.code == 2

    def test_positional_traversal_is_rejected(self):
        assert audit.main(["../../../etc"]) == 2

    def test_help_exits_0_and_documents_exit_codes(self, capsys: pytest.CaptureFixture[str]):
        with pytest.raises(SystemExit) as excinfo:
            audit.main(["--help"])
        assert excinfo.value.code == 0
        assert "Exit codes" in capsys.readouterr().out


class TestCheckDocsSafety:
    """check_docs_safety takes a skill directory, files, or --help."""

    def test_help_exits_0(self, capsys: pytest.CaptureFixture[str]):
        with pytest.raises(SystemExit) as excinfo:
            docs_safety.main(["--help"])
        assert excinfo.value.code == 0
        assert "Exit codes" in capsys.readouterr().out

    def test_skill_dir_with_safe_docs_exits_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        skill = _make_skill(tmp_path, "my-skill")
        (skill / "references").mkdir()
        (skill / "references" / "a.md").write_text("plain text\n", encoding="utf-8")
        assert docs_safety.main([str(skill)]) == 0
        assert "2 files scanned" in capsys.readouterr().out

    def test_skill_dir_scans_references_for_unsafe_lines(self, tmp_path: Path):
        skill = _make_skill(tmp_path, "my-skill")
        (skill / "references").mkdir()
        (skill / "references" / "bad.md").write_text(
            "command: run $TOOL_OUTPUT\n", encoding="utf-8"
        )
        assert docs_safety.main([str(skill)]) == 1

    def test_skill_dir_with_unsafe_skill_md_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        skill = _make_skill(tmp_path, "bad-skill", UNSAFE_DOC)
        assert docs_safety.main([str(skill)]) == 1
        assert "SKILL.md:5" in capsys.readouterr().out

    def test_nested_reference_is_scanned(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        skill = _make_skill(tmp_path, "nested-skill")
        nested = skill / "references" / "deep"
        nested.mkdir(parents=True)
        (nested / "doc.md").write_text(UNSAFE_DOC, encoding="utf-8")
        assert docs_safety.main([str(skill)]) == 1
        assert "doc.md" in capsys.readouterr().out

    def test_file_argument_still_works(self, tmp_path: Path):
        skill = _make_skill(tmp_path, "bad-skill", UNSAFE_DOC)
        assert docs_safety.main([str(skill / "SKILL.md")]) == 1
        safe = _make_skill(tmp_path, "good-skill")
        assert docs_safety.main([str(safe / "SKILL.md")]) == 0

    def test_missing_path_exits_2(self, tmp_path: Path):
        assert docs_safety.main([str(tmp_path / "nope.md")]) == 2

    def test_dir_without_markdown_exits_2(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        empty = tmp_path / "empty"
        empty.mkdir()
        assert docs_safety.main([str(empty)]) == 2
        assert "No markdown files" in capsys.readouterr().err

    def test_no_argument_scans_default_targets(self, capsys: pytest.CaptureFixture[str]):
        # The skill's own docs must be safe; also proves the default path still runs.
        assert docs_safety.main([]) == 0
        assert "3 files scanned" in capsys.readouterr().out


@pytest.mark.parametrize("script", ["quick_validate.py", "validate-skill.py"])
def test_sibling_validators_answer_help(script: str):
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_DIR / script), "--help"],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
        check=False,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "Exit codes" in result.stdout
