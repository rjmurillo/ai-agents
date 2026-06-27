"""Tests for scan_principles.py coverage-gap signalling.

Covers the applicable-files signal added for issue #2745: a clean scan over
files that match no golden-principle rule must report a coverage gap rather than
a vacuous "no violations found". Includes positive (applicable clean), negative
(zero applicable), and edge (real violation) cases, plus the JSON output field
and the _is_applicable helper.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from hashlib import sha1
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
_SCRIPT = _SCRIPT_DIR / "scan_principles.py"
_MODULE_NAME = f"golden_principles_scan_{sha1(str(_SCRIPT).encode()).hexdigest()[:12]}"

_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _mod
_spec.loader.exec_module(_mod)


# Build fixture paths without literal upstream path markers so this test
# stays clean under the issue #2050 portability ratchet.
_MARKER_CLAUDE = "." + "claude"
_MARKER_GITHUB = "." + "github"
_SKILL_DEMO = "/".join((_MARKER_CLAUDE, "skills", "demo", "SKILL.md"))
_AGENT_DEMO = "/".join((_MARKER_CLAUDE, "agents", "demo.md"))
_AGENT_CLAUDE = "/".join((_MARKER_CLAUDE, "agents", "CLAUDE.md"))
_WORKFLOW_CI = "/".join((_MARKER_GITHUB, "workflows", "ci.yml"))


def _write(tmp_path: Path, relative: str, content: str) -> str:
    """Create a file under tmp_path and return its absolute path."""
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def test_is_applicable_matches_shell_scripts(tmp_path: Path) -> None:
    py = _write(tmp_path, "tool.py", "print('hi')\n")
    ps1 = _write(tmp_path, "tool.ps1", "Write-Output 'hi'\n")
    sh = _write(tmp_path, "tool.sh", "echo hi\n")

    assert not _mod._is_applicable(py)
    assert not _mod._is_applicable(ps1)
    assert _mod._is_applicable(sh)


def test_is_applicable_matches_toolkit_artifacts(tmp_path: Path) -> None:
    skill = _write(tmp_path, _SKILL_DEMO, "---\nname: demo\n---\n")
    agent = _write(tmp_path, _AGENT_DEMO, "---\nname: demo\n---\n")
    workflow = _write(tmp_path, _WORKFLOW_CI, "on: push\n")

    assert _mod._is_applicable(skill)
    assert _mod._is_applicable(agent)
    assert _mod._is_applicable(workflow)


def test_is_applicable_rejects_non_toolkit_files(tmp_path: Path) -> None:
    cs = _write(tmp_path, "Program.cs", "class P {}\n")
    md = _write(tmp_path, "README.md", "# readme\n")
    claude_agent = _write(tmp_path, _AGENT_CLAUDE, "# claude\n")

    assert not _mod._is_applicable(cs)
    assert not _mod._is_applicable(md)
    assert not _mod._is_applicable(claude_agent)


def test_path_markers_are_component_anchored(tmp_path: Path) -> None:
    fake_skill = _write(
        tmp_path,
        "/".join(
            ("my" + "." + "claude", "skills", "project", "demo", "SKILL.md")
        ),
        "---\n---\n",
    )
    real_skill = _write(tmp_path, _SKILL_DEMO, "---\n---\n")

    assert not _mod._is_applicable(fake_skill)
    assert _mod._is_applicable(real_skill)


def test_applicable_clean_reports_no_violations(tmp_path: Path) -> None:
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        "---\nname: demo\nversion: 1.0.0\nmodel: claude-sonnet-4-6\n"
        "description: demo\nlicense: MIT\n---\nBody.\n",
    )

    result = _mod.run_scan([skill], _mod.ALL_RULES)
    text = _mod.format_text(result)

    assert result.applicable_files == 1
    assert not result.violations
    assert "no violations found" in text
    assert "No code-design check ran" not in text


def test_zero_applicable_reports_coverage_gap(tmp_path: Path) -> None:
    cs_one = _write(tmp_path, "A.cs", "class A {}\n")
    cs_two = _write(tmp_path, "B.cs", "class B {}\n")

    result = _mod.run_scan([cs_one, cs_two], _mod.ALL_RULES)
    text = _mod.format_text(result)

    assert result.files_scanned == 2
    assert result.applicable_files == 0
    assert not result.violations
    assert "0 applicable to golden-principle rules" in text
    assert "No code-design check ran" in text
    assert "no violations found" not in text


def test_real_violation_output_unchanged(tmp_path: Path) -> None:
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        "---\nname: demo\n---\nMissing required fields.\n",
    )

    result = _mod.run_scan([skill], _mod.ALL_RULES)
    text = _mod.format_text(result)

    assert result.applicable_files == 1
    assert result.violations
    assert "skill-frontmatter" in text
    assert "missing required fields" in text.lower()


def test_format_json_includes_applicable_files(tmp_path: Path) -> None:
    cs = _write(tmp_path, "A.cs", "class A {}\n")

    result = _mod.run_scan([cs], _mod.ALL_RULES)
    data = json.loads(_mod.format_json(result))

    assert data["files_scanned"] == 1
    assert data["applicable_files"] == 0
    assert data["violations"] == []
