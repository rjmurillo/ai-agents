"""Tests for the ai-agents-change-control classify_change.py script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/ai-agents-change-control/scripts/classify_change.py"

spec = importlib.util.spec_from_file_location("classify_change", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ALLOW = mod.load_allowlist(ROOT)


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd
    )


def _classes(path: str) -> list[str]:
    return mod.classify(path, ALLOW)


def test_ai_agents_change_control_investigation_only_exits_0():
    r = run(
        "--repo",
        str(ROOT),
        ".project-toolkit/critique/a.md",
        ".project-toolkit/architecture/REVIEW-x.md",
    )
    out = json.loads(r.stdout)
    assert r.returncode == 0
    assert out["classes"] == ["investigation-only"]
    assert out["examined"] == 2 and out["allowlist_violations"] == []


def test_mixed_investigation_and_code_exits_1():
    r = run("--repo", str(ROOT), ".project-toolkit/critique/a.md", "scripts/foo.py")
    out = json.loads(r.stdout)
    assert r.returncode == 1
    assert out["allowlist_violations"] == ["scripts/foo.py"]
    assert out["mixed"] is True


def test_class_per_path_kind():
    assert _classes("docs/guide.md") == ["docs-only"]
    assert _classes("lefthook.yml") == ["git-hook-config"]
    assert _classes(".github/workflows/ci.yml") == ["workflow"]
    assert _classes(".project-toolkit/architecture/ADR-999-x.md") == ["adr-governance"]
    assert "plugin-content" in _classes("src/claude/rules/x.md")
    assert "docs-only" not in _classes("src/claude/rules/x.md")
    assert {"code", "plugin-content", "claude-lifecycle-hook"} <= set(
        _classes(".claude/hooks/h.py")
    )
    assert "canonical-source" in _classes("templates/agents/a.shared.md")


def test_unclassified_path_has_no_gates():
    out = mod.analyze(["LICENSE"], ALLOW)
    assert out["paths"][0]["classes"] == ["unclassified"]
    assert out["paths"][0]["gates"] == []


def test_gates_are_deduplicated():
    gates = mod.gates_for(["code", "code"])
    assert len(gates) == len(set(gates))


def test_normalizes_dot_slash_and_backslash():
    assert mod.normalize(".\\scripts\\x.py", ROOT) == "scripts/x.py"
    assert mod.normalize("./a/b.md", ROOT) == "a/b.md"


def test_no_input_exits_2():
    assert run("--repo", str(ROOT)).returncode == 2


def test_two_input_modes_exit_2():
    assert run("--repo", str(ROOT), "--staged", "a.py").returncode == 2


def test_missing_allowlist_module_exits_2(tmp_path):
    assert run("--repo", str(tmp_path), "a.py").returncode == 2


def test_map_prints_every_class():
    r = run("--repo", str(ROOT), "--map")
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["examined"] == len(mod.CLASS_MAP)


def _git_repo(tmp_path: Path) -> Path:
    mods = tmp_path / "scripts/modules"
    mods.mkdir(parents=True)
    (mods / "investigation_allowlist.py").write_text(
        (ROOT / "scripts/modules/investigation_allowlist.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    env = ["-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", *env, "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


def test_staged_reads_git_index(tmp_path):
    repo = _git_repo(tmp_path)
    (repo / "notes.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "notes.md"], cwd=repo, check=True)
    r = run("--repo", str(repo), "--staged")
    out = json.loads(r.stdout)
    assert r.returncode == 0
    assert out["classes"] == ["docs-only"]


def test_staged_empty_exits_0_with_zero_examined(tmp_path):
    repo = _git_repo(tmp_path)
    r = run("--repo", str(repo), "--staged")
    assert r.returncode == 0 and json.loads(r.stdout)["examined"] == 0


def test_base_bad_ref_exits_3(tmp_path):
    repo = _git_repo(tmp_path)
    assert run("--repo", str(repo), "--base", "no-such-ref").returncode == 3


def test_base_option_like_value_exits_2_and_writes_no_file(tmp_path, capsys):
    repo = _git_repo(tmp_path)
    out = tmp_path / "x"
    assert mod.main(["--repo", str(repo), f"--base=--output={out}"]) == 2
    assert "must not start with '-'" in capsys.readouterr().err
    assert not out.exists()
