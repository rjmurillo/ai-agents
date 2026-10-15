"""CI-collected tests for issue #5947.

The validator pruned ``references/`` directories and had no path kind for the
slash-command directory that ADR-064 retired, so stale citations in skill
handoff prose and in SKILL.md bodies passed. These tests hold both fixes in the
default pytest run: ``references/`` is walked, and a live-guidance citation of
the retired surface is a ``retired_path`` finding unless the line records the
retirement.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_DIR = _REPO_ROOT / ".claude" / "skills" / "orphan-ref-validator" / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))
_spec = importlib.util.spec_from_file_location(
    "_orphan_ref_validator_scan_refs_retired_ci", _SCRIPT_DIR / "scan.py"
)
assert _spec is not None and _spec.loader is not None
_scan = importlib.util.module_from_spec(_spec)
sys.modules["_orphan_ref_validator_scan_refs_retired_ci"] = _scan
_spec.loader.exec_module(_scan)

scan = _scan.scan
main = _scan.main
extract_retired_surface_refs = _scan.extract_retired_surface_refs
retired_surface_applies = _scan.retired_surface_applies

# The retired directory is spelled in two pieces so this file does not cite it.
RETIRED = ".claude" + "/commands"


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for name in ("alpha-skill", "beta-skill"):
        skill = repo / ".claude" / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("# stub\n", encoding="utf-8")
    (repo / ".git").mkdir()
    return repo


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def skill_file(repo: Path, relative: str, text: str) -> Path:
    return write(repo / ".claude" / "skills" / "alpha-skill" / relative, text)


def kinds(result: Any, kind: str) -> list[Any]:
    return [f for f in result.findings if f.kind == kind]


# ---------- references/ is walked ----------


def test_references_file_citing_missing_skill_fails(fake_repo):
    skill_file(fake_repo, "references/handoff.md", "Hand off to the `dead-skill` skill.\n")
    result = scan([fake_repo / ".claude" / "skills"], fake_repo)
    found = kinds(result, "skill_name")
    assert [f.referenced_entity for f in found] == ["dead-skill"]
    assert found[0].target_file.endswith("references/handoff.md")
    assert result.verdict == "CRITICAL_FAIL"


def test_references_file_citing_live_skill_passes(fake_repo):
    skill_file(fake_repo, "references/handoff.md", "Hand off to the `beta-skill` skill.\n")
    result = scan([fake_repo / ".claude" / "skills"], fake_repo)
    assert result.findings == []
    assert result.verdict == "PASS"


def test_templates_directory_is_still_pruned(fake_repo):
    skill_file(fake_repo, "templates/extract.md", "Hand off to the `dead-skill` skill.\n")
    result = scan([fake_repo / ".claude" / "skills"], fake_repo)
    assert result.findings == []


def test_references_line_ignore_directive_suppresses(fake_repo):
    skill_file(
        fake_repo,
        "references/history.md",
        "The `dead-skill` skill was deleted. <!-- orphan-ref-ignore -->\n",
    )
    result = scan([fake_repo / ".claude" / "skills"], fake_repo)
    assert result.findings == []


# ---------- skill-relative scripts resolve from references/ ----------


def test_references_script_resolves_against_owning_skill(fake_repo):
    skill_file(fake_repo, "scripts/helper.py", "# helper\n")
    skill_file(fake_repo, "references/dev.md", "Run `scripts/helper.py` first.\n")
    result = scan([fake_repo / ".claude" / "skills"], fake_repo)
    assert kinds(result, "script_path") == []
    assert result.refs_checked >= 1


def test_references_script_missing_from_owning_skill_fails(fake_repo):
    skill_file(fake_repo, "references/dev.md", "Run `scripts/helper.py` first.\n")
    result = scan([fake_repo / ".claude" / "skills"], fake_repo)
    assert [f.referenced_entity for f in kinds(result, "script_path")] == ["scripts/helper.py"]


def test_script_in_other_subdirectory_does_not_resolve_skill_relative(fake_repo):
    skill_file(fake_repo, "scripts/helper.py", "# helper\n")
    skill_file(fake_repo, "notes/dev.md", "Run `scripts/helper.py` first.\n")
    result = scan([fake_repo / ".claude" / "skills"], fake_repo)
    assert [f.referenced_entity for f in kinds(result, "script_path")] == ["scripts/helper.py"]


def test_references_script_does_not_resolve_against_sibling_skill(fake_repo):
    write(fake_repo / ".claude" / "skills" / "beta-skill" / "scripts" / "helper.py", "# h\n")
    skill_file(fake_repo, "references/dev.md", "Run `scripts/helper.py` first.\n")
    result = scan([fake_repo / ".claude" / "skills"], fake_repo)
    assert len(kinds(result, "script_path")) == 1


# ---------- retired surface ----------


def test_skill_md_citing_retired_command_file_fails(fake_repo):
    target = skill_file(fake_repo, "SKILL.md", f"Run `{RETIRED}/x.md` to start.\n")
    result = scan([target], fake_repo)
    found = kinds(result, "retired_path")
    assert [(f.referenced_entity, f.severity, f.line) for f in found] == [
        (f"{RETIRED}/x.md", "critical", 1)
    ]
    assert "ADR-064" in found[0].recommendation
    assert result.verdict == "CRITICAL_FAIL"


def test_retired_directory_alone_is_a_finding(fake_repo):
    target = skill_file(fake_repo, "SKILL.md", f"Files live under `{RETIRED}/` today.\n")
    found = kinds(scan([target], fake_repo), "retired_path")
    assert [f.referenced_entity for f in found] == [f"{RETIRED}/"]


def test_trailing_sentence_period_is_not_part_of_the_entity(fake_repo):
    target = skill_file(fake_repo, "SKILL.md", f"See {RETIRED}/x.md.\n")
    found = kinds(scan([target], fake_repo), "retired_path")
    assert [f.referenced_entity for f in found] == [f"{RETIRED}/x.md"]


def test_migrated_from_note_is_allowlisted(fake_repo):
    text = f"Migrated from `{RETIRED}/build.md` under a past change.\n"
    target = skill_file(fake_repo, "SKILL.md", text)
    assert kinds(scan([target], fake_repo), "retired_path") == []


def test_line_naming_adr_064_is_allowlisted(fake_repo):
    text = f"There is no `{RETIRED}/`: ADR-064 made skills the single surface.\n"
    target = skill_file(fake_repo, "SKILL.md", text)
    assert kinds(scan([target], fake_repo), "retired_path") == []


def test_allowlist_covers_only_its_own_line(fake_repo):
    text = f"Migrated from `{RETIRED}/build.md`.\nAlso run `{RETIRED}/ship.md`.\n"
    target = skill_file(fake_repo, "SKILL.md", text)
    found = kinds(scan([target], fake_repo), "retired_path")
    assert [(f.line, f.referenced_entity) for f in found] == [(2, f"{RETIRED}/ship.md")]


def test_line_ignore_directive_suppresses_retired_path(fake_repo):
    text = f"Run `{RETIRED}/x.md`. <!-- orphan-ref-ignore -->\n"
    target = skill_file(fake_repo, "SKILL.md", text)
    assert kinds(scan([target], fake_repo), "retired_path") == []


def test_example_placeholder_line_is_skipped(fake_repo):
    target = skill_file(fake_repo, "SKILL.md", f"For example, `{RETIRED}/x.md` was removed.\n")
    assert kinds(scan([target], fake_repo), "retired_path") == []


def test_labeled_citation_block_is_skipped(fake_repo):
    text = f"Treat them as citations, not local paths:\n\n```text\n- {RETIRED}/x.md\n```\n"
    target = skill_file(fake_repo, "SKILL.md", text)
    assert kinds(scan([target], fake_repo), "retired_path") == []


def test_longer_path_ending_in_retired_name_is_not_matched(fake_repo):
    target = skill_file(fake_repo, "SKILL.md", f"Vendor copy at `vendor/{RETIRED}/x.md`.\n")
    assert kinds(scan([target], fake_repo), "retired_path") == []


def test_reference_doc_citation_is_a_finding(fake_repo):
    skill_file(fake_repo, "references/old.md", f"Edit `{RETIRED}/x.md`.\n")
    found = kinds(scan([fake_repo / ".claude" / "skills"], fake_repo), "retired_path")
    assert [f.referenced_entity for f in found] == [f"{RETIRED}/x.md"]


@pytest.mark.parametrize(
    "rel",
    [
        ".claude/skills/a/SKILL.md",
        "src/claude/skills/a/SKILL.md",
        "src/copilot-cli/skills/a/references/r.md",
        ".claude/rules/a.md",
        ".github/instructions/a.instructions.md",
        "src/copilot-cli/instructions/a.instructions.md",
    ],
)
def test_live_guidance_paths_are_checked(rel):
    assert retired_surface_applies(rel) is True


@pytest.mark.parametrize(
    "rel",
    [
        ".project-toolkit/specs/design/DESIGN-001.md",
        ".project-toolkit/architecture/ADR-064-commands-to-skills-migration.md",
        "tests/evals/skills/triage-prompts.json",
        "docs/guide.md",
    ],
)
def test_dated_records_are_not_checked(rel):
    assert retired_surface_applies(rel) is False


def test_python_comment_citing_retired_surface_is_not_a_finding(fake_repo):
    target = skill_file(fake_repo, "scripts/gate.py", f"# moved here from {RETIRED}/cfg.yaml\n")
    assert kinds(scan([target], fake_repo), "retired_path") == []


def test_spec_citing_retired_surface_is_not_a_finding(fake_repo):
    target = write(
        fake_repo / ".project-toolkit" / "specs" / "DESIGN-001.md",
        f"Written before the migration: `{RETIRED}/spec.md`.\n",
    )
    result = scan([target], fake_repo)
    assert kinds(result, "retired_path") == []
    assert result.verdict == "PASS"


def test_extractor_reports_each_distinct_path_once_per_line():
    text = f"`{RETIRED}/a.md` and `{RETIRED}/a.md` and `{RETIRED}/b.md`\n"
    assert list(extract_retired_surface_refs(text)) == [
        (1, f"{RETIRED}/a.md"),
        (1, f"{RETIRED}/b.md"),
    ]


def test_extractor_yields_nothing_for_clean_text():
    assert list(extract_retired_surface_refs("Use `.claude/skills/alpha-skill/`.\n")) == []


def test_cli_emits_retired_path_kind_and_exits_one(fake_repo, capsys):
    target = skill_file(fake_repo, "SKILL.md", f"Run `{RETIRED}/x.md`.\n")
    rc = main(["--repo-root", str(fake_repo), "--targets", str(target)])
    out = capsys.readouterr().out
    envelope = json.JSONDecoder().raw_decode(out)[0]
    assert rc == 1
    assert envelope["Data"]["findings"][0]["kind"] == "retired_path"
    assert "VERDICT: CRITICAL_FAIL" in out


# ---------- this repository ----------


def test_repo_skills_cite_no_retired_surface_outside_history():
    skills = _REPO_ROOT / ".claude" / "skills"
    result = scan([skills], _REPO_ROOT)
    assert kinds(result, "retired_path") == []


def test_repo_references_add_no_findings():
    """Every finding inside a skill's references/ is an intentional, ignored one."""
    skills = _REPO_ROOT / ".claude" / "skills"
    result = scan([skills], _REPO_ROOT)
    in_references = [f for f in result.findings if "/references/" in f.target_file]
    assert in_references == []
