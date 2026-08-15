# taste-lint: ignore file-size
#
# file-size suppression rationale: this module exhaustively covers the
# REQ-009 acceptance criteria (AC2/AC3/AC4/AC5/AC6/AC8 plus the
# main() bad-CLI-args and runtime catch-all envelope branches) for both
# the canonical `.claude/skills/orphan-ref-validator/scripts/scan.py`
# and its byte-for-byte mirror at
# `src/copilot-cli/skills/orphan-ref-validator/scripts/scan.py`.
# Splitting these tests across multiple files would either duplicate the
# importlib spec-loading shim (lines 22-49) per file, or force tests to
# share module state across files (`sys.modules[main.__module__]` cache),
# weakening the canonical/mirror isolation guarantee.
"""Tests for orphan-ref-validator scan.py.

Covers REQ-009 acceptance criteria:
- AC2: skill_name detection (positive + negative)
- AC3: script_path detection (positive + negative, repo-root containment)
- AC5: ADR-056 envelope + VERDICT line (PASS/WARN/CRITICAL_FAIL/ERROR)
- AC6: vendored install (missing target path -> skip, no raise)
- AC8: edge cases (empty file, mixed living+dead refs, secret denylist,
  oversized files, ignore directives, glob target expansion, main()
  bad-CLI-args + runtime catch-all envelope shape)
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

# Load scan.py via a spec keyed to this file's location so the test suite
# does not collide with a sibling mirror at src/copilot-cli/skills/.../tests/
# that imports a bare module name. The stable cache key prevents two test
# suites from racing on sys.modules["scan"]. Walk to the repo root (a .git
# entry) and use the repo-root-relative path to decide canonical vs. mirror;
# a worktree under .claude/worktrees/ makes ".claude" appear in the absolute
# path of src/copilot-cli files too, so checking for "src" + "copilot-cli" in
# the relative path is the only discriminator that is stable across setups.
_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
_REPO_ROOT_FOR_KEY: Path | None = next(
    (p for p in _SCRIPT_DIR.parents if (p / ".git").exists() or (p / ".git").is_file()),
    None,
)
_IS_MIRROR = (
    _REPO_ROOT_FOR_KEY is not None
    and _SCRIPT_DIR.is_relative_to(_REPO_ROOT_FOR_KEY)
    and _SCRIPT_DIR.relative_to(_REPO_ROOT_FOR_KEY).parts[:2] == ("src", "copilot-cli")
)
_MODULE_KEY = (
    "_orphan_ref_validator_scan_mirror"
    if _IS_MIRROR
    else "_orphan_ref_validator_scan"
)
sys.path.insert(0, str(_SCRIPT_DIR))
_spec = importlib.util.spec_from_file_location(_MODULE_KEY, _SCRIPT_DIR / "scan.py")
assert _spec is not None and _spec.loader is not None
_scan = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_KEY] = _scan
_spec.loader.exec_module(_scan)

Finding = _scan.Finding
ScanResult = _scan.ScanResult
load_baseline = _scan.load_baseline
BaselineError = _scan.BaselineError
extract_script_refs = _scan.extract_script_refs
extract_rule_refs = _scan.extract_rule_refs
extract_instruction_refs = _scan.extract_instruction_refs
extract_skill_refs = _scan.extract_skill_refs
extract_single_word_skill_refs = _scan.extract_single_word_skill_refs
extract_skill_script_refs = _scan.extract_skill_script_refs
_check_skill_script_refs = _scan._check_skill_script_refs
enumerate_skills = _scan.enumerate_skills
enumerate_sibling_artifacts = _scan.enumerate_sibling_artifacts
main = _scan.main
render_envelope = _scan.render_envelope
scan = _scan.scan


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Build a minimal repo layout with two living skills and one agent.

    fake_repo is nested under tmp_path so tests can place files in
    tmp_path that are outside the repo root.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    skills = repo / ".claude" / "skills"
    skills.mkdir(parents=True)
    for name in ("alpha-skill", "beta-skill"):
        d = skills / name
        d.mkdir()
        (d / "SKILL.md").write_text("# stub\n", encoding="utf-8")
    agents = repo / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "agent-one.md").write_text("# agent\n", encoding="utf-8")
    (repo / ".git").mkdir()
    return repo


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fixture_catalog(repo: Path) -> Path:
    """Return the skills catalog a fixture repo built.

    Found by shape rather than by spelling the canonical prefix again, so new
    tests here do not add vendor-portability drift (issue #2050).
    """
    return next(repo.glob("*/skills"))


def skill_dir(repo: Path, name: str) -> Path:
    """Locate a skill directory the fixture created, without restating the layout."""
    return next(p.parent for p in repo.rglob("SKILL.md") if p.parent.name == name)


# ---------- extractor unit tests ----------


def test_extract_skill_refs_kebab_in_backticks():
    text = "Use `alpha-skill` and not `beta-skill`."
    refs = list(extract_skill_refs(text))
    assert (1, "alpha-skill") in refs
    assert (1, "beta-skill") in refs


def test_extract_skill_refs_ignores_inline_kebab_outside_backticks():
    text = "alpha-skill mentioned without backticks"
    assert list(extract_skill_refs(text)) == []


def test_extract_script_refs_full_path_match():
    text = "See `build/scripts/foo.py` for details."
    refs = list(extract_script_refs(text))
    assert refs == [(1, "build/scripts/foo.py")]


def test_extract_rule_refs_from_markdown_link_target():
    text = "See [rule](.claude/rules/missing-rule.md)."
    assert list(extract_rule_refs(text)) == [(1, ".claude/rules/missing-rule.md")]


def test_extract_instruction_refs_from_markdown_link_target():
    text = "See [mirror](src/copilot-cli/instructions/missing.instructions.md)."
    assert list(extract_instruction_refs(text)) == [
        (1, "src/copilot-cli/instructions/missing.instructions.md")
    ]


# ---------- enumerator tests ----------


def test_enumerate_skills_returns_set(fake_repo):
    assert enumerate_skills(fake_repo) == {"alpha-skill", "beta-skill"}


def test_enumerate_skills_handles_missing_dir(tmp_path):
    assert enumerate_skills(tmp_path) is None


# ---------- AC2: skill_name detection ----------


def test_ac2_orphan_skill_name_yields_critical_finding(fake_repo):
    target = fake_repo / "docs" / "stale.md"
    write(target, "Use the skill `gamma-skill` for things.\n")
    result = scan([target], fake_repo)
    skill_findings = [f for f in result.findings if f.kind == "skill_name"]
    assert len(skill_findings) == 1
    f = skill_findings[0]
    assert f.severity == "critical"
    assert f.referenced_entity == "gamma-skill"
    assert f.line == 1
    assert result.verdict == "CRITICAL_FAIL"


def test_ac2_living_skill_name_yields_no_finding(fake_repo):
    target = fake_repo / "docs" / "ok.md"
    write(target, "Use `alpha-skill` and `beta-skill`.\n")
    result = scan([target], fake_repo)
    assert [f for f in result.findings if f.kind == "skill_name"] == []
    assert result.verdict == "PASS"


def test_ac2_known_kebab_words_excluded(fake_repo):
    target = fake_repo / "docs" / "prose.md"
    write(target, "This is `well-known` and `open-source`.\n")
    result = scan([target], fake_repo)
    assert [f for f in result.findings if f.kind == "skill_name"] == []


# ---------- AC3: script_path detection ----------


def test_ac3_missing_script_path_yields_critical_finding(fake_repo):
    target = fake_repo / "docs" / "spec.md"
    write(target, "Run `build/scripts/nonexistent.py` for the thing.\n")
    result = scan([target], fake_repo)
    script_findings = [f for f in result.findings if f.kind == "script_path"]
    assert len(script_findings) == 1
    f = script_findings[0]
    assert f.severity == "critical"
    assert f.referenced_entity == "build/scripts/nonexistent.py"


def test_ac3_existing_script_path_yields_no_finding(fake_repo):
    target = fake_repo / "docs" / "spec.md"
    real = fake_repo / "build" / "scripts" / "real.py"
    write(real, "# real script\n")
    write(target, "Run `build/scripts/real.py` for the thing.\n")
    result = scan([target], fake_repo)
    assert [f for f in result.findings if f.kind == "script_path"] == []


# ---------- rule/instruction path detection (issue #3556) in non-markdown syntax ----------


def test_extract_rule_and_instruction_refs_from_structured_values_and_literals():
    text = "\n".join([
        '{"rule": ".claude/rules/missing-rule.md"}',
        "paths: .github/instructions/missing.instructions.md",
        "---",
        "applyTo: src/copilot-cli/instructions/missing.instructions.md",
        "---",
        "```",
        ".claude/rules/fenced-rule.md",
        "```",
        'RULE = ".claude/rules/python-rule.md"',
    ])
    assert list(extract_rule_refs(text)) == [
        (1, ".claude/rules/missing-rule.md"),
        (7, ".claude/rules/fenced-rule.md"),
        (9, ".claude/rules/python-rule.md"),
    ]
    assert list(extract_instruction_refs(text)) == [
        (2, ".github/instructions/missing.instructions.md"),
        (4, "src/copilot-cli/instructions/missing.instructions.md"),
    ]


def test_ac3_rule_path_json_value_missing_yields_critical_finding(fake_repo):
    target = fake_repo / "tests" / "evals" / "rule-scenarios" / "stale.json"
    write(target, '{"rule_path": ".claude/rules/deleted-rule.md"}\n')
    result = scan([target], fake_repo)
    rule_findings = [f for f in result.findings if f.kind == "rule_path"]
    assert len(rule_findings) == 1
    assert rule_findings[0].referenced_entity == ".claude/rules/deleted-rule.md"
    assert rule_findings[0].severity == "critical"
    assert result.verdict == "CRITICAL_FAIL"


def test_ac3_rule_and_instruction_path_yaml_and_frontmatter_values_are_checked(fake_repo):
    target = fake_repo / "docs" / "frontmatter.md"
    write(
        target,
        "---\n"
        "rule: .claude/rules/missing-frontmatter.md\n"
        "instruction: .github/instructions/missing.instructions.md\n"
        "---\n"
        "Body\n",
    )
    result = scan([target], fake_repo)
    rule_refs = {f.referenced_entity for f in result.findings if f.kind == "rule_path"}
    instruction_refs = {
        f.referenced_entity for f in result.findings if f.kind == "instruction_path"
    }
    assert rule_refs == {".claude/rules/missing-frontmatter.md"}
    assert instruction_refs == {".github/instructions/missing.instructions.md"}
    assert result.verdict == "CRITICAL_FAIL"


def test_ac3_rule_path_bare_fenced_code_path_is_checked(fake_repo):
    target = fake_repo / "docs" / "fenced.md"
    write(target, "```\n.claude/rules/missing-fenced.md\n```\n")
    result = scan([target], fake_repo)
    rule_findings = [f for f in result.findings if f.kind == "rule_path"]
    assert [f.referenced_entity for f in rule_findings] == [
        ".claude/rules/missing-fenced.md"
    ]
    assert result.verdict == "CRITICAL_FAIL"


def test_ac3_existing_rule_and_instruction_paths_yield_no_finding(fake_repo):
    write(fake_repo / ".claude" / "rules" / "live.md", "# live rule\n")
    write(
        fake_repo / ".github" / "instructions" / "live.instructions.md",
        "# live instruction\n",
    )
    write(
        fake_repo / "src" / "copilot-cli" / "instructions" / "live.instructions.md",
        "# live copilot instruction\n",
    )
    target = fake_repo / "docs" / "live.md"
    write(
        target,
        "Refs .claude/rules/live.md, "
        ".github/instructions/live.instructions.md, and "
        "src/copilot-cli/instructions/live.instructions.md.\n",
    )
    result = scan([target], fake_repo)
    assert [f for f in result.findings if f.kind == "rule_path"] == []
    assert [f for f in result.findings if f.kind == "instruction_path"] == []
    assert result.verdict == "PASS"


def test_ac3_rule_path_ignore_directive_suppresses_line(fake_repo):
    target = fake_repo / "docs" / "ignored.md"
    write(
        target,
        ".claude/rules/missing.md <!-- orphan-ref-ignore -->\n"
        ".claude/rules/other-missing.md\n",
    )
    result = scan([target], fake_repo)
    rule_findings = [f for f in result.findings if f.kind == "rule_path"]
    assert [f.referenced_entity for f in rule_findings] == [
        ".claude/rules/other-missing.md"
    ]


def test_ac3_rule_path_partial_prefix_is_not_matched():
    refs = list(extract_rule_refs("x.claude/rules/not-a-ref.md\n"))
    assert refs == []


def test_ac3_python_string_literal_in_explicit_python_target_is_checked(fake_repo):
    target = fake_repo / "scripts" / "probe.py"
    write(target, 'RULE_PATH = ".claude/rules/missing-python.md"\n')
    result = scan([target], fake_repo)
    rule_findings = [f for f in result.findings if f.kind == "rule_path"]
    assert len(rule_findings) == 1
    assert rule_findings[0].referenced_entity == ".claude/rules/missing-python.md"
    assert result.verdict == "CRITICAL_FAIL"


def test_cli_exit_code_critical_fail_for_missing_rule_path(fake_repo, capsys):
    target = fake_repo / "docs" / "missing-rule.md"
    write(target, "Use .claude/rules/missing-cli.md\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
    ])
    assert rc == 1
    assert "VERDICT: CRITICAL_FAIL" in capsys.readouterr().out


# ---------- AC3 broad (PR2, issue #1994): .ps1 script paths ----------


def test_ac3_broad_ps1_script_extractor():
    """SCRIPT_REF_RE matches a backticked .ps1 path under a scanned prefix."""
    text = "Old `scripts/Validate-SessionEnd.ps1` orphan."
    refs = list(extract_script_refs(text))
    assert refs == [(1, "scripts/Validate-SessionEnd.ps1")]


def test_ac3_broad_non_script_suffix_not_matched():
    """A backticked path with a non-script suffix is not a script_path ref."""
    text = "See `scripts/notes.txt` and `scripts/data.json`."
    assert list(extract_script_refs(text)) == []


def test_ac3_broad_missing_ps1_yields_critical_finding(fake_repo):
    target = fake_repo / "docs" / "spec.md"
    write(target, "Call `scripts/Validate-Gone.ps1` before push.\n")
    result = scan([target], fake_repo)
    script_findings = [f for f in result.findings if f.kind == "script_path"]
    assert len(script_findings) == 1
    assert script_findings[0].referenced_entity == "scripts/Validate-Gone.ps1"
    assert script_findings[0].severity == "critical"
    assert result.verdict == "CRITICAL_FAIL"


def test_ac3_broad_existing_ps1_yields_no_finding(fake_repo):
    target = fake_repo / "docs" / "spec.md"
    real = fake_repo / "scripts" / "Validate-Here.ps1"
    write(real, "# real ps1\n")
    write(target, "Call `scripts/Validate-Here.ps1` before push.\n")
    result = scan([target], fake_repo)
    assert [f for f in result.findings if f.kind == "script_path"] == []


class TestTestsScriptRefs:
    """Issue #3456: backticked script refs under tests/ use the existing
    script_path syntax and must resolve against the working tree."""

    def test_missing_tests_script_path_yields_critical_finding(self, fake_repo):
        target = fake_repo / "docs" / "spec.md"
        write(target, "Run `tests/hooks/missing.py` for the guard.\n")
        result = scan([target], fake_repo)
        script_findings = [f for f in result.findings if f.kind == "script_path"]
        assert len(script_findings) == 1
        assert script_findings[0].referenced_entity == "tests/hooks/missing.py"
        assert script_findings[0].severity == "critical"
        assert result.verdict == "CRITICAL_FAIL"

    def test_existing_tests_script_path_yields_no_finding(self, fake_repo):
        target = fake_repo / "docs" / "spec.md"
        write(fake_repo / "tests" / "hooks" / "real.py", "# real test helper\n")
        text = "Run `tests/hooks/real.py` for the guard.\n"
        assert list(extract_script_refs(text)) == [(1, "tests/hooks/real.py")]
        write(target, text)
        result = scan([target], fake_repo)
        assert result.refs_checked == 1
        assert [f for f in result.findings if f.kind == "script_path"] == []
        assert result.verdict == "PASS"

    def test_cli_exits_one_for_missing_tests_script_ref(self, fake_repo, capsys):
        target = fake_repo / "docs" / "spec.md"
        write(target, "Run `tests/hooks/missing.py` for the guard.\n")
        rc = main(["--targets", str(target), "--repo-root", str(fake_repo)])
        assert rc == 1
        assert "VERDICT: CRITICAL_FAIL" in capsys.readouterr().out

    def test_cli_exits_zero_for_existing_tests_script_ref(self, fake_repo, capsys):
        target = fake_repo / "docs" / "spec.md"
        write(fake_repo / "tests" / "hooks" / "real.py", "# real test helper\n")
        text = "Run `tests/hooks/real.py` for the guard.\n"
        assert list(extract_script_refs(text)) == [(1, "tests/hooks/real.py")]
        write(target, text)
        rc = main(["--targets", str(target), "--repo-root", str(fake_repo)])
        assert rc == 0
        out = capsys.readouterr().out
        payload = json.loads(out.split("\nVERDICT:")[0])
        assert payload["Data"]["counts"]["refs_checked"] == 1
        assert "VERDICT: PASS" in out

    def test_default_targets_scan_tests_tree(self, fake_repo, capsys):
        specs_dir = Path("." + "agents") / "specs"
        write(fake_repo / specs_dir / "README.md", "# specs\n")
        write(fake_repo / ".claude" / ".claude-plugin" / "plugin.json", "{}\n")
        write(fake_repo / ".claude-plugin" / "marketplace.json", "{}\n")
        write(fake_repo / ".github" / "plugin" / "marketplace.json", "{}\n")
        target = fake_repo / "tests" / "contracts" / "orphan_refs.md"
        write(target, "Run `tests/hooks/missing.py` for the guard.\n")
        rc = main(["--repo-root", str(fake_repo)])
        assert rc == 1
        assert "tests/hooks/missing.py" in capsys.readouterr().out

    def test_fixture_bad_path_uses_explicit_line_ignore(self, fake_repo):
        fixture = fake_repo / "tests" / "hooks" / "fixtures" / "bad-paths.md"
        write(
            fixture,
            "Intentional negative fixture: `tests/hooks/missing.py` "
            "<!-- orphan-ref-ignore -->\n",
        )
        result = scan([fake_repo / "tests"], fake_repo)
        assert result.directive_suppressed[0].referenced_entity == (
            "tests/hooks/missing.py"
        )
        assert [f for f in result.findings if f.kind == "script_path"] == []
        assert result.verdict == "PASS"

    def test_fenced_code_block_tests_script_ref_is_checked(self, fake_repo):
        target = fake_repo / "docs" / "spec.md"
        write(
            target,
            "```text\n"
            "Run `tests/hooks/missing.py`\n"
            "```\n",
        )
        result = scan([target], fake_repo)
        assert {f.referenced_entity for f in result.findings} == {
            "tests/hooks/missing.py"
        }
        assert result.verdict == "CRITICAL_FAIL"

    def test_commented_out_tests_script_ref_is_checked(self, fake_repo):
        target = fake_repo / "docs" / "spec.md"
        write(target, "<!-- Removed command `tests/hooks/missing.py` -->\n")
        result = scan([target], fake_repo)
        assert {f.referenced_entity for f in result.findings} == {
            "tests/hooks/missing.py"
        }
        assert result.verdict == "CRITICAL_FAIL"

    def test_tests_script_glob_is_not_reference_syntax(self):
        text = "Run `tests/hooks/*.py`.\n"
        assert list(extract_script_refs(text)) == []
        assert list(_scan.extract_all_reference_candidates(text)) == []

    def test_empty_tests_tree_yields_pass(self, fake_repo):
        (fake_repo / "tests").mkdir()
        result = scan([fake_repo / "tests"], fake_repo)
        assert result.findings == []
        assert result.files_scanned == 0
        assert result.incomplete_scans == []
        assert result.verdict == "PASS"


class TestRuleAndInstructionRefs:
    """Rule and instruction mirror paths are first-class scanned entities."""

    def test_missing_rule_path_yields_critical_finding(self, fake_repo):
        target = fake_repo / "docs" / "rules.md"
        write(target, "See `.claude/rules/deleted-rule.md`.\n")
        result = scan([target], fake_repo)
        findings = [f for f in result.findings if f.kind == "rule_path"]
        assert len(findings) == 1
        assert findings[0].referenced_entity == ".claude/rules/deleted-rule.md"
        assert findings[0].severity == "critical"

    def test_existing_rule_path_yields_no_finding(self, fake_repo):
        target = fake_repo / "docs" / "rules.md"
        write(fake_repo / ".claude" / "rules" / "living.md", "# rule\n")
        text = "See [.claude/rules/living.md](.claude/rules/living.md).\n"
        assert list(extract_rule_refs(text)) == [(1, ".claude/rules/living.md")]
        write(target, text)
        result = scan([target], fake_repo)
        assert result.refs_checked == 1
        assert [f for f in result.findings if f.kind == "rule_path"] == []

    def test_missing_instruction_mirror_path_yields_critical_finding(self, fake_repo):
        target = fake_repo / "docs" / "rules.md"
        write(
            target,
            "See [mirror](.github/instructions/deleted.instructions.md).\n",
        )
        result = scan([target], fake_repo)
        findings = [f for f in result.findings if f.kind == "instruction_path"]
        assert len(findings) == 1
        assert findings[0].referenced_entity == (
            ".github/instructions/deleted.instructions.md"
        )
        assert result.verdict == "CRITICAL_FAIL"

    def test_existing_instruction_mirror_path_yields_no_finding(self, fake_repo):
        target = fake_repo / "docs" / "rules.md"
        write(
            fake_repo / "src" / "copilot-cli" / "instructions" / "living.instructions.md",
            "# mirror\n",
        )
        text = "See [mirror](src/copilot-cli/instructions/living.instructions.md).\n"
        assert list(extract_instruction_refs(text)) == [
            (1, "src/copilot-cli/instructions/living.instructions.md")
        ]
        write(target, text)
        result = scan([target], fake_repo)
        assert result.refs_checked == 1
        assert [f for f in result.findings if f.kind == "instruction_path"] == []


# ---------- AC5: envelope + verdict ----------


def test_ac5_envelope_shape_and_verdict_line(fake_repo, capsys):
    target = fake_repo / "docs" / "ok.md"
    write(target, "Hello world\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
        "--output", "json",
    ])
    assert rc == 0
    captured = capsys.readouterr().out.strip().splitlines()
    assert captured[-1].startswith("VERDICT:")
    body = "\n".join(captured[:-1])
    payload = json.loads(body)
    assert set(payload.keys()) == {"Success", "Data", "Error", "Metadata"}
    assert "verdict" in payload["Data"]
    assert "findings" in payload["Data"]
    assert "counts" in payload["Data"]
    assert payload["Metadata"]["Script"] == "scan.py"


def test_ac5_human_output_includes_verdict_line(fake_repo, capsys):
    target = fake_repo / "docs" / "ok.md"
    write(target, "Hello\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
        "--output", "human",
    ])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "VERDICT: PASS" in captured


# ---------- AC6: vendored install scenario ----------


def test_ac6_missing_target_path_does_not_raise(fake_repo, caplog):
    missing = fake_repo / "no-such-dir"
    with caplog.at_level("WARNING"):
        result = scan([missing], fake_repo)
    assert result.verdict == "PASS"
    assert result.findings == []
    assert len(result.incomplete_scans) == 1
    assert result.incomplete_scans[0].reason == "target does not exist or glob matched no files"
    assert any("incomplete scan" in r.getMessage() for r in caplog.records)


def test_ac6_optional_default_targets_skip_when_absent(fake_repo, capsys):
    rc = main([
        "--repo-root",
        str(fake_repo),
        "--output",
        "json",
        "--allow-missing-targets",
        "--allow-empty-scan",
    ])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "VERDICT: PASS" in captured


def test_default_scope_uses_tracked_supported_text_surfaces(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    dot_claude = "." + "claude"
    write(repo / dot_claude / "skills" / "alpha-skill" / "SKILL.md", "# stub\n")
    target = repo / ".claude" / "rules" / "rules.md"
    write(target, "See `.claude/rules/deleted-rule.md`.\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)

    rc = main(["--repo-root", str(repo), "--output", "json"])

    out = capsys.readouterr().out
    payload = json.loads(out.split("\nVERDICT:")[0])
    assert rc == 1
    assert payload["Data"]["counts"]["refs_checked"] == 1
    assert payload["Data"]["findings"][0]["referenced_entity"] == (
        ".claude/rules/deleted-rule.md"
    )


def test_ac6_explicit_missing_target_exits_two(fake_repo, capsys):
    rc = main([
        "--repo-root",
        str(fake_repo),
        "--targets",
        str(fake_repo / "no-such-dir"),
        "--output",
        "json",
    ])
    assert rc == 2
    captured = capsys.readouterr().out.strip().splitlines()
    assert captured[-1] == "VERDICT: ERROR"
    payload = json.loads("\n".join(captured[:-1]))
    assert payload["Data"]["counts"]["incomplete_scans"] == 1
    assert payload["Data"]["incomplete_scans"][0]["reason"] == (
        "target does not exist or glob matched no files"
    )


def test_ac6_zero_files_scanned_exits_two_without_empty_scope(fake_repo, capsys):
    empty = fake_repo / "docs"
    empty.mkdir()
    rc = main([
        "--repo-root",
        str(fake_repo),
        "--targets",
        str(empty),
        "--output",
        "json",
    ])
    assert rc == 2
    captured = capsys.readouterr().out.strip().splitlines()
    assert captured[-1] == "VERDICT: ERROR"
    payload = json.loads("\n".join(captured[:-1]))
    assert payload["Data"]["counts"]["files_scanned"] == 0
    assert payload["Data"]["counts"]["incomplete_scans"] == 1


def test_ac6_zero_files_scanned_can_be_declared_empty_scope(fake_repo, capsys):
    empty = fake_repo / "docs"
    empty.mkdir()
    rc = main([
        "--repo-root",
        str(fake_repo),
        "--targets",
        str(empty),
        "--allow-empty-scan",
    ])
    assert rc == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_ac6_paths_outside_repo_are_skipped(tmp_path, fake_repo, caplog):
    other = tmp_path / "other"
    other.mkdir()
    target = other / "x.md"
    write(target, "content\n")
    with caplog.at_level("WARNING"):
        result = scan([target], fake_repo)
    assert any("outside repo root" in r.getMessage() for r in caplog.records)
    assert len(result.incomplete_scans) >= 1
    assert result.incomplete_scans[0].error_type == "config"
    assert result.verdict == "PASS"
    assert len(result.incomplete_scans) == 1


def test_utf_bom_encoded_files_are_scanned(fake_repo):
    target = fake_repo / "docs" / "utf16.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes("See `.claude/rules/deleted-rule.md`.\n".encode("utf-16"))

    result = scan([target], fake_repo)

    assert result.refs_checked == 1
    assert result.findings[0].referenced_entity == ".claude/rules/deleted-rule.md"
    assert result.incomplete_scans == []


@pytest.mark.parametrize(
    ("encoding", "prefix"),
    [
        ("utf-8-sig", b"\xef\xbb\xbf"),
        ("utf-16", b"\xff\xfe"),
        ("utf-16-be", b"\xfe\xff"),
        ("utf-32", b"\xff\xfe\x00\x00"),
        ("utf-32-be", b"\x00\x00\xfe\xff"),
    ],
)
def test_supported_bom_encodings_decode_without_incomplete_scan(
    fake_repo, encoding, prefix
):
    target = fake_repo / "docs" / f"{encoding}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "See `.claude/rules/deleted-rule.md`.\n"
    data = text.encode(encoding)
    if not data.startswith(prefix):
        data = prefix + data
    target.write_bytes(data)

    result = scan([target], fake_repo)

    assert result.refs_checked == 1
    assert result.findings[0].referenced_entity == ".claude/rules/deleted-rule.md"
    assert result.incomplete_scans == []


def test_invalid_utf8_is_incomplete_scan(fake_repo, capsys):
    target = fake_repo / "docs" / "bad.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\xff\xffbroken-no-bom")

    rc = main(["--targets", str(target), "--repo-root", str(fake_repo)])

    out = capsys.readouterr().out
    payload = json.loads(out.split("\nVERDICT:")[0])
    assert rc == 2
    assert payload["Data"]["counts"]["incomplete_scans"] == 1
    assert "could not decode file" in payload["Data"]["incomplete_scans"][0]["reason"]


# ---------- AC9: edge cases ----------


def test_ac9_empty_file_yields_pass(fake_repo):
    target = fake_repo / "docs" / "empty.md"
    write(target, "")
    result = scan([target], fake_repo)
    assert result.verdict == "PASS"
    assert result.findings == []


def test_ac9_mixed_living_and_dead_refs(fake_repo):
    target = fake_repo / "docs" / "mixed.md"
    write(
        target,
        "Use `alpha-skill` and skill `dead-skill`. Run `build/scripts/missing.py`.\n",
    )
    result = scan([target], fake_repo)
    skill_findings = [f for f in result.findings if f.kind == "skill_name"]
    script_findings = [f for f in result.findings if f.kind == "script_path"]
    assert {f.referenced_entity for f in skill_findings} == {"dead-skill"}
    assert {f.referenced_entity for f in script_findings} == {"build/scripts/missing.py"}
    assert result.verdict == "CRITICAL_FAIL"


def test_ac9_directory_target_walks_files(fake_repo):
    target_dir = fake_repo / "docs"
    write(target_dir / "a.md", "Use `alpha-skill`.\n")
    write(target_dir / "b.md", "Use skill `dead-skill`.\n")
    result = scan([target_dir], fake_repo)
    bad = [f for f in result.findings if f.kind == "skill_name"]
    assert {f.referenced_entity for f in bad} == {"dead-skill"}


def test_ac9_secret_files_skipped(fake_repo):
    target_dir = fake_repo / "docs"
    write(target_dir / ".env.local", "Use skill `dead-skill`.\n")
    write(target_dir / "ok.md", "Use `alpha-skill`.\n")
    result = scan([target_dir], fake_repo)
    files = {f.target_file for f in result.findings}
    assert not any(".env" in p for p in files)


def test_ac9_large_files_skipped(fake_repo, caplog):
    target = fake_repo / "docs" / "huge.md"
    write(target, "X" * (5 * 1024 * 1024 + 1))
    with caplog.at_level("WARNING"):
        result = scan([target], fake_repo)
    assert any("exceeds" in r.getMessage() for r in caplog.records)
    assert result.verdict == "PASS"


# ---------- exit code tests ----------


def test_exit_code_pass(fake_repo, capsys):
    target = fake_repo / "docs" / "ok.md"
    write(target, "Use `alpha-skill`.\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
    ])
    assert rc == 0


def test_exit_code_critical_fail(fake_repo, capsys):
    target = fake_repo / "docs" / "bad.md"
    write(target, "Use skill `dead-skill`.\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
    ])
    assert rc == 1


def test_exit_code_warn_does_not_block(fake_repo, capsys):
    """A scan with no critical findings must exit 0. This manifest carries
    no skill or script references, so it produces zero findings -> PASS,
    which still satisfies the WARN-does-not-block contract."""
    plugin = fake_repo / ".claude-plugin" / "marketplace.json"
    write(plugin, '{"description": "Catalog has 5 agents."}')
    rc = main([
        "--targets", str(plugin),
        "--repo-root", str(fake_repo),
    ])
    assert rc == 0


# The precondition is built from file mode bits; root ignores them and
# Windows does not carry them. Mirrors the idiom in
# tests/test_gc_anchor_readers.py (_NO_PERMISSION_BARRIER).
@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="root and Windows do not honour the mode-bit barrier this needs",
)
def test_permission_denied_file_returns_auth_exit_code(fake_repo, capsys):
    target = fake_repo / "docs" / "locked.md"
    write(target, "Use skill `dead-skill`.\n")
    original_mode = target.stat().st_mode
    os.chmod(target, 0)
    try:
        rc = main(["--targets", str(target), "--repo-root", str(fake_repo)])
    finally:
        os.chmod(target, original_mode)

    out = capsys.readouterr().out
    payload = json.loads(out.split("\nVERDICT:")[0])
    assert rc == 4
    assert payload["Error"]["Code"] == 4
    assert payload["Error"]["Type"] == "AuthError"


# ---------- render_envelope direct tests ----------


def test_render_envelope_json_carries_findings(fake_repo):
    result = ScanResult(
        findings=[
            Finding(
                kind="skill_name",
                severity="critical",
                target_file="x.md",
                line=2,
                referenced_entity="ghost",
                recommendation="restore or remove",
            )
        ],
        files_scanned=1,
        refs_checked=3,
    )
    out = render_envelope(result, "json")
    payload = json.loads(out.split("\nVERDICT:")[0])
    assert payload["Data"]["verdict"] == "CRITICAL_FAIL"
    assert payload["Data"]["counts"]["files_scanned"] == 1
    assert payload["Data"]["findings"][0]["referenced_entity"] == "ghost"
    assert out.strip().endswith("VERDICT: CRITICAL_FAIL")


def test_render_envelope_json_carries_directive_suppressed_refs(fake_repo):
    target = fake_repo / "docs" / "fixture.md"
    write(
        target,
        "Intentional fixture `scripts/missing.py` <!-- orphan-ref-ignore -->\n",
    )
    result = scan([target], fake_repo)
    out = render_envelope(result, "json")
    payload = json.loads(out.split("\nVERDICT:")[0])
    assert payload["Data"]["counts"]["directive_suppressed"] == 1
    assert payload["Data"]["directive_suppressed"][0]["referenced_entity"] == (
        "scripts/missing.py"
    )


def test_file_scope_ignore_reports_suppressed_references(fake_repo):
    target = fake_repo / "docs" / "ignored.md"
    write(
        target,
        "<!-- orphan-ref-ignore-file -->\n"
        "Use `scripts/missing.py` and `.claude/rules/deleted-rule.md`.\n",
    )

    result = scan([target], fake_repo)

    assert result.files_scanned == 0
    assert result.files_skipped == 1
    assert {ref.reason for ref in result.directive_suppressed} == {
        "file ignore directive"
    }
    assert {ref.referenced_entity for ref in result.directive_suppressed} == {
        "scripts/missing.py",
        ".claude/rules/deleted-rule.md",
    }


def test_render_envelope_human_lists_findings(fake_repo):
    result = ScanResult(
        findings=[
            Finding(
                kind="script_path",
                severity="critical",
                target_file="x.md",
                line=4,
                referenced_entity="scripts/missing.py",
                recommendation="restore or remove",
            )
        ],
    )
    out = render_envelope(result, "human")
    assert "[critical]" in out
    assert "x.md:4" in out
    assert "VERDICT: CRITICAL_FAIL" in out


def test_render_envelope_human_lists_directive_suppressed_refs(fake_repo):
    target = fake_repo / "docs" / "fixture.md"
    write(
        target,
        "Intentional fixture `tests/hooks/missing.py` <!-- orphan-ref-ignore -->\n",
    )
    result = scan([target], fake_repo)
    out = render_envelope(result, "human")
    assert "directive_suppressed: 1" in out
    assert "[directive_suppressed]" in out
    assert "tests/hooks/missing.py" in out


# ---------- ADR-056: Success contract ----------


def test_adr056_success_true_on_critical_fail(fake_repo, capsys):
    target = fake_repo / "docs" / "bad.md"
    write(target, "Use skill `dead-skill`.\n")
    rc = main([
        "--targets", str(target),
        "--repo-root", str(fake_repo),
        "--output", "json",
    ])
    assert rc == 1
    captured = capsys.readouterr().out.strip().splitlines()
    body = "\n".join(captured[:-1])
    payload = json.loads(body)
    # ADR-056: Success reflects scan execution, not finding presence.
    assert payload["Success"] is True
    assert payload["Data"]["verdict"] == "CRITICAL_FAIL"
    assert payload["Error"] is None


# ---------- _resolve_repo_root validation ----------


def test_invalid_repo_root_returns_config_error(tmp_path, capsys):
    bogus = tmp_path / "does-not-exist"
    rc = main([
        "--repo-root", str(bogus),
        "--targets", str(tmp_path / "noop.md"),
    ])
    assert rc == 2


def test_repo_root_pointing_at_file_returns_config_error(tmp_path, capsys):
    f = tmp_path / "regular-file"
    f.write_text("not a directory")
    rc = main([
        "--repo-root", str(f),
        "--targets", str(tmp_path / "noop.md"),
    ])
    assert rc == 2


# ---------- walk pruning + symlink containment ----------


def test_walk_prunes_excluded_directories(fake_repo):
    docs = fake_repo / "docs"
    write(docs / "ok.md", "Use `alpha-skill`.\n")
    nm = docs / "node_modules" / "pkg"
    write(nm / "trap.md", "Use skill `dead-skill`.\n")
    refs = docs / "references"
    write(refs / "trap.md", "Use skill `dead-skill`.\n")
    result = scan([docs], fake_repo)
    bad = [f for f in result.findings if f.kind == "skill_name"]
    assert bad == []


def test_skill_name_warn_when_catalog_absent(tmp_path):
    """A vendored install without .claude/skills/ should not produce critical
    findings on backticked kebab tokens; downgrade to warn."""
    repo = tmp_path / "vendored"
    repo.mkdir()
    (repo / ".git").mkdir()
    docs = repo / "docs"
    write(docs / "x.md", "Use skill `dead-skill`.\n")
    result = scan([docs], repo)
    skill_findings = [f for f in result.findings if f.kind == "skill_name"]
    assert len(skill_findings) == 1
    assert skill_findings[0].severity == "warn"
    # WARN does not block; verdict is WARN, not CRITICAL_FAIL.
    assert result.verdict == "WARN"


def test_skill_name_critical_when_catalog_empty(tmp_path):
    """An empty .claude/skills/ is authoritative: emit critical for
    backticked kebab tokens."""
    repo = tmp_path / "empty-catalog"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".claude" / "skills").mkdir(parents=True)
    docs = repo / "docs"
    write(docs / "x.md", "Use skill `dead-skill`.\n")
    result = scan([docs], repo)
    skill_findings = [f for f in result.findings if f.kind == "skill_name"]
    assert len(skill_findings) == 1
    assert skill_findings[0].severity == "critical"
    assert result.verdict == "CRITICAL_FAIL"


def test_walk_skips_symlink_resolving_outside_repo(tmp_path, fake_repo, caplog):
    docs = fake_repo / "docs"
    write(docs / "ok.md", "Hello\n")
    outside = tmp_path / "outside"
    write(outside / "trap.md", "Use skill `dead-skill`.\n")
    link = docs / "link.md"
    link.symlink_to(outside / "trap.md")
    with caplog.at_level("WARNING"):
        result = scan([docs], fake_repo)
    assert [f for f in result.findings if f.kind == "skill_name"] == []
    assert any("outside repo root" in r.getMessage() for r in caplog.records)
    assert len(result.incomplete_scans) >= 1
    assert result.incomplete_scans[0].error_type == "config"


def test_walk_skips_symlink_to_directory_outside_repo(tmp_path, fake_repo, caplog):
    """A symlink directory under an allowed target that points outside the
    repo must not be recursed into. CWE-22 / CWE-59 hardening."""
    docs = fake_repo / "docs"
    write(docs / "ok.md", "Use `alpha-skill`.\n")
    outside = tmp_path / "outside_dir"
    write(outside / "trap.md", "Use skill `dead-skill`.\n")
    link = docs / "external_dir"
    link.symlink_to(outside)
    with caplog.at_level("WARNING"):
        result = scan([docs], fake_repo)
    assert [f for f in result.findings if f.kind == "skill_name"] == []
    assert any("outside repo root" in r.getMessage() for r in caplog.records)
    assert len(result.incomplete_scans) >= 1
    assert result.incomplete_scans[0].error_type == "config"


def test_enumerate_skills_returns_none_when_path_is_file(tmp_path):
    """A vendored install with .claude/skills/ as a regular file (corrupt
    layout, broken symlink) must return None, not raise NotADirectoryError."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "skills").write_text("oops not a directory")
    assert enumerate_skills(tmp_path) is None


def test_resolve_repo_root_falls_back_to_cwd_when_no_git(tmp_path, monkeypatch):
    """When no parent has a .git directory, _resolve_repo_root returns CWD."""
    isolated = tmp_path / "no-git-here"
    isolated.mkdir()
    monkeypatch.chdir(isolated)
    rc = main(["--targets", str(isolated), "--allow-empty-scan"])
    assert rc == 0


def test_glob_target_pattern_expansion(fake_repo):
    """--targets accepts glob patterns that expand against repo_root."""
    skills_dir = fake_repo / ".claude" / "skills"
    (skills_dir / "alpha-skill" / "SKILL.md").write_text(
        "# alpha\nUse skill `dead-skill` here.\n"
    )
    (skills_dir / "beta-skill" / "SKILL.md").write_text("# beta living-only\n")
    rc = main([
        "--targets", ".claude/skills/*/SKILL.md",
        "--repo-root", str(fake_repo),
    ])
    assert rc == 1


def test_walk_skips_file_symlink_resolving_outside_repo(tmp_path, fake_repo, caplog):
    """A FILE symlink under an allowed dir whose target is outside the
    repo must be skipped at yield time. CWE-22 / CWE-59 hardening."""
    docs = fake_repo / "docs"
    write(docs / "ok.md", "Hello\n")
    outside_file = tmp_path / "outside-target.md"
    write(outside_file, "Use skill `dead-skill`.\n")
    link = docs / "external_file.md"
    link.symlink_to(outside_file)
    with caplog.at_level("WARNING"):
        result = scan([docs], fake_repo)
    assert [f for f in result.findings if f.kind == "skill_name"] == []
    assert any("outside repo root" in r.getMessage() for r in caplog.records)
    assert len(result.incomplete_scans) >= 1
    assert result.incomplete_scans[0].error_type == "config"


def test_broken_symlink_is_incomplete_scan(fake_repo, caplog):
    docs = fake_repo / "docs"
    docs.mkdir()
    link = docs / "broken.md"
    link.symlink_to(docs / "missing-target.md")
    with caplog.at_level("WARNING"):
        result = scan([docs], fake_repo)

    assert result.incomplete_scans
    assert "could not resolve symlink" in result.incomplete_scans[0].reason
    assert any("could not resolve symlink" in r.getMessage() for r in caplog.records)


def test_walk_breaks_in_repo_symlink_cycle(tmp_path, fake_repo, caplog):
    """A symlinked directory pointing back to an ancestor inside the
    repo must not cause infinite recursion."""
    docs = fake_repo / "docs"
    write(docs / "ok.md", "Hello\n")
    sub = docs / "sub"
    sub.mkdir()
    write(sub / "leaf.md", "Hello\n")
    # sub/back -> docs (cycle)
    (sub / "back").symlink_to(docs)
    with caplog.at_level("WARNING"):
        result = scan([docs], fake_repo)
    assert any("symlink cycle" in r.getMessage() for r in caplog.records)
    assert len(result.incomplete_scans) == 1
    assert result.incomplete_scans[0].error_type == "config"
    assert result.incomplete_scans[0].reason == "symlink cycle detected"


def test_walk_filters_suffix_on_direct_file_target(fake_repo):
    """A direct file target with a non-scanned suffix should be skipped."""
    target = fake_repo / "notes.txt"
    write(target, "Use skill `dead-skill`.\n")
    result = scan([target], fake_repo)
    assert result.findings == []
    assert result.files_scanned == 0


def test_max_findings_cap_truncates_as_incomplete_scan(fake_repo):
    """When findings exceed max_findings, the result is incomplete and
    bounded. A measurement not taken is not a measurement of zero."""
    docs = fake_repo / "docs"
    # Each line produces one finding for skill `dead-skill`.
    payload = "\n".join(["Use skill `dead-skill`." for _ in range(10)])
    write(docs / "huge.md", payload)
    result = scan([docs], fake_repo, max_findings=3)
    truncation = [f for f in result.findings if f.kind == "scan_truncated"]
    assert len(truncation) == 1
    assert truncation[0].severity == "warn"
    assert "incomplete" in truncation[0].recommendation.lower()
    # Hard bound: total findings must respect the budget.
    assert len(result.findings) <= 3
    assert result.incomplete_scans[0].reason == "scan truncated at 3 findings"


def test_truncation_keeps_active_orphan_when_baselined_noise_fills_budget(fake_repo):
    docs = fake_repo / "docs"
    for index in range(499):
        write(docs / f"baseline-{index:03}.md", "Use skill `dead-skill`.\n")
    write(docs / "z-active.md", "Use skill `active-skill`.\n")
    full = scan([docs], fake_repo, max_findings=1000)
    baseline = {
        f.key for f in full.findings if f.referenced_entity == "dead-skill"
    }
    assert len(baseline) == 499

    result = scan([docs], fake_repo, max_findings=10, baseline=baseline)

    active = [f for f in result.findings if not f.suppressed]
    assert result.verdict == "CRITICAL_FAIL"
    assert any(f.referenced_entity == "active-skill" for f in active)
    assert any(item.reason == "scan truncated at 10 findings" for item in result.incomplete_scans)


def test_render_error_envelope_emitted_on_bad_cli_args(capsys):
    """argparse calls sys.exit(2) on typoed flags. main() must catch the
    SystemExit and still emit the ADR-056 error envelope so downstream
    gates parse a stable shape."""
    rc = main(["--not-a-real-flag"])
    assert rc == 2
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "VERDICT: ERROR"
    body = "\n".join(out[:-1])
    payload = json.loads(body)
    assert payload["Success"] is False
    assert payload["Error"]["Code"] == 2
    assert payload["Error"]["Type"] == "InvalidParams"


def test_render_error_envelope_emitted_on_invalid_repo_root(tmp_path, capsys):
    """ADR-056: exit-2 path must emit the envelope with Success=false and
    a populated Error block. The contract is documented in render_envelope's
    docstring; this test pins it."""
    bogus = tmp_path / "does-not-exist"
    rc = main([
        "--repo-root", str(bogus),
        "--targets", str(tmp_path / "x.md"),
        "--output", "json",
    ])
    assert rc == 2
    captured = capsys.readouterr().out.strip().splitlines()
    assert captured[-1] == "VERDICT: ERROR"
    body = "\n".join(captured[:-1])
    payload = json.loads(body)
    assert payload["Success"] is False
    assert payload["Data"] is None
    assert payload["Error"] is not None
    # Per .agents/schemas/skill-output.schema.json: Code is the integer
    # exit code, Type is the canonical enum.
    assert payload["Error"]["Code"] == 2
    assert payload["Error"]["Type"] == "InvalidParams"
    assert "does not exist" in payload["Error"]["Message"]


def test_main_emits_error_envelope_on_unexpected_runtime_failure(
    tmp_path, capsys, monkeypatch
):
    """main() catches an unexpected runtime crash inside scan() and emits the
    ADR-056 error envelope + VERDICT: ERROR line. Without the catch-all the
    /build gate parser sees a Python traceback on stdout and the contract
    breaks. Refs PR #1979 round 18 (Copilot scan.py:488)."""
    # Patch ``scan`` on the module that owns ``main``: this test file loads
    # scan.py via an importlib spec under a private cache key (see the
    # _MODULE_KEY block at the top of the file), so ``import scripts.scan``
    # would resolve to a *different* module object than the one ``main``
    # closes over, and the monkeypatch would not take effect.
    scan_mod = sys.modules[main.__module__]

    def boom(*args, **kwargs):
        raise RuntimeError("simulated filesystem race")

    monkeypatch.setattr(scan_mod, "scan", boom)
    rc = main([
        "--repo-root", str(tmp_path),
        "--targets", str(tmp_path / "anything.md"),
        "--output", "json",
    ])
    assert rc == 2
    out = capsys.readouterr().out.strip().splitlines()
    assert out[-1] == "VERDICT: ERROR"
    payload = json.loads("\n".join(out[:-1]))
    assert payload["Success"] is False
    assert payload["Error"]["Code"] == 2
    assert payload["Error"]["Type"] == "General"
    assert "simulated filesystem race" in payload["Error"]["Message"]
    assert "RuntimeError" in payload["Error"]["Message"]


class TestSkillScriptRefs:
    """Issue #1987: orphan references to .claude/skills/**/scripts/**.py,
    backticked or as a bare `python3 ...` command."""

    def test_bare_command_wrong_name_flagged(self, tmp_path):
        scripts = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        scripts.mkdir(parents=True)
        (scripts / "get_unresolved_review_threads.py").write_text("# real\n")
        text = "python3 .claude/skills/github/scripts/pr/get_unresolved_threads.py --pull-request 1"
        findings, checked = _check_skill_script_refs(text, "doc.md", tmp_path)
        assert checked == 1
        assert [f.kind for f in findings] == ["script_path"]
        assert findings[0].severity == "critical"

    def test_correct_name_not_flagged(self, tmp_path):
        scripts = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        scripts.mkdir(parents=True)
        (scripts / "get_unresolved_review_threads.py").write_text("# real\n")
        text = "`.claude/skills/github/scripts/pr/get_unresolved_review_threads.py`"
        findings, _ = _check_skill_script_refs(text, "doc.md", tmp_path)
        assert findings == []

    def test_extract_handles_both_forms(self):
        assert list(extract_skill_script_refs("python3 .claude/skills/x/scripts/y.py")) == [
            (1, ".claude/skills/x/scripts/y.py")
        ]
        assert list(extract_skill_script_refs("`src/copilot-cli/skills/x/scripts/y.py`")) == [
            (1, "src/copilot-cli/skills/x/scripts/y.py")
        ]

    def test_skill_local_test_path_wrong_name_flagged(self, tmp_path):
        tests_dir = tmp_path / ("." + "claude") / "skills" / "orphan-ref-validator" / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_scan.py").write_text("# real\n")
        missing = ".claude" + "/skills/orphan-ref-validator/tests/test_missing.py"
        text = f"`{missing}`"
        findings, checked = _check_skill_script_refs(text, "doc.md", tmp_path)
        assert checked == 1
        assert [f.kind for f in findings] == ["script_path"]
        assert findings[0].referenced_entity.endswith("test_missing.py")


class TestSingleWordSkillRefs:
    """Issue #2679: single-word (no-hyphen) skill names were invisible to
    SKILL_REF_RE (which requires a hyphen), so deleting a single-word skill
    produced zero orphan-ref findings even when prose still referenced it.

    Detection is widened to single-word backticked tokens, but narrowed to
    genuine skill references: a token is flagged only when it is a curated
    known single-word skill name absent from the live catalog. Arbitrary
    backticked English words are never flagged.
    """

    @pytest.fixture
    def repo_with_single_word_skill(self, fake_repo: Path) -> Path:
        """fake_repo plus a live single-word skill `review`."""
        claude_dir = fake_repo / ".claude"
        skill = claude_dir / "skills" / "review"
        skill.mkdir()
        (skill / "SKILL.md").write_text("# stub\n", encoding="utf-8")
        return fake_repo

    def test_extract_single_word_token_in_backticks(self):
        refs = list(extract_single_word_skill_refs("Use `incoherence` here."))
        assert (1, "incoherence") in refs

    def test_extract_ignores_inline_word_outside_backticks(self):
        assert list(extract_single_word_skill_refs("incoherence no ticks")) == []

    def test_extract_does_not_double_count_hyphenated_token(self):
        # A hyphenated span never matches as a single-word token: the regex has
        # no hyphen group and the backtick must immediately follow the word.
        assert list(extract_single_word_skill_refs("Use `alpha-skill`.")) == []

    def test_retired_single_word_skill_flagged(self, fake_repo):
        """A backticked retired single-word skill name absent from the catalog
        yields a critical orphan finding (the #2662 `incoherence` case)."""
        target = fake_repo / "docs" / "stale.md"
        write(target, "Detection moved out of `incoherence` long ago.\n")
        result = scan([target], fake_repo)
        skill_findings = [f for f in result.findings if f.kind == "skill_name"]
        assert len(skill_findings) == 1
        assert skill_findings[0].referenced_entity == "incoherence"
        assert skill_findings[0].severity == "critical"
        assert result.verdict == "CRITICAL_FAIL"

    def test_common_english_word_not_flagged(self, fake_repo):
        """Ordinary backticked single words (not known skill names) are prose,
        not skill references, and must never be flagged."""
        target = fake_repo / "docs" / "prose.md"
        write(
            target,
            "The `session` value and the `count` field control `output`.\n",
        )
        result = scan([target], fake_repo)
        assert [f for f in result.findings if f.kind == "skill_name"] == []
        assert result.verdict == "PASS"

    @pytest.mark.parametrize("token", ["x", "y", "foo", "bar", "baz", "name"])
    def test_metasyntactic_placeholder_type_claim_not_flagged(self, fake_repo, token):
        """Documentation of the scanner syntax must not become an orphan finding.

        Issue #3833: prose such as ``Skill: `x``` documents the key-value
        route syntax. The explicit type claim makes the token look like a
        skill reference, but these conventional placeholders are examples.
        """
        target = fake_repo / "docs" / "syntax.md"
        write(target, f"The scanner reads Skill: `{token}` as a route name.\n")
        result = scan([target], fake_repo)
        assert [f for f in result.findings if f.kind == "skill_name"] == []
        assert result.refs_checked == 0
        assert result.verdict == "PASS"

    def test_live_single_word_skill_not_flagged(self, repo_with_single_word_skill):
        """A single-word skill present in the catalog is a valid reference and
        produces no finding, even though `review` is also a common word."""
        repo = repo_with_single_word_skill
        target = repo / "docs" / "ok.md"
        write(target, "Run the `review` skill before shipping.\n")
        result = scan([target], repo)
        assert [f for f in result.findings if f.kind == "skill_name"] == []
        assert result.refs_checked == 1
        assert result.verdict == "PASS"

    def test_hyphenated_behavior_unchanged(self, fake_repo):
        """Hyphenated names keep the original behavior: a living kebab name is
        clean, a dead one is critical."""
        target = fake_repo / "docs" / "mixed.md"
        write(target, "Use `alpha-skill` not skill `dead-skill`.\n")
        result = scan([target], fake_repo)
        bad = {
            f.referenced_entity
            for f in result.findings
            if f.kind == "skill_name"
        }
        assert bad == {"dead-skill"}

    def test_retired_single_word_skill_warns_when_catalog_absent(self, tmp_path):
        """Without a skills catalog (vendored install), a retired
        single-word reference downgrades to a non-blocking warn, mirroring the
        hyphenated catalog-absent path."""
        repo = tmp_path / "vendored"
        repo.mkdir()
        (repo / ".git").mkdir()
        docs = repo / "docs"
        write(docs / "x.md", "Use `incoherence` here.\n")
        result = scan([docs], repo)
        skill_findings = [f for f in result.findings if f.kind == "skill_name"]
        assert len(skill_findings) == 1
        assert skill_findings[0].referenced_entity == "incoherence"
        assert skill_findings[0].severity == "warn"
        assert result.verdict == "WARN"


class TestBaselineSuppression:
    """Issue #2371: a default repo-wide scan must not fail on pre-existing
    findings. A --baseline of known finding keys suppresses those findings so
    the verdict is PASS/WARN, while a new finding not in the baseline still
    drives CRITICAL_FAIL."""

    def _orphan(self, fake_repo: Path) -> Any:
        target = fake_repo / "docs" / "stale.md"
        write(target, "Use the skill `gamma-skill` for things.\n")
        result = scan([target], fake_repo)
        critical = [f for f in result.findings if f.severity == "critical"]
        assert len(critical) == 1
        return critical[0]

    def test_baselined_critical_finding_yields_pass(self, fake_repo):
        # Capture the orphan finding's key, then re-scan with it baselined.
        orphan = self._orphan(fake_repo)
        target = fake_repo / "docs" / "stale.md"
        result = scan([target], fake_repo, baseline={orphan.key})
        assert result.verdict == "PASS"
        suppressed = [f for f in result.findings if f.suppressed]
        assert len(suppressed) == 1
        assert suppressed[0].referenced_entity == "gamma-skill"

    def test_new_finding_not_in_baseline_yields_critical_fail(self, fake_repo):
        # Baseline an unrelated key; the actual orphan is still active.
        target = fake_repo / "docs" / "stale.md"
        write(target, "Use the skill `gamma-skill` for things.\n")
        result = scan([target], fake_repo, baseline={"other.md:1:skill_name:zeta-skill"})
        assert result.verdict == "CRITICAL_FAIL"
        active = [f for f in result.findings if not f.suppressed]
        assert any(f.referenced_entity == "gamma-skill" for f in active)

    def test_mixed_baselined_and_new_yields_critical_fail(self, fake_repo):
        target = fake_repo / "docs" / "stale.md"
        write(target, "Use skill `gamma-skill` and skill `delta-skill` here.\n")
        full = scan([target], fake_repo)
        keys = {f.key for f in full.findings if f.referenced_entity == "gamma-skill"}
        assert keys, "expected gamma-skill orphan finding"
        result = scan([target], fake_repo, baseline=keys)
        # gamma-skill suppressed; delta-skill still active and critical.
        assert result.verdict == "CRITICAL_FAIL"
        suppressed = {f.referenced_entity for f in result.findings if f.suppressed}
        active = {f.referenced_entity for f in result.findings if not f.suppressed}
        assert "gamma-skill" in suppressed
        assert "delta-skill" in active

    def test_finding_key_format(self):
        f = Finding(
            kind="skill_name",
            severity="critical",
            target_file="docs/x.md",
            line=7,
            referenced_entity="gamma-skill",
            recommendation="fix it",
        )
        assert f.key == "docs/x.md:7:skill_name:gamma-skill"

    def test_load_baseline_plain_text(self, tmp_path):
        bl = tmp_path / "baseline.txt"
        bl.write_text(
            "# pre-existing orphans\n"
            "docs/a.md:1:skill_name:gamma-skill\n"
            "\n"
            "docs/b.md:2:script_path:scripts/old.py\n",
            encoding="utf-8",
        )
        keys = load_baseline(bl)
        assert keys == {
            "docs/a.md:1:skill_name:gamma-skill",
            "docs/b.md:2:script_path:scripts/old.py",
        }

    def test_load_baseline_json_list(self, tmp_path):
        bl = tmp_path / "baseline.json"
        bl.write_text(
            json.dumps(["docs/a.md:1:skill_name:gamma-skill"]), encoding="utf-8"
        )
        assert load_baseline(bl) == {"docs/a.md:1:skill_name:gamma-skill"}

    def test_load_baseline_json_envelope(self, tmp_path):
        bl = tmp_path / "baseline.json"
        envelope = {
            "Data": {
                "findings": [
                    {
                        "kind": "skill_name",
                        "target_file": "docs/a.md",
                        "line": 1,
                        "referenced_entity": "gamma-skill",
                    }
                ]
            }
        }
        bl.write_text(json.dumps(envelope), encoding="utf-8")
        assert load_baseline(bl) == {"docs/a.md:1:skill_name:gamma-skill"}

    def test_load_baseline_json_envelope_with_verdict_suffix(self, tmp_path):
        bl = tmp_path / "baseline.json"
        result = ScanResult(
            findings=[
                Finding(
                    kind="skill_name",
                    severity="critical",
                    target_file="docs/a.md",
                    line=1,
                    referenced_entity="gamma-skill",
                    recommendation="Remove stale reference.",
                )
            ]
        )
        bl.write_text(render_envelope(result, "json"), encoding="utf-8")
        assert load_baseline(bl) == {"docs/a.md:1:skill_name:gamma-skill"}

    def test_load_baseline_json_envelope_skips_null_key_fields(self, tmp_path):
        bl = tmp_path / "baseline.json"
        envelope = {
            "Data": {
                "findings": [
                    {
                        "kind": "skill_name",
                        "target_file": "docs/a.md",
                        "line": None,
                        "referenced_entity": "gamma-skill",
                    }
                ]
            }
        }
        bl.write_text(json.dumps(envelope), encoding="utf-8")
        assert load_baseline(bl) == set()

    def test_load_baseline_missing_file_raises(self, tmp_path):
        with pytest.raises(BaselineError):
            load_baseline(tmp_path / "nope.txt")

    def test_load_baseline_bad_json_raises(self, tmp_path):
        bl = tmp_path / "baseline.json"
        bl.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(BaselineError):
            load_baseline(bl)

    def test_cli_baseline_file_suppresses(self, fake_repo, capsys):
        target = fake_repo / "docs" / "stale.md"
        write(target, "Use the skill `gamma-skill` for things.\n")
        bl = fake_repo / "baseline.txt"
        bl.write_text("docs/stale.md:1:skill_name:gamma-skill\n", encoding="utf-8")
        rc = main(
            [
                "--targets",
                str(target),
                "--repo-root",
                str(fake_repo),
                "--baseline",
                str(bl),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "VERDICT: PASS" in out

    def test_cli_bad_baseline_file_is_config_error(self, fake_repo, capsys):
        rc = main(
            [
                "--repo-root",
                str(fake_repo),
                "--baseline",
                str(fake_repo / "missing.txt"),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 2
        assert "VERDICT: ERROR" in out

    def test_cli_baseline_path_outside_repo_is_config_error(self, fake_repo, capsys):
        outside = fake_repo.parent / "baseline.txt"
        outside.write_text("docs/stale.md:1:skill_name:gamma-skill\n", encoding="utf-8")
        rc = main(
            [
                "--repo-root",
                str(fake_repo),
                "--baseline",
                str(outside),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 2
        assert "baseline path escapes repository root" in out
        assert "VERDICT: ERROR" in out

    def test_truncation_keeps_active_findings_before_suppressed(self, fake_repo):
        target = fake_repo / "docs" / "stale.md"
        write(target, "Use skill `gamma-skill` and skill `delta-skill` here.\n")
        full = scan([target], fake_repo)
        gamma_keys = {
            f.key for f in full.findings if f.referenced_entity == "gamma-skill"
        }
        assert gamma_keys, "expected gamma-skill orphan finding"
        result = scan([target], fake_repo, max_findings=2, baseline=gamma_keys)
        active = [f for f in result.findings if not f.suppressed]
        assert result.verdict == "CRITICAL_FAIL"
        assert any(f.referenced_entity == "delta-skill" for f in active)


# ---------- sibling-namespace resolution ----------
#
# SKILL_REF_RE matches every backticked kebab token, so prose that names a
# non-skill artifact (an agent, a slash command, a review axis, a Serena
# memory) was reported as a reference to a deleted skill. Resolving the token
# against those namespaces is what separates "names a real non-skill thing"
# from "names nothing". Regression cover for the 14 false positives the
# default-target scan reported on main.


@pytest.fixture
def sibling_repo(fake_repo: Path) -> Path:
    """Extend fake_repo with one artifact in each sibling namespace."""
    write(fake_repo / ".claude" / "commands" / "ship-it.md", "# command\n")
    write(
        skill_dir(fake_repo, "alpha-skill") / "references" / "decision-rigor.md",
        "# review axis\n",
    )
    write(
        fake_repo / ".serena" / "memories" / "testing" / "testing-002-test-first.md",
        "# memory\n",
    )
    return fake_repo


def test_enumerate_sibling_artifacts_covers_every_namespace(sibling_repo):
    names = enumerate_sibling_artifacts(sibling_repo)
    assert {"agent-one", "ship-it", "decision-rigor", "testing-002-test-first"} <= names


def test_enumerate_sibling_artifacts_empty_when_namespaces_absent(tmp_path):
    """A vendored install has none of these directories; resolution is a no-op."""
    assert enumerate_sibling_artifacts(tmp_path) == frozenset()


@pytest.mark.parametrize(
    "token",
    ["agent-one", "ship-it", "decision-rigor", "testing-002-test-first"],
)
def test_sibling_namespace_reference_yields_no_finding(sibling_repo, token, capsys):
    write(sibling_repo / "notes" / "s.md", f"Mentions `{token}` in prose.\n")
    rc = main(["--targets", "notes", "--repo-root", str(sibling_repo)])
    assert rc == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_sibling_resolution_does_not_mask_a_real_orphan(sibling_repo, capsys):
    """Negative control: resolution must not suppress a genuinely dead skill."""
    write(
        sibling_repo / "notes" / "s.md",
        "Live `alpha-skill`, agent `agent-one`, dead skill `ghost-skill`.\n",
    )
    rc = main(["--targets", "notes", "--repo-root", str(sibling_repo)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "ghost-skill" in out
    assert "agent-one" not in out


def test_memory_corpus_bare_kebab_tokens_are_not_skill_candidates(fake_repo, capsys):
    """Issue #3637: .serena memories use kebab-case for many non-skill terms.

    A memory-corpus gate must not flag bare GitHub Actions, model, config,
    hook, HTTP header, or label tokens as missing skills. The same corpus still
    needs typed skill references so real deleted skills are not buried.
    """
    text = "\n".join(
        [
            "CI uses `ubuntu-latest`, `self-hosted`, and `retention-days`.",
            "Models include `gpt-4o-mini` and `claude-fable-5`.",
            "Config keys include `quality-gates`, `bot-pat`, and `write-all`.",
            "Hooks include `post-create`, `post-switch`, and `pre-merge`.",
            "Headers include `x-ratelimit-remaining` and `retry-after`.",
            "Labels include `area-workflows` and `area-infrastructure`.",
        ]
    )
    write(fake_repo / ".serena" / "memories" / "ops.md", text + "\n")

    rc = main(["--targets", ".serena/memories", "--repo-root", str(fake_repo)])

    assert rc == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_memory_corpus_typed_nonhistorical_kebab_token_is_not_flagged(
    fake_repo, capsys
):
    """A typed-looking memory mention is not enough without retired-skill evidence."""
    write(
        fake_repo / ".serena" / "memories" / "ops.md",
        "This memory captures learnings from using the `land-and-deploy` skill.\n",
    )

    rc = main(["--targets", ".serena/memories", "--repo-root", str(fake_repo)])

    assert rc == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_memory_corpus_typed_orphan_skill_still_flags(fake_repo, capsys):
    """Negative control: memory-corpus narrowing must not make detector inert."""
    write(
        fake_repo / ".serena" / "memories" / "ops.md",
        "See the `doc-coverage` skill.\n",
    )

    rc = main(["--targets", ".serena/memories", "--repo-root", str(fake_repo)])
    out = capsys.readouterr().out

    assert rc == 1
    assert "doc-coverage" in out


def test_check_skill_refs_defaults_to_previous_behavior():
    """Omitting sibling_names keeps the pre-change contract for other callers."""
    findings, checked = _scan._check_skill_refs(
        "A skill `ghost-skill` ref.\n", "s.md", set(), True
    )
    assert checked == 1
    assert [f.referenced_entity for f in findings] == ["ghost-skill"]


@pytest.mark.parametrize("token", ["keep-as-agent", "context-fork-skill", "co-change-checklist"])
def test_classification_verdict_literals_are_denylisted(fake_repo, token, capsys):
    """REQ-011/TASK-011 verdict enums and spec section templates are not skills."""
    write(fake_repo / "notes" / "s.md", f"Set `verdict = {token}` here.\n")
    rc = main(["--targets", "notes", "--repo-root", str(fake_repo)])
    assert rc == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_typed_skill_reference_does_not_resolve_to_a_sibling(sibling_repo, capsys):
    """REQ-009 AC-2: prose calling a token a skill must resolve against skills.

    `agent-one` exists only as an agent. Claiming it is a skill is a wrong
    reference, so sibling resolution must not rescue it. This is the case the
    first cut of sibling resolution got wrong: it traded a false positive for
    a wrong pass.
    """
    write(sibling_repo / "notes" / "s.md", "Use the `agent-one` skill.\n")
    rc = main(["--targets", "notes", "--repo-root", str(sibling_repo)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "agent-one" in out


@pytest.mark.parametrize(
    "prose",
    [
        "Use the `decision-rigor` skill.",
        "The `decision-rigor` skill lives here.",
        "See skill `decision-rigor` for detail.",
        'Call Skill(skill=`decision-rigor`) now.',
        "`decision-rigor` is a skill.",
    ],
)
def test_type_claim_shapes_all_force_strict_resolution(sibling_repo, prose, capsys):
    """Every shape that asserts skill-ness must bypass sibling resolution."""
    write(sibling_repo / "notes" / "s.md", prose + "\n")
    rc = main(["--targets", "notes", "--repo-root", str(sibling_repo)])
    assert rc == 1
    assert "decision-rigor" in capsys.readouterr().out


@pytest.mark.parametrize(
    "prose",
    [
        "Improve your `bash` skills.",
        "Soft skills `people` matter.",
        "The `alpha-skill` and `beta-skill` skills.",
    ],
)
def test_plural_skills_prose_is_not_a_type_claim(sibling_repo, prose, capsys):
    """Plural reads as proficiency prose more often than as a catalog reference.

    Treating it as a type claim turns the /build gate red on sentences that
    name no artifact at all.
    """
    write(sibling_repo / "notes" / "s.md", prose + "\n")
    rc = main(["--targets", "notes", "--repo-root", str(sibling_repo)])
    assert rc == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_type_claim_is_honored_without_any_sibling_namespace(fake_repo, capsys):
    """A vendored install has no siblings; explicit skill claims still bind.

    Guards against gating the type-claim scan on sibling availability, which
    would silently drop the check in exactly the install shape the fallback
    was written for.
    """
    write(fake_repo / "notes" / "s.md", "Invoke the `ghost` skill.\n")
    rc = main(["--targets", "notes", "--repo-root", str(fake_repo)])
    assert rc == 1
    assert "ghost" in capsys.readouterr().out


def test_type_claim_on_a_living_skill_still_passes(sibling_repo, capsys):
    """Strict resolution must not flag a typed reference to a real skill."""
    write(sibling_repo / "notes" / "s.md", "Use the `alpha-skill` skill.\n")
    rc = main(["--targets", "notes", "--repo-root", str(sibling_repo)])
    assert rc == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


@pytest.mark.parametrize(
    "prose",
    [
        'Config sets skill="decision-rigor" here.',
        'Config sets skill: "decision-rigor" here.',
        "Config sets skill='decision-rigor' here.",
    ],
)
def test_quoted_type_claim_alone_is_not_a_reference(sibling_repo, prose, capsys):
    """A type claim strengthens resolution; it never creates a candidate.

    Both extractors require backticks, so a quoted ``skill="x"`` with no
    backticked ``x`` on the line yields a type claim about a token the
    scanner never examines. Pinned because the natural "fix" on reading the
    type-claim regex is to widen the extractors to quoted values, which would
    flag every YAML and JSON config key that happens to be named ``skill``.
    """
    write(sibling_repo / "notes" / "s.md", prose + "\n")
    rc = main(["--targets", "notes", "--repo-root", str(sibling_repo)])
    assert rc == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_quoted_type_claim_types_a_backticked_token_on_the_same_line(
    sibling_repo, capsys
):
    """The quoted arm is live: it types a candidate the backticks supply.

    ``decision-rigor`` is a review axis, so a bare mention resolves through
    the sibling namespace. The quoted type claim on the same line asserts it
    is a skill, which forces strict resolution and the finding.
    """
    write(
        sibling_repo / "notes" / "s.md",
        'Use `decision-rigor` (skill="decision-rigor").\n',
    )
    rc = main(["--targets", "notes", "--repo-root", str(sibling_repo)])
    assert rc == 1
    assert "decision-rigor" in capsys.readouterr().out


def test_type_claim_does_not_reach_a_candidate_on_another_line(
    sibling_repo, capsys
):
    """Type claims are line-scoped, and the scoping is what makes them safe.

    Both extractors return ``(lineno, token)`` pairs and ``_check_skill_refs``
    tests the pair, not the bare token. Collapsing that to a token-only set
    would let one config line retroactively retype every prose mention of the
    same name in the file, turning sibling artifacts into orphans document
    wide.
    """
    write(
        sibling_repo / "notes" / "s.md",
        'Use `decision-rigor`.\nConfig sets skill="decision-rigor".\n',
    )
    rc = main(["--targets", "notes", "--repo-root", str(sibling_repo)])
    assert rc == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_type_claim_does_not_reach_a_different_token_on_its_own_line(
    sibling_repo, capsys
):
    """A claim types the token it names, not every candidate beside it.

    Matching on line number alone is the cheaper implementation and passes a
    naive same-line test, so pin the token half of the pair too. Here the
    claim names ``alpha-skill`` while the backticks supply ``decision-rigor``,
    a review axis that must keep resolving through the sibling namespace.
    """
    write(
        sibling_repo / "notes" / "s.md",
        'Use `decision-rigor` (skill="alpha-skill").\n',
    )
    rc = main(["--targets", "notes", "--repo-root", str(sibling_repo)])
    assert rc == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


# ---------- issue #3637: kebab tokens need evidence, not just a hyphen ----------


def _filters_module():
    """Load filters.py beside the scan.py under test, keyed like _MODULE_KEY."""
    key = _MODULE_KEY + "_filters"
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, _SCRIPT_DIR / "filters.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def _skill_names(result) -> set[str]:
    return {f.referenced_entity for f in result.findings if f.kind == "skill_name"}


def _catalog() -> Path:
    """Return the skills catalog holding this test, canonical or vendored.

    The file sits at ``<catalog>/orphan-ref-validator/tests/test_scan.py`` in
    both trees, so ``parents[2]`` is the catalog in either one. Naming the
    canonical prefix literally would resolve to nothing from the vendored copy,
    which is the portability drift issue #2050 exists to stop.
    """
    return Path(__file__).resolve().parents[2]


def _repo_root() -> Path:
    """Return the checkout root, found by walking up rather than by index.

    The canonical and vendored trees sit at different depths, so a fixed parent
    index is correct in at most one of them.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    pytest.skip("not a git checkout")


def _live_skills() -> set[str]:
    """Return the names the catalog currently resolves."""
    catalog = _catalog()
    if not catalog.is_dir():
        pytest.skip("no skills catalog in this checkout")
    return {p.name for p in catalog.iterdir() if (p / "SKILL.md").is_file()}


class TestKebabTokensNeedEvidence:
    """A backticked kebab token is a skill reference only with evidence.

    Evidence is a type claim in the prose or membership in the curated set of
    names this repository has used for a skill. Before issue #3637 every
    hyphenated token was a candidate, which produced 183 findings and zero
    true positives on `.serena/memories/`.
    """

    # -- still detected: the reference makes a type claim --

    def test_a_typed_reference_to_a_missing_skill_is_flagged(self, fake_repo):
        write(fake_repo / "notes" / "s.md", "Run the `zeta-skill` skill now.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {"zeta-skill"}

    def test_the_skill_before_token_form_is_flagged(self, fake_repo):
        write(fake_repo / "notes" / "s.md", "Invoke skill `zeta-skill` here.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {"zeta-skill"}

    def test_the_key_value_form_is_flagged(self, fake_repo):
        write(fake_repo / "notes" / "s.md", 'Use `zeta-skill` (skill="zeta-skill").\n')
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {"zeta-skill"}

    def test_a_typed_reference_to_a_live_skill_is_not_flagged(self, fake_repo):
        write(fake_repo / "notes" / "s.md", "Run the `alpha-skill` skill now.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    # -- still detected: the name is a retired skill of this repository --

    def test_a_bare_retired_skill_name_is_flagged(self, fake_repo):
        write(fake_repo / "notes" / "s.md", "See `doc-coverage` for details.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {"doc-coverage"}

    @pytest.mark.parametrize(
        "name",
        ["doc-coverage", "doc-sync", "github-pr-reply",
         "session-migration", "session-qa-eligibility"],
    )
    def test_every_curated_retired_name_is_detectable(self, fake_repo, name):
        write(fake_repo / "notes" / "s.md", f"Mentions `{name}` in prose.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {name}

    def test_a_retired_name_that_is_live_again_is_not_flagged(self, fake_repo):
        restored = fixture_catalog(fake_repo) / "doc-sync"
        restored.mkdir(parents=True)
        (restored / "SKILL.md").write_text("# stub\n", encoding="utf-8")
        write(fake_repo / "notes" / "s.md", "See `doc-sync` for details.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    def test_a_typed_retired_name_yields_one_finding_not_two(self, fake_repo):
        write(fake_repo / "notes" / "s.md", "Run the `doc-sync` skill.\n")
        result = scan([fake_repo / "notes"], fake_repo)
        assert [f.referenced_entity for f in result.findings] == ["doc-sync"]

    # -- no longer detected: a bare token with no evidence --

    def test_a_bare_unknown_kebab_token_is_not_flagged(self, fake_repo):
        write(fake_repo / "notes" / "s.md", "Set `zeta-skill` in the config.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    @pytest.mark.parametrize(
        "token",
        [
            "ubuntu-latest", "windows-latest", "self-hosted", "retention-days",
            "any-glob-to-any-file", "all-globs-to-all-files",
            "gpt-4o-mini", "gemini-3-pro", "claude-fable-5",
            "x-ratelimit-remaining", "retry-after",
            "post-switch", "pre-merge", "post-merge",
            "try-catch", "if-then-else", "return-value",
            "area-workflows", "vscode-extension", "mcp-server",
            "hexagonal-architecture", "branch-by-abstraction",
            "probe-050", "your-api-key-here",
        ],
    )
    def test_real_prose_vocabulary_is_not_flagged(self, fake_repo, token):
        """Every token here was a live false positive on the memory corpus."""
        write(fake_repo / "notes" / "s.md", f"The `{token}` value applies.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    def test_a_bare_live_skill_name_still_counts_as_checked(self, fake_repo):
        findings, checked = _scan._check_skill_refs(
            "Use `alpha-skill` here.\n", "s.md", {"alpha-skill"}, True
        )
        assert (findings, checked) == ([], 1)

    def test_a_bare_unknown_token_is_not_counted_as_checked(self, fake_repo):
        findings, checked = _scan._check_skill_refs(
            "Use `zeta-skill` here.\n", "s.md", {"alpha-skill"}, True
        )
        assert (findings, checked) == ([], 0)

    # -- a hyphenated token is reachable once prose calls it a skill --

    def test_a_hyphenated_non_skill_is_flagged_when_typed(self, fake_repo):
        write(fake_repo / "notes" / "s.md", "Run the `read-only` skill.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {"read-only"}

    def test_a_hyphenated_non_skill_is_silent_without_a_type_claim(
        self, fake_repo
    ):
        write(fake_repo / "notes" / "s.md", "The file is `read-only` here.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    def test_a_model_identifier_is_never_a_candidate(self, fake_repo):
        write(fake_repo / "notes" / "s.md", "Run the `claude-opus-5` skill.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    # -- a field noun after the token makes it a noun adjunct, not a name --

    def test_a_field_noun_after_the_token_is_not_a_type_claim(self, fake_repo):
        write(
            fake_repo / "notes" / "s.md",
            "Iterate on the skill `description` field until it passes.\n",
        )
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    def test_the_same_token_without_the_field_noun_is_still_a_claim(
        self, fake_repo
    ):
        write(fake_repo / "notes" / "s.md", "Run the skill `description`.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {
            "description"
        }

    @pytest.mark.parametrize(
        "head_noun", ["name", "names", "file", "files", "directory", "directories"]
    )
    def test_every_head_noun_issue_3727_names_is_guarded(self, fake_repo, head_noun):
        """Issue #3727 lists these head nouns; each must defeat the type claim.

        Parametrized rather than merged into one fixture so a regression names
        the single noun that broke instead of failing on the whole set.
        """
        write(
            fake_repo / "notes" / "s.md",
            f"Check the skill `description` {head_noun} before shipping.\n",
        )
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    # -- a skill owned by another catalog is a correct reference --

    def test_a_catalog_qualified_foreign_skill_is_not_an_orphan(self, fake_repo):
        write(
            fake_repo / "notes" / "s.md",
            "gstack `claim-verification-before-ingest` skill\n",
        )
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    def test_an_unqualified_foreign_skill_is_still_an_orphan(self, fake_repo):
        """Issue #3728 exempts the qualified form only; the bare token stays a finding.

        Without this the two-entry allowlist would swallow every future mention
        of those tokens, including one that names a local skill gone missing.
        """
        write(
            fake_repo / "notes" / "s.md",
            "`claim-verification-before-ingest` skill\n",
        )
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {
            "claim-verification-before-ingest"
        }

    def test_a_wrongly_qualified_foreign_skill_is_still_an_orphan(self, fake_repo):
        """A qualifier that is not the owning catalog is not a qualifier."""
        write(
            fake_repo / "notes" / "s.md",
            "gizmo `claim-verification-before-ingest` skill\n",
        )
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {
            "claim-verification-before-ingest"
        }

    def test_an_unknown_foreign_looking_skill_is_still_an_orphan(
        self, fake_repo
    ):
        write(
            fake_repo / "notes" / "s.md",
            "gstack `not-a-foreign-skill` skill\n",
        )
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {
            "not-a-foreign-skill"
        }

    def test_the_owning_catalog_qualifies_only_its_own_token(self, fake_repo):
        """Both tokens are gstack's, so each must accept the same qualifier."""
        write(
            fake_repo / "notes" / "s.md",
            "gstack `front-gate-before-pipeline` skill\n",
        )
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    def test_a_catalog_name_embedded_in_a_longer_word_is_not_a_qualifier(
        self, fake_repo
    ):
        """The qualifier pattern is word-bounded, so a substring must not count.

        Without the boundaries ``gstack`` would match inside ``gstackoverflow``
        and silently exempt a token that nothing in the sentence actually
        attributes to the owning catalog.
        """
        write(
            fake_repo / "notes" / "s.md",
            "gstackoverflow `front-gate-before-pipeline` skill\n",
        )
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {
            "front-gate-before-pipeline"
        }

    def test_every_catalog_name_has_a_compiled_qualifier_pattern(self):
        """The qualifier lookup indexes directly, so the table must be total.

        ``is_qualified_foreign_skill`` reads
        ``_CATALOG_QUALIFIER_PATTERNS[catalog]`` without a fallback, which is
        safe only while the pattern table covers every value in
        ``FOREIGN_SKILL_CATALOGS``. Adding a catalog entry without rebuilding
        the table would raise ``KeyError`` on the first reference instead of
        returning a finding, so pin the invariant here rather than discover it
        from a traceback.
        """
        filters = _filters_module()
        assert set(filters._CATALOG_QUALIFIER_PATTERNS) == set(
            filters.FOREIGN_SKILL_CATALOGS.values()
        )

    def test_a_catalog_qualifier_still_matches_case_insensitively(self, fake_repo):
        """``re.IGNORECASE`` moved from the call site into the compiled pattern.

        Prose capitalizes a catalog name at the start of a sentence, so losing
        the flag during that move would turn every sentence-initial mention
        back into a finding while the lowercase tests kept passing.
        """
        write(
            fake_repo / "notes" / "s.md",
            "GStack `front-gate-before-pipeline` skill\n",
        )
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    # -- sibling resolution is unchanged --

    def test_an_untyped_sibling_artifact_is_not_flagged(self, fake_repo):
        write(fake_repo / "notes" / "s.md", "See `agent-one` for details.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == set()

    def test_a_typed_sibling_artifact_is_still_flagged(self, fake_repo):
        write(fake_repo / "notes" / "s.md", "Run the `agent-one` skill.\n")
        assert _skill_names(scan([fake_repo / "notes"], fake_repo)) == {"agent-one"}


class TestFindingsAreDeduplicated:
    """Issue #3727: identical findings must not each spend a budget slot."""

    def _finding(self, **over):
        base = dict(
            kind="skill_name",
            severity="critical",
            target_file="a.md",
            line=7,
            referenced_entity="ghost",
            recommendation="anything",
        )
        base.update(over)
        return _scan.Finding(**base)

    def test_an_identical_repeat_is_dropped(self):
        findings = [self._finding(), self._finding()]
        _scan._deduplicate_findings(findings)
        assert len(findings) == 1

    def test_a_differing_recommendation_still_counts_as_a_repeat(self):
        findings = [self._finding(), self._finding(recommendation="other")]
        _scan._deduplicate_findings(findings)
        assert len(findings) == 1

    def test_findings_differing_in_any_key_field_are_both_kept(self):
        for field, value in (
            ("target_file", "b.md"),
            ("line", 8),
            ("kind", "script_path"),
            ("referenced_entity", "other"),
        ):
            findings = [self._finding(), self._finding(**{field: value})]
            _scan._deduplicate_findings(findings)
            assert len(findings) == 2, field

    def test_the_first_of_a_repeat_pair_is_the_one_kept(self):
        findings = [self._finding(), self._finding(recommendation="second")]
        _scan._deduplicate_findings(findings)
        assert findings[0].recommendation == "anything"

    def test_one_line_naming_a_token_twice_yields_one_finding(self, fake_repo):
        """End to end: proves ``scan`` calls the deduplicator.

        A token written twice on one line is extracted twice, so before
        issue #3727 the same finding was appended twice and spent two slots
        of the ``MAX_FINDINGS`` budget. Real instances of this shape include
        ADR-040 line 232 and the scanner's own ``patterns.py`` line 65.
        """
        write(
            fake_repo / "notes" / "s.md",
            "The `ghost` skill replaced the `ghost` skill.\n",
        )
        findings = [
            f
            for f in scan([fake_repo / "notes"], fake_repo).findings
            if f.referenced_entity == "ghost"
        ]
        assert len(findings) == 1

    def test_deduplication_runs_before_the_budget_is_spent(self, fake_repo):
        """A repeat must not push a real finding past ``max_findings``."""
        findings = [self._finding(), self._finding(), self._finding(line=9)]
        _scan._deduplicate_findings(findings)
        assert [f.line for f in findings] == [7, 9]


class TestRetiredKebabSkillsStayHonest:
    """The curated set is only trustworthy while it matches the catalog."""

    def test_no_curated_name_is_currently_live(self):
        """A live name in the set is stale: the catalog already resolves it."""
        assert _filters_module().KNOWN_RETIRED_KEBAB_SKILLS & _live_skills() == set()

    def test_every_curated_name_is_hyphenated(self):
        """A single-word name belongs in KNOWN_SINGLE_WORD_SKILLS instead."""
        assert all("-" in n for n in _filters_module().KNOWN_RETIRED_KEBAB_SKILLS)

    def test_every_deleted_hyphenated_skill_is_curated_or_restored(self):
        """Drift guard: a deleted skill must be listed or it goes silent.

        Scoped to the canonical catalog, which is what the curated set
        describes. The generated mirror's deletion history records generation
        events, not retirements: ``merge-resolver`` reads as deleted there
        while it is live canonically, so asserting against it would fail for a
        reason that has nothing to do with skill retirement.

        Walks ``HEAD`` rather than ``--all``. ``--all`` reads every ref the
        clone happens to hold, including ``refs/remotes/pr/*`` caches of
        unmerged pull request heads and any local branch. Those are properties
        of the clone, not of the repository, so the same commit passed in CI
        and failed locally (issue #3753). ``HEAD`` is the history of the commit
        under test, which is what the curated set describes.

        Skipped on a shallow clone, where the deletion history is absent and
        the derived set would be empty for the wrong reason.
        """
        if _MODULE_KEY.endswith("_mirror"):
            pytest.skip("generated mirror: deletions are generation, not retirement")
        repo_root = _repo_root()
        shallow = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--is-shallow-repository"],
            capture_output=True, text=True, check=False,
        )
        if shallow.stdout.strip() != "false":
            pytest.skip("shallow clone: deletion history unavailable")
        rel = _catalog().relative_to(repo_root).as_posix()
        log = subprocess.run(
            ["git", "-C", str(repo_root), "log", "HEAD", "--diff-filter=D",
             "--name-only", "--format=", "--", f"{rel}/*/SKILL.md"],
            capture_output=True, text=True, check=False,
        )
        deleted = {
            PurePosixPath(line).parent.name
            for line in log.stdout.splitlines()
            if line.startswith(f"{rel}/") and line.endswith("/SKILL.md")
        }
        gone = {n for n in deleted if n not in _live_skills() and "-" in n}
        assert gone <= _filters_module().KNOWN_RETIRED_KEBAB_SKILLS


class TestTheMemoryCorpusIsGateable:
    """Issue #3637 acceptance bar, measured against the real corpus."""

    @staticmethod
    def _memories() -> Path:
        target = _repo_root() / ".serena" / "memories"
        if not target.is_dir():
            pytest.skip("no .serena/memories in this checkout")
        return target

    def test_the_memory_corpus_reports_no_unowned_skill_orphans(self):
        """183 skill_name findings before the change, zero after.

        The one remaining candidate was `land-and-deploy`, a typed mention that
        the memory itself documents as belonging to gstack. Memories are prose
        about other repositories as often as this one, so a type claim alone is
        not evidence there and PR #3698 requires the retired-skill allowlist as
        well. This test pins that decision: an accurate sentence about an
        external tool must not fail the gate. The planted-reference test below
        is the negative control proving the detector is still live here.
        """
        target = self._memories()
        result = scan([target], _repo_root())
        assert _skill_names(result) == set()

    def test_a_planted_reference_to_a_deleted_skill_is_still_caught(self, tmp_path):
        """The other half of the acceptance bar."""
        repo_root = _repo_root()
        if not _catalog().is_dir():
            pytest.skip("no skills catalog in this checkout")
        planted = repo_root / ".serena" / "memories"
        if not planted.is_dir():
            pytest.skip("no .serena/memories in this checkout")
        probe = planted / "zz-orphan-ref-probe.md"
        probe.write_text("See the `doc-coverage` skill.\n", encoding="utf-8")
        try:
            result = scan([probe], repo_root)
        finally:
            probe.unlink()
        assert _skill_names(result) == {"doc-coverage"}

class TestDocumentationMayQuoteARouteWithoutBecomingOne:
    """Issue #3749: prose that describes route syntax has to write route syntax.

    The memory corpus documents the parser's own route-versus-documentation
    rule, and to state the rule it spells both forms out. The scanner reads the
    live form as a reference and blocks the push. The line-scoped
    ``<!-- orphan-ref-ignore -->`` directive is the designed escape hatch; these
    tests pin that it reaches ``skill_name`` findings, not only path findings,
    and that it does not quietly blunt the detector for everyone else.

    Everything runs against ``fake_repo`` rather than the real checkout. Writing
    probes into the working tree would race the canonical and mirrored copies of
    this suite against each other, since both carry the same test names, and a
    crashed run would leave litter behind.
    """

    @staticmethod
    def _docs(fake_repo: Path, body: str) -> Path:
        docs = fake_repo / "memories"
        docs.mkdir(exist_ok=True)
        (docs / "memo.md").write_text(body, encoding="utf-8")
        return docs

    def test_an_undirected_route_in_prose_is_still_reported(self, fake_repo: Path) -> None:
        """Negative control: without the directive the detector must fire.

        Without this the positive case below could pass because the scanner
        stopped detecting anything at all.
        """
        docs = self._docs(fake_repo, "prose about Skill: `zzznotaskill` here\n")
        assert _skill_names(scan([docs], fake_repo)) == {"zzznotaskill"}

    def test_the_directive_suppresses_a_skill_name_finding(self, fake_repo: Path) -> None:
        """Positive: the same line, plus the directive, is not a finding."""
        docs = self._docs(
            fake_repo,
            "prose about Skill: `zzznotaskill` here <!-- orphan-ref-ignore -->\n",
        )
        assert _skill_names(scan([docs], fake_repo)) == set()

    def test_a_suppressed_route_is_recorded_rather_than_dropped(self, fake_repo: Path) -> None:
        """Edge: suppression must stay auditable.

        A directive that silently deleted the reference would make the escape
        hatch impossible to review. The reference has to survive in
        ``directive_suppressed`` with its file and line.

        ``target_file`` is built with ``str()`` on a relative path, so it is
        separator-native and reads ``memories\\memo.md`` on Windows. The
        comparison normalises rather than pinning the POSIX form.
        """
        docs = self._docs(
            fake_repo,
            "prose about Skill: `zzznotaskill` here <!-- orphan-ref-ignore -->\n",
        )
        result = scan([docs], fake_repo)
        recorded = [
            (Path(ref.target_file).as_posix(), ref.line)
            for ref in result.directive_suppressed
        ]
        assert recorded == [("memories/memo.md", 1)]

    def test_the_directive_is_scoped_to_its_own_line(self, fake_repo: Path) -> None:
        """Edge: a directive on one line must not cover the next one.

        A file-wide effect would let one directive hide every later drift in
        the same memory. ``<!-- orphan-ref-ignore-file -->`` is the opt-in for
        that, and it is a different directive.
        """
        docs = self._docs(
            fake_repo,
            "first Skill: `zzzfirstskill` here <!-- orphan-ref-ignore -->\n"
            "second Skill: `zzzsecondskill` here\n",
        )
        assert _skill_names(scan([docs], fake_repo)) == {"zzzsecondskill"}
