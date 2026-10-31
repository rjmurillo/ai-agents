"""Tests for the ai-agents-empirical-probe-toolkit cli_flags_check.py script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "cli_flags_check",
    ROOT / ".claude/skills/ai-agents-empirical-probe-toolkit/scripts/cli_flags_check.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

SCRIPT = (
    "import argparse\n"
    "p = argparse.ArgumentParser()\n"
    "p.add_argument('--dry-run', action='store_true')\n"
    "p.add_argument('--n-runs', type=int)\n"
)


def _repo(tmp_path: Path, skill_text: str, script: str | None = SCRIPT) -> Path:
    if script is not None:
        target = tmp_path / "scripts" / "eval" / "tool.py"
        target.parent.mkdir(parents=True)
        target.write_text(script)
    md = tmp_path / ".claude/skills/ai-agents-empirical-probe-toolkit/SKILL.md"
    md.parent.mkdir(parents=True)
    md.write_text(skill_text)
    return tmp_path


def test_declared_flags_pass(tmp_path, capsys):
    text = "```bash\npython3 scripts/eval/tool.py \\\n  --n-runs 3 --dry-run\n```\n"
    repo = _repo(tmp_path, text)
    assert mod.main(["--repo", str(repo)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["examined"] == 2 and out["undeclared"] == []


def test_undeclared_flag_exits_one(tmp_path, capsys):
    repo = _repo(tmp_path, "Run scripts/eval/tool.py with `--security-critical`.\n")
    assert mod.main(["--repo", str(repo)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["undeclared"][0]["flag"] == "--security-critical"


def test_missing_script_is_a_finding(tmp_path, capsys):
    repo = _repo(tmp_path, "python3 scripts/eval/tool.py --dry-run\n", script=None)
    assert mod.main(["--repo", str(repo)]) == 1
    assert json.loads(capsys.readouterr().out)["undeclared"][0]["reason"] == "script missing"


def test_negation_and_unattributed_flags_skipped(tmp_path, capsys):
    text = "Use --repo first.\nscripts/eval/tool.py has no `--mock` flag.\n"
    repo = _repo(tmp_path, text)
    assert mod.main(["--repo", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out)["examined"] == 0


def test_non_eval_script_resets_attribution(tmp_path, capsys):
    text = "scripts/eval/tool.py then other/x.py --bogus\n"
    repo = _repo(tmp_path, text)
    assert mod.main(["--repo", str(repo)]) == 0


def test_missing_skill_md_exits_two(tmp_path):
    assert mod.main(["--repo", str(tmp_path)]) == 2


def test_bad_argument_exits_two():
    assert mod.main(["--nope"]) == 2


def test_syntax_error_script_exits_two(tmp_path):
    repo = _repo(tmp_path, "scripts/eval/tool.py --dry-run\n", script="def (:\n")
    assert mod.main(["--repo", str(repo)]) == 2


def test_real_skill_flags_declared():
    assert mod.main(["--repo", str(ROOT)]) == 0
