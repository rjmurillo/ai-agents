"""Tests for scripts/validation/check_host_neutral_dispatch.py (issue #7226)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_host_neutral_dispatch.py"
sys.path.insert(0, str(SCRIPT.parent))

import check_host_neutral_dispatch as gate

CLEAN_SKILL = (
    "---\nname: demo\nallowed-tools: Task, AskUserQuestion\n---\n"
    "# Demo\n\nDelegate to the `qa` agent: You are a QA engineer.\n"
)


def _repo(tmp_path: Path, codex_body: str = CLEAN_SKILL, muse_body: str = CLEAN_SKILL) -> Path:
    for tree, body in (("codex", codex_body), ("muse", muse_body)):
        skill = tmp_path / "src" / tree / "skills" / "demo"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(body, encoding="utf-8")
    return tmp_path


def test_clean_trees_exit_zero_and_print_examined_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)

    code = gate.main(["--repo-root", str(root)])

    assert code == 0
    assert "0 violation(s) in 2 files examined" in capsys.readouterr().out


@pytest.mark.parametrize(
    "line",
    [
        'Task(subagent_type="qa"): You are a QA engineer.',
        '`Task(subagent_type="analyst")`: Read the tiers.',
        "Decide the prompt with AskUserQuestion:",
    ],
)
def test_bare_claude_tool_call_fails(tmp_path: Path, line: str) -> None:
    root = _repo(tmp_path, codex_body=f"# Demo\n\n{line}\n")

    assert gate.main(["--repo-root", str(root)]) == 1


def test_fenced_task_block_fails(tmp_path: Path) -> None:
    body = '# Demo\n\n```python\nTask(subagent_type="critic", prompt="""\nReview.\n""")\n```\n'
    root = _repo(tmp_path, muse_body=body)

    assert gate.main(["--repo-root", str(root)]) == 1


def test_python_script_printing_bare_task_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    script = root / "src" / "codex" / "skills" / "demo" / "hint.py"
    script.write_text("print('  Task(subagent_type=\"security\")')\n", encoding="utf-8")

    assert gate.main(["--repo-root", str(root)]) == 1


@pytest.mark.parametrize(
    "line",
    [
        "class RunnableTask(Protocol):",
        "_Task(name)",
        'Claude Code: `Task` with `subagent_type="qa"`; Codex `spawn_agent`.',
        "Use the host's ask tool (Claude Code: `AskUserQuestion`) when it applies.",
        "print('(Claude Code: Task(subagent_type=\"security\"); Codex: spawn_agent)')",
    ],
)
def test_attributed_or_unrelated_lines_pass(tmp_path: Path, line: str) -> None:
    root = _repo(tmp_path, codex_body=f"# Demo\n\n{line}\n")

    assert gate.main(["--repo-root", str(root)]) == 0


def test_frontmatter_is_skipped_but_body_after_it_is_scanned(tmp_path: Path) -> None:
    body = "---\nallowed-tools: AskUserQuestion\n---\n# Demo\n\nUse AskUserQuestion now.\n"
    root = _repo(tmp_path, codex_body=body)

    assert gate.scan_file(root / "src" / "codex" / "skills" / "demo" / "SKILL.md") == [
        (6, "AskUserQuestion")
    ]


def test_missing_tree_is_a_config_error(tmp_path: Path) -> None:
    (tmp_path / "src" / "codex").mkdir(parents=True)

    assert gate.main(["--repo-root", str(tmp_path)]) == 2


def test_cli_exit_code_reaches_the_process(tmp_path: Path) -> None:
    root = _repo(tmp_path, codex_body='# Demo\n\nTask(subagent_type="qa")\n')

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert proc.returncode == 1
    assert "src/codex/skills/demo/SKILL.md:3: bare Task(" in proc.stdout


def test_shipped_trees_are_clean() -> None:
    assert gate.main(["--repo-root", str(REPO_ROOT)]) == 0
