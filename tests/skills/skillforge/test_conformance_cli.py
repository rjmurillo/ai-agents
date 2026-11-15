"""Catalog shape, parser, CLI contract, and repository state for conformance.py."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.skills.skillforge.conformance_support import (
    PROJECT_ROOT,
    RULES,
    SCRIPT_DIR,
    SKILLS_DIR,
    conformance,
    load,
    make_skill,
    results,
)

SCRIPT = SCRIPT_DIR / "conformance.py"
BUILDERS = ("skillforge", "skillopt", "skill-doctor", "skill-bootstrap", "skillify")


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, check=False
    )


class TestCatalog:
    def test_ids_are_unique_and_well_formed(self) -> None:
        ids = [rule.id for rule in RULES]
        assert len(ids) == len(set(ids))
        assert all(re.fullmatch(r"[a-z]+(\.[a-z0-9-]+)+", rule_id) for rule_id in ids)

    def test_every_rule_has_level_source_and_summary(self) -> None:
        for rule in RULES:
            assert rule.level in ("MUST", "SHOULD", "MAY"), rule.id
            assert rule.source.startswith("https://agentskills.io/"), rule.id
            assert "#" in rule.source, rule.id
            assert rule.summary.strip().endswith("."), rule.id
            assert rule.check is None or callable(rule.check), rule.id

    def test_catalog_covers_the_spec_and_all_four_guides(self) -> None:
        pages = {rule.source.split("#", 1)[0] for rule in RULES}
        assert pages == {
            "https://agentskills.io/specification",
            "https://agentskills.io/skill-creation/using-scripts",
            "https://agentskills.io/skill-creation/best-practices",
            "https://agentskills.io/skill-creation/optimizing-descriptions",
            "https://agentskills.io/skill-creation/evaluating-skills",
        }

    def test_every_spec_must_rule_is_automated(self) -> None:
        manual_musts = [rule.id for rule in RULES if rule.level == "MUST" and rule.manual]
        assert manual_musts == []

    def test_limits_come_from_the_shared_constants(self) -> None:
        constants = load("skillforge_constants_for_conformance", "_constants.py")
        check = RULES[0].check
        assert check is not None
        checks = check.__globals__
        assert checks["NAME_MAX_LENGTH"] == constants.NAME_MAX_LENGTH == 64
        assert checks["DESCRIPTION_MAX_LENGTH"] == constants.DESCRIPTION_MAX_LENGTH == 1024
        assert checks["COMPATIBILITY_MAX_LENGTH"] == constants.COMPATIBILITY_MAX_LENGTH == 500
        assert checks["BODY_MAX_LINES"] == constants.BODY_MAX_LINES == 500

    def test_skillify_copy_of_the_limits_agrees(self) -> None:
        text = (SKILLS_DIR / "skillify" / "scripts" / "skillify_verify.py").read_text(
            encoding="utf-8"
        )
        assert "MAX_DESCRIPTION_CHARS = 1024" in text
        assert "MAX_SKILL_LINES = 500" in text


class TestParser:
    def test_anchor_makes_must_rules_not_evaluated(self, tmp_path: Path) -> None:
        skill = make_skill(tmp_path, frontmatter="name: &n release-notes\ndescription: d e f g h\n")
        found = results(skill)
        assert found["spec.frontmatter.mapping"].status == "NOT_EVALUATED"
        assert found["spec.name.present"].status == "NOT_EVALUATED"
        assert conformance.failed(list(found.values()), strict=False)

    def test_comments_quotes_and_block_scalars(self, tmp_path: Path) -> None:
        frontmatter = (
            "# a comment\n"
            "name: 'release-notes'  # trailing\n"
            'description: "Format notes: \\"quoted\\". Use when releasing."\n'
            "license: |\n  MIT\n"
        )
        found = results(make_skill(tmp_path, frontmatter=frontmatter))
        assert found["spec.name.matches-directory"].status == "PASS"
        assert found["spec.frontmatter.known-fields"].status == "PASS"

    def test_tab_indentation_is_a_parse_error(self, tmp_path: Path) -> None:
        skill = make_skill(
            tmp_path, frontmatter="name: release-notes\ndescription: d\nmetadata:\n\tk: v\n"
        )
        assert results(skill)["spec.frontmatter.mapping"].status == "FAIL"

    def test_every_shipped_skill_frontmatter_parses(self) -> None:
        unparsed = []
        for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            status = results(skill_md.parent, "project")["spec.frontmatter.mapping"].status
            if status != "PASS":
                unparsed.append((skill_md.parent.name, status))
        assert unparsed == []


class TestCli:
    def test_list_prints_every_rule(self, tmp_path: Path) -> None:
        proc = _run("--list", cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        for rule in RULES:
            assert rule.id in proc.stdout

    def test_list_json_marks_manual_rules(self, tmp_path: Path) -> None:
        proc = _run("--list", "--format", "json", "--profile", "project", cwd=tmp_path)
        rows = {row["id"]: row for row in json.loads(proc.stdout)["rules"]}
        assert rows["spec.description.what-and-when"]["kind"] == "manual"
        assert rows["spec.name.charset"]["kind"] == "automated"
        assert rows["spec.allowed-tools.string"]["deviation"]

    def test_clean_skill_exits_zero(self, tmp_path: Path) -> None:
        make_skill(tmp_path)
        proc = _run("release-notes", cwd=tmp_path)
        assert proc.returncode == 0, proc.stdout
        assert "need human review" in proc.stdout

    def test_must_failure_exits_one_and_names_the_source(self, tmp_path: Path) -> None:
        make_skill(tmp_path, frontmatter="name: other-name\ndescription: d e f g\n")
        proc = _run("release-notes", cwd=tmp_path)
        assert proc.returncode == 1
        assert "spec.name.matches-directory" in proc.stdout
        assert "https://agentskills.io/specification#name-field" in proc.stdout

    def test_warn_exits_zero_unless_strict(self, tmp_path: Path) -> None:
        make_skill(tmp_path, body="See [gone](references/gone.md).\n")
        assert _run("release-notes", cwd=tmp_path).returncode == 0
        assert _run("release-notes", "--strict", cwd=tmp_path).returncode == 1

    def test_json_output_shape(self, tmp_path: Path) -> None:
        make_skill(tmp_path)
        payload = json.loads(_run("release-notes", "--format", "json", cwd=tmp_path).stdout)
        assert payload["exit_code"] == 0 and payload["profile"] == "spec"
        skill = payload["skills"][0]
        assert {"id", "level", "status", "source", "summary", "problems", "reason"} <= set(
            skill["results"][0]
        )
        assert skill["counts"]["MANUAL"] == sum(1 for rule in RULES if rule.manual)

    def test_manual_flag_lists_guidelines(self, tmp_path: Path) -> None:
        make_skill(tmp_path)
        proc = _run("release-notes", "--manual", cwd=tmp_path)
        assert "practice.gotchas" in proc.stdout

    @pytest.mark.parametrize(
        "args",
        [
            (),
            ("missing-dir",),
            ("release-notes", "--waive", "no.such-rule"),
            ("release-notes", "--profile", "loose"),
            ("release-notes", "--root", "not-a-dir"),
        ],
    )
    def test_usage_errors_exit_two(self, tmp_path: Path, args: tuple[str, ...]) -> None:
        make_skill(tmp_path)
        assert _run(*args, cwd=tmp_path).returncode == 2

    def test_path_outside_root_exits_two(self, tmp_path: Path) -> None:
        make_skill(tmp_path / "outside")
        (tmp_path / "inside").mkdir()
        proc = _run(str(tmp_path / "outside" / "release-notes"), cwd=tmp_path / "inside")
        assert proc.returncode == 2
        assert "outside the root" in proc.stderr

    def test_root_flag_admits_a_path_outside_cwd(self, tmp_path: Path) -> None:
        make_skill(tmp_path / "other")
        (tmp_path / "here").mkdir()
        target = str(tmp_path / "other" / "release-notes")
        proc = _run(target, "--root", str(tmp_path / "other"), cwd=tmp_path / "here")
        assert proc.returncode == 0, proc.stderr

    def test_help_documents_exit_codes(self, tmp_path: Path) -> None:
        text = (SCRIPT_DIR / "conformance.py").read_text(encoding="utf-8")
        assert "Exit codes:" in text
        assert _run("--help", cwd=tmp_path).returncode == 0


class TestRepositoryState:
    @pytest.mark.parametrize("name", BUILDERS)
    def test_skill_builders_conform_under_the_project_profile(self, name: str) -> None:
        found = results(SKILLS_DIR / name, "project")
        blocking = {
            rid: r.problems or r.reason
            for rid, r in found.items()
            if r.status in ("FAIL", "NOT_EVALUATED")
        }
        assert blocking == {}

    @pytest.mark.parametrize("name", [b for b in BUILDERS if b != "skill-bootstrap"])
    def test_skill_builders_have_no_warnings(self, name: str) -> None:
        # skill-bootstrap's body carries the ADR-121 locator lines its contract
        # tests pin in SKILL.md, which keep it over the token estimate.
        found = results(SKILLS_DIR / name, "project")
        warnings = {rid: r.problems for rid, r in found.items() if r.status == "WARN"}
        assert warnings == {}

    def test_cli_runs_from_the_repository_root(self) -> None:
        proc = _run("src/claude/skills/skillforge", "--profile", "project", cwd=PROJECT_ROOT)
        assert proc.returncode == 0, proc.stdout + proc.stderr
