"""Tests for the ai-agents-generation-and-release generator_inventory.py script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".claude/skills/ai-agents-generation-and-release/scripts/generator_inventory.py"

spec = importlib.util.spec_from_file_location("generator_inventory", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

BUILD_ALL = '''"""Doc.

Exit 2 has three producers.
"""
GENERATORS: list = [
    ("agents", f),
    ("hooks", g),
]
OWNED_PREFIXES: tuple[str, ...] = (
    "src/",
    "docs/x.md",
)
'''

BINPLACE = """schemaVersion: "1.0"
rows:
  - class: agents
    source: templates/agents
    plugin_tree: src/claude/agents
    install_tree: .claude/agents
    link: true
  - class: skills
    source: templates/skills
    plugin_tree: src/claude/skills
    install_tree: .claude/skills
    compile: skill_templates
    link: true
  - class: settings
    source: templates/hooks/settings.tmpl
    plugin_tree: null
    install_tree: .claude/settings.json
    compile: hook_templates
"""


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "build/scripts").mkdir(parents=True)
    (tmp_path / "build/scripts/build_all.py").write_text(BUILD_ALL, encoding="utf-8")
    (tmp_path / "templates/platforms").mkdir(parents=True)
    (tmp_path / "templates/platforms/binplace.yaml").write_text(BINPLACE, encoding="utf-8")
    skills = tmp_path / "templates/skills"
    skills.mkdir(parents=True)
    (skills / "a.SKILL.md.tmpl").write_text("---\nname: a\n---\nbody\n", encoding="utf-8")
    (skills / "b.SKILL.md.tmpl").write_text(
        "---\nname: b\nmetadata:\n  distribution: repo-local\n---\nbody\n", encoding="utf-8"
    )
    return tmp_path


def test_generators_lists_order_and_prefixes(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert mod.main(["--repo", str(repo), "generators"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [g["name"] for g in out["generators"]] == ["agents", "hooks"]
    assert out["owned_prefixes"] == ["src/", "docs/x.md"]
    assert out["exit2_producers"] == "three"
    assert out["examined"] == 4


def test_generators_missing_file_exits_2(tmp_path, capsys):
    assert mod.main(["--repo", str(tmp_path), "generators"]) == 2


def test_generators_unparseable_exits_2(tmp_path):
    (tmp_path / "build/scripts").mkdir(parents=True)
    (tmp_path / "build/scripts/build_all.py").write_text("def (:", encoding="utf-8")
    assert mod.main(["--repo", str(tmp_path), "generators"]) == 2


def test_generators_at_head_matches_build_all(capsys):
    assert mod.main(["--repo", str(ROOT), "generators"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["generator_count"] == len(out["generators"]) >= 7
    assert "src/" in out["owned_prefixes"]


def test_path_canonical_generated_and_link(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert mod.main(["--repo", str(repo), "path", "templates/agents/x.shared.md"]) == 0
    assert json.loads(capsys.readouterr().out)["role"] == "canonical"
    assert mod.main(["--repo", str(repo), "path", "./src/claude/agents/x.md"]) == 0
    assert json.loads(capsys.readouterr().out)["role"] == "generated"
    assert mod.main(["--repo", str(repo), "path", ".claude/agents/x.md"]) == 0
    assert json.loads(capsys.readouterr().out)["role"] == "link"
    assert mod.main(["--repo", str(repo), "path", ".claude/settings.json"]) == 0
    assert json.loads(capsys.readouterr().out)["role"] == "binplaced-copy"


def test_path_owned_prefix_fallback(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert mod.main(["--repo", str(repo), "path", "docs/x.md"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["role"] == "generated"
    assert out["owned_prefix"] == "docs/x.md"


def test_path_unmapped_exits_1(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert mod.main(["--repo", str(repo), "path", "nowhere/file.txt"]) == 1
    assert json.loads(capsys.readouterr().out)["role"] is None


def test_path_repo_local_skill_flagged(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert mod.main(["--repo", str(repo), "path", ".claude/skills/b/SKILL.md"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["repo_local_skill"] is True
    assert out["role"] == "repo-local-rendered"
    assert mod.main(["--repo", str(repo), "path", ".claude/skills/a/SKILL.md"]) == 0
    assert json.loads(capsys.readouterr().out)["repo_local_skill"] is False


def test_skills_counts_repo_local(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert mod.main(["--repo", str(repo), "skills"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["templates"], out["shipped"], out["repo_local"]) == (2, 1, ["b"])


def test_skills_missing_dir_exits_2(tmp_path):
    assert mod.main(["--repo", str(tmp_path), "skills"]) == 2


def test_gates_at_head_all_wired(capsys):
    assert mod.main(["--repo", str(ROOT), "gates"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["unwired"] == 0
    jobs = {g["id"]: [w["job"] for w in g["wired"]] for g in out["gates"]}
    assert "build-all-staleness" in jobs["build-all-staleness"]


def test_gates_empty_repo_exits_1(tmp_path, capsys):
    assert mod.main(["--repo", str(tmp_path), "gates"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["unwired"] == len(out["gates"])


def test_gates_ignores_comment_and_path_filter_lines(tmp_path, capsys):
    wf = tmp_path / ".github/workflows"
    wf.mkdir(parents=True)
    needle = "build_all.py --check"
    (wf / "validate-generated-agents.yml").write_text(
        f"jobs:\n  build-all-staleness:\n    steps:\n      # {needle}\n      - '{needle}'\n",
        encoding="utf-8",
    )
    mod.main(["--repo", str(tmp_path), "gates"])
    gates = {g["id"]: g for g in json.loads(capsys.readouterr().out)["gates"]}
    assert gates["build-all-staleness"]["missing"]


def test_gates_reports_enclosing_job(tmp_path, capsys):
    wf = tmp_path / ".github/workflows"
    wf.mkdir(parents=True)
    (wf / "validate-generated-agents.yml").write_text(
        "jobs:\n  build-all-staleness:\n    steps:\n"
        "      - run: uv run python build/scripts/build_all.py --check\n",
        encoding="utf-8",
    )
    mod.main(["--repo", str(tmp_path), "gates"])
    gates = {g["id"]: g for g in json.loads(capsys.readouterr().out)["gates"]}
    assert gates["build-all-staleness"]["wired"][0]["job"] == "build-all-staleness"


def test_cli_help_and_bad_args():
    ok = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert ok.returncode == 0
    bad = subprocess.run([sys.executable, str(SCRIPT), "nonsense"], capture_output=True, text=True)
    assert bad.returncode == 2


def test_bad_repo_exits_2(tmp_path):
    assert mod.main(["--repo", str(tmp_path / "nope"), "skills"]) == 2
