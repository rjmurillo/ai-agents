"""Guards for the template repo-reference gate.

Shipped skill and agent templates are vendored into other repositories, so a
cited issue or PR number is meaningless there and can collide.

Coverage:

- positive: clean templates pass, placeholders pass, ADR ids pass, and the real tree passes.
- negative: each flagged form fails, in skills and in agents.
- edge: a missing tree is a config error, a non-UTF-8 file is skipped, the CLI
  returns ADR-035 exit codes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_template_repo_refs as gate


def _tree(tmp_path: Path, skill: str = "clean text", agent: str = "clean text") -> Path:
    skills = tmp_path / "templates" / "skills"
    agents = tmp_path / "templates" / "agents"
    skills.mkdir(parents=True)
    agents.mkdir(parents=True)
    (skills / "a.SKILL.md.tmpl").write_text(skill, encoding="utf-8")
    (agents / "b.shared.md").write_text(agent, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "text",
    [
        "Fixes the hook (issue #6743).",
        "See Issue #1301 for detail.",
        "Merged in PR #5132.",
        "PRs #12 and #34 agree.",
        "Tracked by Child 1 #1934.",
        "Closed under Issue 722.",
        "Rule lives at (#2205) in the log.",
        "Reuses #5396 ownership.",
        "[x](https://github.com/rjmurillo/ai-agents/pull/6581)",
        "https://github.com/owner/repo/issues/456",
    ],
)
def test_flagged_forms_fail_in_skills_and_agents(tmp_path: Path, text: str) -> None:
    assert gate.validate_template_repo_refs(_tree(tmp_path, skill=text)) is False
    other = tmp_path / "other"
    other.mkdir()
    assert gate.validate_template_repo_refs(_tree(other, agent=text)) is False


@pytest.mark.parametrize(
    "text",
    [
        "Closes #<number> on merge.",
        "github.com/owner/repo/pull/<number>",
        "ADR-042 and ADR-109 apply.",
        "Step #1 then step #2.",
        "Color &#35; and anchor #section.",
        "Pre-PR gate runs first.",
        "Open a PR when ready.",
    ],
)
def test_placeholders_and_non_refs_pass(tmp_path: Path, text: str) -> None:
    assert gate.validate_template_repo_refs(_tree(tmp_path, skill=text, agent=text)) is True


def test_finding_reports_path_line_and_text(tmp_path: Path) -> None:
    root = _tree(tmp_path, skill="ok\nsecond (issue #99) line")
    findings = gate.find_repo_refs(root)
    assert findings == [(Path("templates/skills/a.SKILL.md.tmpl"), 2, "issue #99")]


def test_missing_tree_is_config_error(tmp_path: Path) -> None:
    (tmp_path / "templates" / "skills").mkdir(parents=True)
    assert gate.validate_template_repo_refs(tmp_path) is False
    assert gate.main([str(tmp_path)]) == 2


def test_invalid_root_is_config_error(tmp_path: Path) -> None:
    assert gate.main([str(tmp_path / "missing")]) == 2


def test_non_utf8_file_is_skipped(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "templates" / "skills" / "blob.bin").write_bytes(b"\xff\xfe issue #5")
    assert gate.validate_template_repo_refs(root) is True


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main([str(_tree(tmp_path))]) == 0
    bad = tmp_path / "bad"
    bad.mkdir()
    assert gate.main([str(_tree(bad, skill="PR #7"))]) == 1
    assert "templates/skills/a.SKILL.md.tmpl:1" in capsys.readouterr().err


def test_real_tree_is_clean() -> None:
    assert gate.find_repo_refs(REPO_ROOT) == []
