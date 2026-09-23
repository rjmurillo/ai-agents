"""Tests for always-on skill accounting in instruction_budget.py (issue #4871).

A skill under ``.claude/skills/`` whose frontmatter ``description`` declares
unconditional loading is effective always-on context. These tests prove it
counts toward every language budget, and that body-only mentions do not.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.instruction_budget as ib


def _write_rule(root: Path, name: str, apply_to: str, body: str = "body\n") -> int:
    """Create an instruction file and return its UTF-8 byte length."""
    inst_dir = root / ib.INSTRUCTIONS_SUBDIR
    inst_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\napplyTo: {apply_to}\n---\n\n# {name}\n\n{body}"
    (inst_dir / f"{name}.instructions.md").write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


def _write_skill(root: Path, name: str, description: str, body: str = "Body text.\n") -> int:
    """Create a `.claude/skills/<name>/SKILL.md` and return its UTF-8 byte length."""
    skill_dir = root / ib.SKILLS_SUBDIR / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


def _result(total: int, ceiling: int, reserve: int = 0) -> ib.ExtensionResult:
    """Build an ExtensionResult directly, bypassing the filesystem."""
    return ib.ExtensionResult(
        extension=".md",
        matched_files=("a.instructions.md",),
        total_bytes=total,
        estimated_tokens=total // 4,
        ceiling_bytes=ceiling,
        reserve_bytes=reserve,
    )

# --------------------------------------------------------------------------
# always-on skill accounting (issue #4871)
#
# A skill under .claude/skills/ whose own frontmatter `description` declares
# unconditional loading ("Load at the start of EVERY task.") is effective
# always-on context, no different from a rule matched by a universal
# `applyTo`. It must count toward the same per-extension budget instead of
# dodging it by living outside .github/instructions/ and .claude/rules/.
# --------------------------------------------------------------------------


def test_always_on_skill_is_counted_in_every_extension(tmp_path: Path) -> None:
    size = _write_skill(tmp_path, "you", "Load at the start of EVERY task.")
    results = ib.evaluate(tmp_path, ib.DEFAULT_CEILINGS_BYTES)
    assert results  # sanity: DEFAULT_CEILINGS_BYTES is non-empty
    for result in results:
        assert ".claude/skills/you/SKILL.md" in result.matched_files
        idx = result.matched_files.index(".claude/skills/you/SKILL.md")
        assert result.matched_activation[idx] == "skill-description"
        assert result.total_bytes >= size


def test_ordinary_skill_with_every_task_only_in_body_is_not_counted(
    tmp_path: Path,
) -> None:
    _write_skill(
        tmp_path,
        "build",
        "Implement a planned change test-first with atomic commits.",
        body="Every task has a done definition before it is closed.\n",
    )
    results = ib.evaluate(tmp_path, {".py": 10_000})
    assert results[0].matched_files == ()
    assert results[0].total_bytes == 0


def test_always_on_declaration_on_continuation_line_is_counted(tmp_path: Path) -> None:
    (tmp_path / ib.INSTRUCTIONS_SUBDIR).mkdir(parents=True)
    skill_dir = tmp_path / ib.SKILLS_SUBDIR / "you"
    skill_dir.mkdir(parents=True)
    content = (
        "---\nname: you\ndescription: Personal profile.\n"
        "  Load at the start of\n  EVERY task.\n---\n\nbody\n"
    )
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    results = ib.evaluate(tmp_path, {".py": 10_000})
    assert results[0].matched_files == (".claude/skills/you/SKILL.md",)
    assert results[0].total_bytes == len(content.encode("utf-8"))


def test_non_string_skill_description_fails_closed(tmp_path: Path) -> None:
    (tmp_path / ib.INSTRUCTIONS_SUBDIR).mkdir(parents=True)
    skill_dir = tmp_path / ib.SKILLS_SUBDIR / "odd"
    skill_dir.mkdir(parents=True)
    content = "---\nname: odd\ndescription:\n  - Load on every task\n---\n\nbody\n"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    with pytest.raises(ib.MalformedSkillFrontmatterError):
        ib.evaluate(tmp_path, {".py": 10_000})


def test_no_claude_skills_directory_still_works(tmp_path: Path) -> None:
    _write_rule(tmp_path, "universal", "'**'")
    files = ib.load_instruction_files(tmp_path)
    assert [f for f in files if f.activation == "skill-description"] == []


def test_malformed_skill_frontmatter_raises(tmp_path: Path) -> None:
    # Fail closed (issue #4871), mirroring UnsupportedApplyToError for
    # instruction files: an unparseable description cannot be ruled out as an
    # always-on declaration, so it must not silently score as zero bytes.
    skill_dir = tmp_path / ib.SKILLS_SUBDIR / "broken"
    skill_dir.mkdir(parents=True)
    broken = "---\nname: broken\nno closing delimiter\n"
    (skill_dir / "SKILL.md").write_text(broken, encoding="utf-8")
    with pytest.raises(ib.MalformedSkillFrontmatterError):
        ib.evaluate(tmp_path, {".py": 10_000})


def test_main_returns_2_on_malformed_skill_frontmatter(tmp_path: Path) -> None:
    _write_rule(tmp_path, "universal", "'**'")
    skill_dir = tmp_path / ib.SKILLS_SUBDIR / "broken"
    skill_dir.mkdir(parents=True)
    broken = "---\nname: broken\nno closing delimiter\n"
    (skill_dir / "SKILL.md").write_text(broken, encoding="utf-8")
    assert ib.main(["--path", str(tmp_path)]) == 2


@pytest.mark.parametrize(
    "description",
    [
        "Load at the start of EVERY task.",
        "Runs every session before anything else.",
        "Fires on every turn, no trigger needed.",
        "Handled on every request automatically.",
        "Injected on every prompt by the harness.",
        "Loaded every conversation without being asked.",
        "Always load this before doing anything else.",
        "This skill is always loaded by the harness.",
        "loaded at the start of every task, no exceptions.",
        "Read before answering any question.",
        "on every task the harness re-runs this skill.",
    ],
)
def test_always_on_skill_pattern_positive_cases(description: str) -> None:
    assert ib._skill_declares_always_on(description) is True


@pytest.mark.parametrize(
    "description",
    [
        "Use when you say build this or implement this slice.",
        "Runs every time you deploy to production.",
        "Load this skill manually when needed for ADRs.",
        "A comprehensive skill for many tasks and requests.",
        "Helps write skill descriptions well.",
        "Triggers when the user mentions every quarter's roadmap.",
        "",
    ],
)
def test_always_on_skill_pattern_negative_cases(description: str) -> None:
    assert ib._skill_declares_always_on(description) is False


def test_json_output_carries_activation_for_skill_matches() -> None:
    result = ib.ExtensionResult(
        extension=".py",
        matched_files=("a.instructions.md", ".claude/skills/you/SKILL.md"),
        matched_activation=("applyTo", "skill-description"),
        total_bytes=100,
        estimated_tokens=25,
        ceiling_bytes=1000,
    )
    payload = json.loads(ib.format_json([result]))
    sources = payload[0]["matched_sources"]
    assert sources == [
        {"name": "a.instructions.md", "activation": "applyTo"},
        {"name": ".claude/skills/you/SKILL.md", "activation": "skill-description"},
    ]


def test_json_output_defaults_activation_when_not_supplied() -> None:
    # A result built before issue #4871 (or by hand, as `_result()` does above)
    # carries no matched_activation. format_json must not crash on the gap.
    payload = json.loads(ib.format_json([_result(900, 1000)]))
    assert payload[0]["matched_sources"] == [
        {"name": "a.instructions.md", "activation": "applyTo"}
    ]


def test_main_json_output_reports_skill_source_end_to_end(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_rule(tmp_path, "universal", "'**'")
    _write_skill(tmp_path, "you", "Load at the start of EVERY task.")
    code = ib.main(["--path", str(tmp_path), "--format", "json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    py_result = next(r for r in payload if r["extension"] == ".py")
    assert ".claude/skills/you/SKILL.md" in py_result["matched_files"]
    skill_source = next(
        s for s in py_result["matched_sources"] if s["name"] == ".claude/skills/you/SKILL.md"
    )
    assert skill_source["activation"] == "skill-description"
