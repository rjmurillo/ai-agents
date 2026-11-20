"""Guards for the agent and skill reference-page gate.

Rule: ``templates/rules/agent-skill-docs.md``. Past misses this reproduces:

- PR #7424 shipped ``technical-writing`` with no page and no README row.
- PR #7416 shipped ``sol-loop`` and ``llm-council`` with no page.

Coverage:

- positive: skill, page, and README row all present passes; the real tree passes.
- negative: missing page, missing row, orphaned page, row for a missing page,
  and sections out of order each fail, for skills and for agents.
- edge: a missing docs tree is a config error; a skill directory with no
  ``SKILL.md`` is not a skill.
- freshness: an Exit Codes, argument-hint, trigger, or script-name change with
  no page edit warns; the same change with a page edit, or a wording-only
  change, does not.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.validation import check_agent_skill_docs as gate
from tests.build_scripts.orphan_test_helpers import symlink_or_skip

REPO_ROOT = Path(__file__).resolve().parents[2]

_SECTIONS = (
    "When to use it",
    "When not to use it",
    "Quick start",
    "What you get",
    "Advanced use",
    "Where it runs",
    "Related",
)

_SKILL_MD = """\
---
name: {name}
description: Use when you say "do the thing". Do NOT use for other things.
argument-hint: "[target]"
---

# {name}

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Logic error |

## Notes

Plain wording.
"""


def _page_text(name: str, sections: tuple[str, ...] = _SECTIONS) -> str:
    body = "".join(f"## {section}\n\nText.\n\n" for section in sections)
    return f"# {name}\n\n{body}"


def _repo(tmp_path: Path) -> Path:
    for rel in ("src/claude/skills", ".claude/skills", "templates/agents"):
        (tmp_path / rel).mkdir(parents=True)
    for kind in ("skills", "agents"):
        (tmp_path / "docs" / kind).mkdir(parents=True)
        (tmp_path / "docs" / kind / "README.md").write_text(
            f"# {kind}\n\n| Page | Use |\n| --- | --- |\n", encoding="utf-8"
        )
    return tmp_path


def _skill(repo: Path, name: str, tree: str = "src/claude/skills") -> Path:
    path = repo / tree / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(_SKILL_MD.format(name=name), encoding="utf-8")
    return path


def _agent(repo: Path, name: str) -> None:
    (repo / "templates" / "agents" / f"{name}.shared.md").write_text(
        f"---\nname: {name}\n---\n", encoding="utf-8"
    )


def _page(repo: Path, kind: str, name: str, sections: tuple[str, ...] = _SECTIONS) -> None:
    (repo / "docs" / kind / f"{name}.md").write_text(_page_text(name, sections), encoding="utf-8")


def _row(repo: Path, kind: str, name: str) -> None:
    readme = repo / "docs" / kind / "README.md"
    with readme.open("a", encoding="utf-8") as handle:
        handle.write(f"| [`{name}`]({name}.md) | Does {name} |\n")


def _documented_skill(repo: Path, name: str, tree: str = "src/claude/skills") -> Path:
    path = _skill(repo, name, tree)
    _page(repo, "skills", name)
    _row(repo, "skills", name)
    return path


def _paths(report: gate.Report) -> list[str]:
    return sorted(finding.path for finding in report.findings)


# Positive


def test_documented_skill_and_agent_pass(tmp_path):
    repo = _repo(tmp_path)
    _documented_skill(repo, "alpha")
    _documented_skill(repo, "local-only", tree=".claude/skills")
    _agent(repo, "analyst")
    _page(repo, "agents", "analyst")
    _row(repo, "agents", "analyst")

    report = gate.find_page_findings(repo)

    assert report.findings == []
    assert report.examined == 3
    assert gate.main([str(repo)]) == 0


def test_real_repository_tree_passes():
    report = gate.find_page_findings(REPO_ROOT)

    assert report.findings == [], report.findings
    assert report.examined > 100


def test_symlinked_skill_counts_once(tmp_path):
    repo = _repo(tmp_path)
    _documented_skill(repo, "alpha")
    symlink_or_skip(
        repo / ".claude" / "skills" / "alpha",
        repo / "src" / "claude" / "skills" / "alpha",
        target_is_directory=True,
    )

    report = gate.find_page_findings(repo)

    assert report.findings == []
    assert report.examined == 1


# Negative: the past misses


def test_pr_7424_technical_writing_without_page_or_row_fails(tmp_path, capsys):
    repo = _repo(tmp_path)
    _documented_skill(repo, "alpha")
    _skill(repo, "technical-writing")

    report = gate.find_page_findings(repo)

    assert _paths(report) == ["docs/skills/technical-writing.md"]
    assert "no page" in report.findings[0].message
    assert gate.main([str(repo)]) == 1
    assert "docs/skills/technical-writing.md" in capsys.readouterr().err


def test_pr_7416_sol_loop_and_llm_council_without_page_fail(tmp_path):
    repo = _repo(tmp_path)
    _documented_skill(repo, "alpha")
    _skill(repo, "sol-loop")
    _skill(repo, "llm-council")

    report = gate.find_page_findings(repo)

    assert _paths(report) == ["docs/skills/llm-council.md", "docs/skills/sol-loop.md"]


def test_page_without_readme_row_fails(tmp_path):
    repo = _repo(tmp_path)
    _skill(repo, "technical-writing")
    _page(repo, "skills", "technical-writing")

    report = gate.find_page_findings(repo)

    assert _paths(report) == ["docs/skills/README.md"]
    assert "technical-writing" in report.findings[0].message


def test_orphaned_page_for_removed_skill_fails(tmp_path):
    repo = _repo(tmp_path)
    _page(repo, "skills", "old-name")
    _row(repo, "skills", "old-name")

    report = gate.find_page_findings(repo)

    assert _paths(report) == ["docs/skills/old-name.md"]
    assert "no skill" in report.findings[0].message


def test_readme_row_for_missing_page_fails(tmp_path):
    repo = _repo(tmp_path)
    _documented_skill(repo, "alpha")
    _row(repo, "skills", "renamed-away")

    report = gate.find_page_findings(repo)

    assert _paths(report) == ["docs/skills/README.md"]
    assert "renamed-away" in report.findings[0].message


def test_sections_out_of_order_fail(tmp_path):
    repo = _repo(tmp_path)
    _skill(repo, "alpha")
    swapped = ("Quick start", *(s for s in _SECTIONS if s != "Quick start"))
    _page(repo, "skills", "alpha", sections=swapped)
    _row(repo, "skills", "alpha")

    report = gate.find_page_findings(repo)

    assert _paths(report) == ["docs/skills/alpha.md"]
    assert "section" in report.findings[0].message


def test_missing_section_fails(tmp_path):
    repo = _repo(tmp_path)
    _skill(repo, "alpha")
    _page(repo, "skills", "alpha", sections=_SECTIONS[:-1])
    _row(repo, "skills", "alpha")

    assert _paths(gate.find_page_findings(repo)) == ["docs/skills/alpha.md"]


def test_extra_section_between_siblings_passes(tmp_path):
    repo = _repo(tmp_path)
    _skill(repo, "alpha")
    extra = (*_SECTIONS[:3], "Examples", *_SECTIONS[3:])
    _page(repo, "skills", "alpha", sections=extra)
    _row(repo, "skills", "alpha")

    assert gate.find_page_findings(repo).findings == []


def test_section_name_inside_code_fence_is_ignored(tmp_path):
    repo = _repo(tmp_path)
    _skill(repo, "alpha")
    _row(repo, "skills", "alpha")
    sample = "```markdown\n## Related\n## When to use it\n```\n"
    page = repo / "docs" / "skills" / "alpha.md"
    page.write_text(
        _page_text("alpha").replace("## Advanced use\n\nText.", "## Advanced use\n\n" + sample),
        encoding="utf-8",
    )

    assert gate.find_page_findings(repo).findings == []


def test_agent_without_page_fails(tmp_path):
    repo = _repo(tmp_path)
    _agent(repo, "analyst")

    assert _paths(gate.find_page_findings(repo)) == ["docs/agents/analyst.md"]


def test_orphaned_agent_page_fails(tmp_path):
    repo = _repo(tmp_path)
    _page(repo, "agents", "retired")
    _row(repo, "agents", "retired")

    assert _paths(gate.find_page_findings(repo)) == ["docs/agents/retired.md"]


# Edge


def test_directory_without_skill_md_is_not_a_skill(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src" / "claude" / "skills" / "__pycache__").mkdir()

    report = gate.find_page_findings(repo)

    assert report.findings == []
    assert report.examined == 0


def test_missing_docs_tree_is_config_error(tmp_path, capsys):
    repo = _repo(tmp_path)
    (repo / "docs" / "skills" / "README.md").unlink()

    assert gate.main([str(repo)]) == 2
    assert "docs/skills/README.md" in capsys.readouterr().err


def test_main_prints_examined_count(tmp_path, capsys):
    repo = _repo(tmp_path)
    _documented_skill(repo, "alpha")

    assert gate.main([str(repo)]) == 0
    assert "0 finding(s) in 1 agent(s) and skill(s)" in capsys.readouterr().out


def test_validate_returns_typed_fail(tmp_path):
    repo = _repo(tmp_path)
    _skill(repo, "technical-writing")

    outcome = gate.validate_agent_skill_docs(repo)

    assert outcome.state.value == "FAIL"
    assert outcome.findings == 1


# Freshness (advisory)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _committed_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = _repo(tmp_path)
    skill = _documented_skill(repo, "alpha")
    (skill / "scripts").mkdir()
    (skill / "scripts" / "run.py").write_text("print('x')\n", encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A")
    _git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "base")
    return repo, skill


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_exit_codes_change_without_page_edit_warns(tmp_path, capsys):
    repo, skill = _committed_repo(tmp_path)
    _edit(skill / "SKILL.md", "| 1 | Logic error |", "| 1 | Logic error |\n| 2 | Config error |")

    report = gate.find_stale_pages(repo, "HEAD")

    assert report is not None
    assert _paths(report) == ["docs/skills/alpha.md"]
    assert "Exit Codes" in report.findings[0].message
    assert gate.main([str(repo), "--freshness", "--base-ref", "HEAD"]) == 1
    assert "docs/skills/alpha.md" in capsys.readouterr().err


def test_exit_codes_change_with_page_edit_is_quiet(tmp_path):
    repo, skill = _committed_repo(tmp_path)
    _edit(skill / "SKILL.md", "| 1 | Logic error |", "| 1 | Logic error |\n| 2 | Config error |")
    _edit(
        repo / "docs" / "skills" / "alpha.md", "## Related\n\nText.", "## Related\n\nExit 2 added."
    )

    report = gate.find_stale_pages(repo, "HEAD")

    assert report is not None
    assert report.findings == []
    assert report.examined == 1


def test_argument_hint_change_warns(tmp_path):
    repo, skill = _committed_repo(tmp_path)
    _edit(skill / "SKILL.md", 'argument-hint: "[target]"', 'argument-hint: "[target] [--dry-run]"')

    report = gate.find_stale_pages(repo, "HEAD")

    assert report is not None
    assert _paths(report) == ["docs/skills/alpha.md"]
    assert "argument-hint" in report.findings[0].message


def test_trigger_phrase_change_warns(tmp_path):
    repo, skill = _committed_repo(tmp_path)
    _edit(skill / "SKILL.md", '"do the thing"', '"do the other thing"')

    report = gate.find_stale_pages(repo, "HEAD")

    assert report is not None
    assert _paths(report) == ["docs/skills/alpha.md"]
    assert "trigger" in report.findings[0].message


def test_new_script_file_warns(tmp_path):
    repo, skill = _committed_repo(tmp_path)
    (skill / "scripts" / "extra.py").write_text("print('y')\n", encoding="utf-8")

    report = gate.find_stale_pages(repo, "HEAD")

    assert report is not None
    assert _paths(report) == ["docs/skills/alpha.md"]
    assert "extra.py" in report.findings[0].message


def test_wording_only_change_is_quiet(tmp_path):
    repo, skill = _committed_repo(tmp_path)
    _edit(skill / "SKILL.md", "Plain wording.", "Plainer wording.")

    report = gate.find_stale_pages(repo, "HEAD")

    assert report is not None
    assert report.findings == []


def _commit(repo: Path, message: str) -> None:
    _git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t", "add", "-A")
    _git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", message)


def test_change_landed_on_base_after_fork_is_not_blamed(tmp_path):
    repo, skill = _committed_repo(tmp_path)
    _git(repo, "branch", "feature")
    _edit(skill / "SKILL.md", 'argument-hint: "[target]"', 'argument-hint: "[other]"')
    _commit(repo, "main moves on")
    _git(repo, "checkout", "-q", "feature")
    (repo / "notes.txt").write_text("unrelated\n", encoding="utf-8")

    report = gate.find_stale_pages(repo, "main")

    assert report is not None
    assert report.findings == []


def test_page_edited_on_base_after_fork_does_not_hide_branch_change(tmp_path):
    repo, skill = _committed_repo(tmp_path)
    _git(repo, "branch", "feature")
    _edit(repo / "docs" / "skills" / "alpha.md", "## Related\n\nText.", "## Related\n\nMain edit.")
    _commit(repo, "main edits the page")
    _git(repo, "checkout", "-q", "feature")
    _edit(skill / "SKILL.md", "| 1 | Logic error |", "| 1 | Logic error |\n| 2 | Config error |")

    report = gate.find_stale_pages(repo, "main")

    assert report is not None
    assert _paths(report) == ["docs/skills/alpha.md"]


def test_skill_moved_between_trees_is_still_compared(tmp_path):
    repo, skill = _committed_repo(tmp_path)
    moved = repo / ".claude" / "skills" / "alpha"
    skill.rename(moved)
    _edit(moved / "SKILL.md", "| 1 | Logic error |", "| 1 | Logic error |\n| 2 | Config error |")

    report = gate.find_stale_pages(repo, "HEAD")

    assert report is not None
    assert _paths(report) == ["docs/skills/alpha.md"]
    assert "Exit Codes" in report.findings[0].message


def test_freshness_bad_base_ref_returns_none(tmp_path):
    repo, _ = _committed_repo(tmp_path)

    assert gate.find_stale_pages(repo, "no-such-ref") is None


def test_freshness_validate_reports_advisory_fail(tmp_path, monkeypatch):
    repo, skill = _committed_repo(tmp_path)
    _edit(skill / "SKILL.md", "| 1 | Logic error |", "| 1 | Logic error |\n| 2 | Config error |")
    monkeypatch.setattr(gate, "_resolve_default_base_ref", lambda _root: "HEAD")

    outcome = gate.validate_skill_page_freshness(repo)

    assert outcome.state.value == "FAIL"
    assert outcome.reason == "advisory.findings"
