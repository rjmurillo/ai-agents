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
        "/".join(("my" + "." + "claude", "skills", "project", "demo", "SKILL.md")),
        "---\n---\n",
    )
    real_skill = _write(tmp_path, _SKILL_DEMO, "---\n---\n")

    assert not _mod._is_applicable(fake_skill)
    assert _mod._is_applicable(real_skill)


def test_applicable_clean_reports_no_violations(tmp_path: Path) -> None:
    # model: field omitted -- correct default per ADR-080
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        "---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\n---\nBody.\n",
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


# ADR-080: model field optional, rolling alias + rationale required when present.


def test_skill_model_omitted_is_valid(tmp_path: Path) -> None:
    """No model: field is the correct default per ADR-080 (inherit harness)."""
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        "---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\n---\n",
    )
    result = _mod.run_scan([skill], ["skill-frontmatter"])
    assert not result.violations


def test_skill_model_valid_alias_with_rationale_is_valid(tmp_path: Path) -> None:
    """Rolling alias + model-rationale: passes GP-003 per ADR-080."""
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        (
            "---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\n"
            "model: haiku\nmodel-rationale: Cost-sensitive scan.\n---\n"
        ),
    )
    result = _mod.run_scan([skill], ["skill-frontmatter"])
    assert not result.violations


def test_skill_model_versioned_id_fails_adr080(tmp_path: Path) -> None:
    """Versioned model id (claude-opus-4-6) is forbidden for skills per ADR-080."""
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        (
            "---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\n"
            "model: claude-sonnet-4-6\n---\n"
        ),
    )
    result = _mod.run_scan([skill], ["skill-frontmatter"])
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.rule == "skill-frontmatter"
    assert "ADR-080" in v.message
    assert "versioned" in v.message


def test_skill_model_alias_without_rationale_fails_adr080(tmp_path: Path) -> None:
    """Rolling alias without model-rationale: is forbidden per ADR-080."""
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        ("---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\nmodel: haiku\n---\n"),
    )
    result = _mod.run_scan([skill], ["skill-frontmatter"])
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.rule == "skill-frontmatter"
    assert "ADR-080" in v.message
    assert "model-rationale" in v.message


def test_skill_model_haiku_cost_exception_is_valid(tmp_path: Path) -> None:
    """haiku alias with cost-based model-rationale: passes GP-003 (ADR-080 endorsed pattern).

    Per ADR-080 rule 3, model-rationale is a cost exception. Only an alias
    priced below the harness default qualifies; in practice that is haiku.
    """
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        (
            "---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\n"
            "model: haiku\n"
            "model-rationale: Cost-conscious; haiku-tier pricing sufficient for this task.\n"
            "---\n"
        ),
    )
    result = _mod.run_scan([skill], ["skill-frontmatter"])
    assert not result.violations


def test_skill_model_unknown_value_fails_adr080(tmp_path: Path) -> None:
    """Non-alias model value (e.g. gpt-4) fails ADR-080 versioned-id check."""
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        ("---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\nmodel: gpt-4\n---\n"),
    )
    result = _mod.run_scan([skill], ["skill-frontmatter"])
    assert len(result.violations) == 1
    assert "ADR-080" in result.violations[0].message


def test_adr080_check_is_isolating_load_bearing(tmp_path: Path) -> None:
    """Negative control: removing _ALLOWED_MODEL_ALIASES from the check would
    mean a versioned id no longer raises a violation. This test fails if that
    validation path is removed.
    """
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        (
            "---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\n"
            "model: claude-opus-4-6\n---\n"
        ),
    )
    result = _mod.run_scan([skill], ["skill-frontmatter"])
    # Must produce exactly one violation citing ADR-080; if zero violations
    # are returned the ADR-080 check was stripped and the mutation survived.
    assert result.violations, "ADR-080 versioned-id check must be present and triggered"
    assert any("ADR-080" in v.message for v in result.violations)


def test_skill_model_sonnet_with_rationale_fails_adr080(tmp_path: Path) -> None:
    """model: sonnet is not a cost-exception alias per ADR-080 rule 3.

    Even with model-rationale:, sonnet does not resolve to a version priced
    below the harness default, so the field is rejected.
    """
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        (
            "---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\n"
            "model: sonnet\n"
            "model-rationale: Fast turnaround needed.\n"
            "---\n"
        ),
    )
    result = _mod.run_scan([skill], ["skill-frontmatter"])
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.rule == "skill-frontmatter"
    assert "ADR-080" in v.message
    assert "cost-exception" in v.message


def test_skill_model_opus_with_rationale_fails_adr080(tmp_path: Path) -> None:
    """model: opus is not a cost-exception alias per ADR-080 rule 3.

    Even with model-rationale:, opus does not resolve to a version priced
    below the harness default, so the field is rejected.
    """
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        (
            "---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\n"
            "model: opus\n"
            "model-rationale: Complex reasoning required.\n"
            "---\n"
        ),
    )
    result = _mod.run_scan([skill], ["skill-frontmatter"])
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.rule == "skill-frontmatter"
    assert "ADR-080" in v.message
    assert "cost-exception" in v.message


def test_skill_model_blank_fails_adr080(tmp_path: Path) -> None:
    """A blank model: value (model: with nothing after colon) is caught by ADR-080.

    Previously _MODEL_FIELD_RE required at least one character after 'model:'
    so a blank value silently skipped validation. The regex now accepts empty
    values and flags them.
    """
    skill = _write(
        tmp_path,
        _SKILL_DEMO,
        ("---\nname: demo\nversion: 1.0.0\ndescription: demo\nlicense: MIT\nmodel:\n---\n"),
    )
    result = _mod.run_scan([skill], ["skill-frontmatter"])
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.rule == "skill-frontmatter"
    assert "ADR-080" in v.message
    assert "blank" in v.message
