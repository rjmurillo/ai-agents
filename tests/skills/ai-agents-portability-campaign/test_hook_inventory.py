"""Tests for the ai-agents-portability-campaign hook_inventory.py instrument."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT / ".claude" / "skills" / "ai-agents-portability-campaign" / "scripts" / "hook_inventory.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("hook_inventory", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hi = _load()


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def _track(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)


def test_counts_nested_registrations(tmp_path, capsys):
    settings = {
        "hooks": {
            "SessionStart": [{"hooks": [{"command": "a"}, {"command": "b"}]}],
            "Stop": [{"hooks": [{"command": "c"}]}],
            "Empty": [],
        }
    }
    _write(tmp_path, ".claude/settings.json", json.dumps(settings))
    _write(tmp_path, "src/copilot-cli/hooks/hooks.json", '{"hooks": {}, "version": 1}')
    assert hi.main(["--repo", str(tmp_path), "counts"]) == 0
    out = json.loads(capsys.readouterr().out)
    by_path = {f["path"]: f for f in out["files"]}
    assert by_path[".claude/settings.json"]["events"] == 2
    assert by_path[".claude/settings.json"]["registrations"] == 3
    assert by_path["src/copilot-cli/hooks/hooks.json"]["events"] == 0
    assert by_path[".claude/hooks/hooks.json"]["exists"] is False
    assert out["examined"] == 3


def test_counts_malformed_json_is_config_error(tmp_path):
    _write(tmp_path, ".claude/settings.json", "{not json")
    assert hi.main(["--repo", str(tmp_path), "counts"]) == 2


def test_counts_hooks_not_object_is_config_error(tmp_path):
    _write(tmp_path, ".claude/settings.json", '{"hooks": []}')
    assert hi.main(["--repo", str(tmp_path), "counts"]) == 2


def test_counts_at_head_matches_known_shape(capsys):
    assert hi.main(["--repo", str(ROOT), "counts"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {f["path"] for f in out["files"]} == set(hi.MANIFESTS)


def test_bad_repo_is_config_error(tmp_path):
    assert hi.main(["--repo", str(tmp_path / "nope"), "counts"]) == 2


def test_phase_tests_all_present(tmp_path, capsys):
    _write(tmp_path, "tests/a/test_x.py", "")
    _write(tmp_path, "S.md", "run `uv run pytest tests/a/test_x.py -q`")
    assert hi.main(["--repo", str(tmp_path), "phase-tests", "--skill-md", "S.md"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["missing"] == [] and out["examined"] == 1


def test_phase_tests_reports_missing(tmp_path, capsys):
    _write(tmp_path, "tests/a/test_x.py", "")
    _write(tmp_path, "S.md", "pytest tests/a/test_x.py \\\n  tests/a/test_gone.py -q")
    assert hi.main(["--repo", str(tmp_path), "phase-tests", "--skill-md", "S.md"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["missing"] == ["tests/a/test_gone.py"]


def test_phase_tests_no_paths_is_ok(tmp_path, capsys):
    _write(tmp_path, "S.md", "no tests here")
    assert hi.main(["--repo", str(tmp_path), "phase-tests", "--skill-md", "S.md"]) == 0
    assert json.loads(capsys.readouterr().out)["examined"] == 0


def test_phase_tests_missing_skill_md_is_config_error(tmp_path):
    assert hi.main(["--repo", str(tmp_path), "phase-tests", "--skill-md", "nope.md"]) == 2


def test_qualifiers_same_line_and_paragraph(tmp_path, capsys):
    repo = _git_repo(tmp_path)
    name = hi.SKILL_NAME
    _write(repo, "src/a.md", f"In the ai-agents repository, route through `{name}`.\n")
    _write(repo, "src/b.md", f'In the ai-agents repository, do this:\n`Skill(skill="{name}")`\n')
    _track(repo)
    assert hi.main(["--repo", str(repo), "qualifiers"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["examined"] == 2 and out["unqualified"] == []


def test_qualifiers_flags_unqualified_and_paragraph_break(tmp_path, capsys):
    repo = _git_repo(tmp_path)
    name = hi.SKILL_NAME
    _write(repo, "src/a.md", f"Route through `{name}`.\n")
    _write(repo, "src/b.md", f"In the ai-agents repository.\n\nRoute through `{name}`.\n")
    _track(repo)
    assert hi.main(["--repo", str(repo), "qualifiers"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert sorted(r["path"] for r in out["unqualified"]) == ["src/a.md", "src/b.md"]


def test_qualifiers_ignores_untracked_and_other_trees(tmp_path, capsys):
    repo = _git_repo(tmp_path)
    _write(repo, "docs/a.md", f"`{hi.SKILL_NAME}` bare\n")
    _write(repo, "src/untracked.md", f"`{hi.SKILL_NAME}` bare\n")
    _write(repo, "src/keep.md", "nothing\n")
    subprocess.run(["git", "-C", str(repo), "add", "docs", "src/keep.md"], check=True)
    assert hi.main(["--repo", str(repo), "qualifiers"]) == 0


def test_qualifiers_git_failure_is_exit_3(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(hi.subprocess, "run", boom)
    assert hi.main(["--repo", str(tmp_path), "qualifiers"]) == 3


@pytest.mark.parametrize("cmd", ["counts", "phase-tests", "qualifiers"])
def test_cli_help_works(cmd):
    proc = subprocess.run(
        ["python3", str(SCRIPT), cmd, "--help"], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0
