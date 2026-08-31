"""Tests for the skill routing manifest validator (issue #5384).

Coverage strategy (per `.agents/governance/TESTING-RIGOR.md`): every validator
function gets a positive case, a negative case asserting the specific finding
code, and edge cases (whitespace-only fields, self-reference, intended
inbound-zero). CLI exit codes are asserted by driving ``main(argv)`` and reading
the returned integer (ADR-035: 0 ok, 1 validation, 2 config). I/O is mocked by
building a throwaway repo tree under ``tmp_path`` rather than touching the real
one; a separate class drives the SHIPPED manifest to pin the acceptance
criterion that all 95 canonical skills are classified with zero findings.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import skill_routing_manifest as srm

# ---------------------------------------------------------------------------
# Fixtures: build a throwaway repo tree
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(
    tmp_path: Path,
    skills: dict[str, str],
    manifest_skills: dict,
    *,
    agents: tuple[str, ...] = ("critic",),
    commands: dict[str, str] | None = None,
    scenarios: tuple[str, ...] = (),
    manifest_text: str | None = None,
) -> Path:
    """Create a minimal repo tree and return its root.

    ``skills`` maps a skill name to its SKILL.md body (used for the invocation
    graph). ``manifest_skills`` is the ``skills:`` mapping dumped to YAML unless
    ``manifest_text`` overrides the raw file content.
    """
    for name, body in skills.items():
        _write(tmp_path / ".claude" / "skills" / name / "SKILL.md", body)
    for agent in agents:
        _write(tmp_path / ".claude" / "agents" / f"{agent}.md", f"# {agent}\n")
    for cmd_name, body in (commands or {}).items():
        _write(tmp_path / ".claude" / "commands" / f"{cmd_name}.md", body)
    for scenario in scenarios:
        _write(tmp_path / "tests" / "evals" / "skill-scenarios" / f"{scenario}.json", "{}")
    if manifest_text is not None:
        _write(tmp_path / srm.MANIFEST_RELPATH, manifest_text)
    else:
        import yaml

        _write(
            tmp_path / srm.MANIFEST_RELPATH,
            yaml.safe_dump({"skills": manifest_skills}, sort_keys=True),
        )
    return tmp_path


def _codes(findings: list[srm.Finding]) -> set[str]:
    return {f.code for f in findings}


def _validate_repo(repo: Path) -> list[srm.Finding]:
    manifest = srm.load_manifest(repo / srm.MANIFEST_RELPATH)
    skills = srm.discover_canonical_skills(repo)
    agents = srm.discover_agents(repo)
    commands = srm.discover_commands(repo)
    return srm.validate(manifest, skills, agents, commands)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_discovers_only_dirs_with_skill_md(self, tmp_path: Path) -> None:
        repo = _make_repo(
            tmp_path,
            {"alpha": "# alpha", "beta": "# beta"},
            {"alpha": {"role": "explicit-only", "owner": "user", "rationale": "x"},
             "beta": {"role": "explicit-only", "owner": "user", "rationale": "x"}},
        )
        # A bare directory with no SKILL.md is not a skill.
        (repo / ".claude" / "skills" / "not-a-skill").mkdir()
        assert srm.discover_canonical_skills(repo) == {"alpha", "beta"}

    def test_missing_skills_dir_raises_config_error(self, tmp_path: Path) -> None:
        with pytest.raises(srm.ManifestError):
            srm.discover_canonical_skills(tmp_path)

    def test_agents_exclude_directory_docs(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, {"alpha": "# a"},
                          {"alpha": {"role": "explicit-only", "owner": "user", "rationale": "x"}},
                          agents=("critic", "qa"))
        _write(repo / ".claude" / "agents" / "AGENTS.md", "# doc")
        _write(repo / ".claude" / "agents" / "CLAUDE.md", "# doc")
        assert srm.discover_agents(repo) == {"critic", "qa"}


# ---------------------------------------------------------------------------
# Invocation graph (structural reachability)
# ---------------------------------------------------------------------------


class TestComputeInbound:
    def test_detects_the_three_invocation_forms(self, tmp_path: Path) -> None:
        skills = {
            "caller": 'Skill(skill="callee-a")\nSkill: callee-b\nAgent: callee-c',
            "callee-a": "# a",
            "callee-b": "# b",
            "callee-c": "# c",
        }
        manifest = {
            "caller": {"role": "explicit-only", "owner": "user", "rationale": "x"},
            "callee-a": {"role": "nested-helper", "owner": "caller"},
            "callee-b": {"role": "nested-helper", "owner": "caller"},
            "callee-c": {"role": "nested-helper", "owner": "caller"},
        }
        repo = _make_repo(tmp_path, skills, manifest)
        inbound = srm.compute_inbound(repo, set(skills))
        assert inbound["callee-a"] == {"skill:caller"}
        assert inbound["callee-b"] == {"skill:caller"}
        assert inbound["callee-c"] == {"skill:caller"}

    def test_backtick_wrapped_route_is_detected(self, tmp_path: Path) -> None:
        skills = {"caller": "Skill: `callee`", "callee": "# c"}
        manifest = {
            "caller": {"role": "explicit-only", "owner": "user", "rationale": "x"},
            "callee": {"role": "nested-helper", "owner": "caller"},
        }
        repo = _make_repo(tmp_path, skills, manifest)
        assert srm.compute_inbound(repo, set(skills))["callee"] == {"skill:caller"}

    def test_self_reference_is_not_counted(self, tmp_path: Path) -> None:
        skills = {"loner": 'Skill(skill="loner")'}
        manifest = {"loner": {"role": "explicit-only", "owner": "user", "rationale": "x"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert srm.compute_inbound(repo, set(skills))["loner"] == set()

    def test_command_source_is_recorded(self, tmp_path: Path) -> None:
        skills = {"target": "# t"}
        manifest = {"target": {"role": "lifecycle", "owner": "/build"}}
        repo = _make_repo(tmp_path, skills, manifest,
                          commands={"build": 'Skill(skill="target")'})
        assert srm.compute_inbound(repo, set(skills))["target"] == {"cmd:/build"}


# ---------------------------------------------------------------------------
# Manifest loading (config errors)
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(srm.ManifestError):
            srm.load_manifest(tmp_path / "nope.yaml")

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "m.yaml"
        p.write_text("skills: {: :}", encoding="utf-8")
        with pytest.raises(srm.ManifestError):
            srm.load_manifest(p)

    def test_missing_skills_key_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "m.yaml"
        p.write_text("other: 1", encoding="utf-8")
        with pytest.raises(srm.ManifestError):
            srm.load_manifest(p)

    def test_skills_not_mapping_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "m.yaml"
        p.write_text("skills: [a, b]", encoding="utf-8")
        with pytest.raises(srm.ManifestError):
            srm.load_manifest(p)


# ---------------------------------------------------------------------------
# Validation: positive
# ---------------------------------------------------------------------------


class TestValidatePositive:
    def test_well_formed_manifest_has_no_findings(self, tmp_path: Path) -> None:
        skills = {"front": "# f", "helper": "# h", "gate": "# g"}
        manifest = {
            "front": {"role": "front-door", "owner": "/autoplan"},
            "helper": {"role": "nested-helper", "owner": "front"},
            "gate": {"role": "lifecycle", "owner": "/build"},
        }
        repo = _make_repo(tmp_path, skills, manifest)
        assert _validate_repo(repo) == []

    def test_agent_is_a_valid_nested_helper_owner(self, tmp_path: Path) -> None:
        skills = {"h": "# h"}
        manifest = {"h": {"role": "nested-helper", "owner": "critic"}}
        repo = _make_repo(tmp_path, skills, manifest, agents=("critic",))
        assert _validate_repo(repo) == []

    def test_deprecated_with_replacement_is_valid(self, tmp_path: Path) -> None:
        skills = {"old": "# old"}
        manifest = {"old": {"role": "deprecated", "owner": "user",
                            "replacement": "removed in #9999"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert _validate_repo(repo) == []


# ---------------------------------------------------------------------------
# Validation: negative (one class per finding code)
# ---------------------------------------------------------------------------


class TestValidateNegative:
    def test_unclassified_skill(self, tmp_path: Path) -> None:
        skills = {"a": "# a", "b": "# b"}
        manifest = {"a": {"role": "front-door", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest)
        findings = _validate_repo(repo)
        assert "UNCLASSIFIED" in _codes(findings)
        assert any(f.skill == "b" for f in findings)

    def test_unknown_skill_entry(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "front-door", "owner": "/autoplan"},
                    "ghost": {"role": "front-door", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert "UNKNOWN_SKILL" in _codes(_validate_repo(repo))

    def test_invalid_role(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "backdoor", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert "INVALID_ROLE" in _codes(_validate_repo(repo))

    def test_unknown_invoker(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "nested-helper", "owner": "does-not-exist"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert "UNKNOWN_INVOKER" in _codes(_validate_repo(repo))

    def test_missing_owner(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "front-door"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert "MISSING_OWNER" in _codes(_validate_repo(repo))

    def test_malformed_entry(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": ["not", "a", "mapping"]}
        repo = _make_repo(tmp_path, skills, manifest)
        assert "MALFORMED_ENTRY" in _codes(_validate_repo(repo))

    @pytest.mark.parametrize(
        "entry",
        [
            {"role": "front-door", "owner": "/build"},
            {"role": "lifecycle", "owner": "/autoplan"},
            {"role": "explicit-only", "owner": "/build", "rationale": "x"},
            {"role": "conditional-adjunct", "owner": "user", "trigger": "t"},
            {"role": "nested-helper", "owner": "/build"},
        ],
    )
    def test_contradictory_role(self, tmp_path: Path, entry: dict) -> None:
        skills = {"a": "# a"}
        repo = _make_repo(tmp_path, skills, {"a": entry})
        assert "CONTRADICTORY_ROLE" in _codes(_validate_repo(repo))

    def test_missing_trigger_for_conditional_adjunct(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "conditional-adjunct", "owner": "/build"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert "MISSING_TRIGGER" in _codes(_validate_repo(repo))

    def test_missing_rationale_for_explicit_only(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "explicit-only", "owner": "user"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert "MISSING_RATIONALE" in _codes(_validate_repo(repo))

    def test_missing_replacement_for_deprecated(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "deprecated", "owner": "user"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert "MISSING_REPLACEMENT" in _codes(_validate_repo(repo))


# ---------------------------------------------------------------------------
# Validation: edge cases
# ---------------------------------------------------------------------------


class TestValidateEdge:
    def test_whitespace_only_rationale_is_missing(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "explicit-only", "owner": "user", "rationale": "   "}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert "MISSING_RATIONALE" in _codes(_validate_repo(repo))

    def test_intended_inbound_zero_does_not_fail_validation(self, tmp_path: Path) -> None:
        # A conditional-adjunct whose invoker has not wired it yet (the #5385-5388
        # shape): zero inbound routes, but that is a report signal, not a failure.
        skills = {"adjunct": "# a", "owner-skill": "# o"}
        manifest = {
            "adjunct": {"role": "conditional-adjunct", "owner": "owner-skill",
                        "trigger": "some predicate"},
            "owner-skill": {"role": "front-door", "owner": "/autoplan"},
        }
        repo = _make_repo(tmp_path, skills, manifest)
        assert _validate_repo(repo) == []
        inbound = srm.compute_inbound(repo, set(skills))
        assert inbound["adjunct"] == set()  # inbound-zero
        report = srm.build_report(repo, manifest, set(skills), inbound)
        assert "adjunct (conditional-adjunct, owner owner-skill)" in report

    def test_empty_skills_directory_reports_no_classification(self, tmp_path: Path) -> None:
        # No skill dirs, but a stray manifest entry: it is UNKNOWN_SKILL, not a crash.
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        _write(tmp_path / srm.MANIFEST_RELPATH,
               "skills:\n  ghost: {role: front-door, owner: /autoplan}\n")
        assert "UNKNOWN_SKILL" in _codes(_validate_repo(tmp_path))


# ---------------------------------------------------------------------------
# Resolved manifest + report
# ---------------------------------------------------------------------------


class TestResolveAndReport:
    def test_resolved_entry_carries_derived_fields(self, tmp_path: Path) -> None:
        skills = {"front": "# f"}
        manifest = {"front": {"role": "front-door", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest, scenarios=("front",))
        inbound = srm.compute_inbound(repo, set(skills))
        resolved = srm.resolve_manifest(repo, manifest, inbound)["front"]
        assert resolved["user_facing"] is True
        assert resolved["activation_scenario"] == "tests/evals/skill-scenarios/front.json"
        assert resolved["activation_scenario_present"] is True

    def test_nested_helper_is_not_user_facing(self, tmp_path: Path) -> None:
        skills = {"h": "# h", "o": "# o"}
        manifest = {"h": {"role": "nested-helper", "owner": "o"},
                    "o": {"role": "front-door", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest)
        inbound = srm.compute_inbound(repo, set(skills))
        assert srm.resolve_manifest(repo, manifest, inbound)["h"]["user_facing"] is False

    def test_report_names_the_three_measurements(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "front-door", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest)
        report = srm.build_report(repo, manifest, set(skills),
                                  srm.compute_inbound(repo, set(skills)))
        assert "Structural reachability" in report
        assert "Activation-scenario coverage" in report
        assert "Scored routing accuracy" in report


# ---------------------------------------------------------------------------
# CLI exit codes (ADR-035)
# ---------------------------------------------------------------------------


class TestCliExitCodes:
    def test_valid_manifest_exits_zero(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "front-door", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert srm.main(["--repo-root", str(repo)]) == srm.EXIT_OK

    def test_finding_exits_one(self, tmp_path: Path) -> None:
        skills = {"a": "# a", "b": "# b"}
        manifest = {"a": {"role": "front-door", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert srm.main(["--repo-root", str(repo)]) == srm.EXIT_VALIDATION

    def test_missing_manifest_exits_two(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text("# a", encoding="utf-8")
        assert srm.main(["--repo-root", str(tmp_path)]) == srm.EXIT_CONFIG

    def test_json_format_emits_resolved_manifest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "front-door", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert srm.main(["--repo-root", str(repo), "--format", "json"]) == srm.EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["a"]["role"] == "front-door"
        assert payload["a"]["user_facing"] is True

    def test_wiring_entry_returns_true_when_valid(self, tmp_path: Path) -> None:
        skills = {"a": "# a"}
        manifest = {"a": {"role": "front-door", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert srm.validate_skill_routing_manifest(repo) is True

    def test_wiring_entry_returns_false_on_finding(self, tmp_path: Path) -> None:
        skills = {"a": "# a", "b": "# b"}
        manifest = {"a": {"role": "front-door", "owner": "/autoplan"}}
        repo = _make_repo(tmp_path, skills, manifest)
        assert srm.validate_skill_routing_manifest(repo) is False


# ---------------------------------------------------------------------------
# The SHIPPED manifest (acceptance criterion)
# ---------------------------------------------------------------------------


class TestShippedManifest:
    """Pins the acceptance criteria against the real 95-skill catalog."""

    def test_every_canonical_skill_is_classified_with_no_findings(self) -> None:
        findings = _validate_repo(REPO_ROOT)
        assert findings == [], "\n".join(f.render() for f in findings)

    def test_all_canonical_skills_have_exactly_one_role(self) -> None:
        manifest = srm.load_manifest(REPO_ROOT / srm.MANIFEST_RELPATH)
        skills = srm.discover_canonical_skills(REPO_ROOT)
        # Exactly the canonical set, no extras, no omissions.
        assert set(manifest) == skills
        for name in skills:
            assert manifest[name]["role"] in srm.ROLES

    def test_shipped_manifest_cli_exits_zero(self) -> None:
        assert srm.main(["--repo-root", str(REPO_ROOT)]) == srm.EXIT_OK
