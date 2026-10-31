"""Tests for ai-agents-architecture-contract scripts/contract_probe.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / ".claude"
    / "skills"
    / "ai-agents-architecture-contract"
    / "scripts"
    / "contract_probe.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("ac_contract_probe", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


probe = _load()


def _adr(repo: Path, name: str, body: str) -> None:
    d = repo / ".project-toolkit" / "architecture"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def test_adrs_at_head_resolve_every_cited_adr(capsys):
    assert probe.main(["--repo", str(ROOT), "adrs"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["missing"] == []
    by_id = {r["id"]: r for r in out["adrs"]}
    assert by_id["ADR-007"]["status"] == "superseded"
    assert by_id["ADR-007"]["superseded_by"] == "ADR-106"
    assert out["examined"] >= 20


def test_adrs_explicit_id_skips_comment_lines(tmp_path, capsys):
    _adr(
        tmp_path,
        "ADR-072-x.md",
        "---\n# taste-lint: note\nid: ADR-072\nstatus: accepted\nsuperseded-by: null\n"
        "implemented: false\ndate: 2026-06-09\n---\n",
    )
    assert probe.main(["--repo", str(tmp_path), "adrs", "--adr", "ADR-072"]) == 0
    row = json.loads(capsys.readouterr().out)["adrs"][0]
    assert (row["status"], row["superseded_by"], row["implemented"]) == ("accepted", None, "false")


def test_adrs_missing_file_exits_1(tmp_path, capsys):
    _adr(tmp_path, "ADR-001-x.md", "---\nstatus: accepted\n---\n")
    assert probe.main(["--repo", str(tmp_path), "adrs", "--adr", "ADR-999"]) == 1
    assert json.loads(capsys.readouterr().out)["missing"] == ["ADR-999"]


def test_adrs_bad_id_exits_2(capsys):
    assert probe.main(["--repo", str(ROOT), "adrs", "--adr", "adr72"]) == 2


def test_adrs_without_adr_dir_exits_2(tmp_path):
    assert probe.main(["--repo", str(tmp_path), "adrs"]) == 2


def test_bad_repo_exits_2(tmp_path):
    assert probe.main(["--repo", str(tmp_path / "nope"), "guard"]) == 2


def test_frontmatter_without_block_is_empty():
    assert probe.parse_frontmatter("# no frontmatter\n") == {}


def test_guard_at_head_finds_definition_and_calls(capsys):
    assert probe.main(["--repo", str(ROOT), "guard"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [d["file"] for d in out["definitions"]] == ["build/scripts/build_all.py"]
    assert any(c["file"] == "build/scripts/build_all.py" for c in out["calls"])


def test_guard_without_definition_exits_1(tmp_path, capsys):
    (tmp_path / "build" / "scripts").mkdir(parents=True)
    (tmp_path / "build" / "scripts" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert probe.main(["--repo", str(tmp_path), "guard"]) == 1
    assert json.loads(capsys.readouterr().out)["definitions"] == []


def test_guard_separates_definition_from_call(tmp_path, capsys):
    d = tmp_path / "build" / "scripts"
    d.mkdir(parents=True)
    (d / "a.py").write_text(
        "def assert_no_claude_writes(a):\n    pass\n\nassert_no_claude_writes(1)\n",
        encoding="utf-8",
    )
    assert probe.main(["--repo", str(tmp_path), "guard"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["definitions"] == [{"file": "build/scripts/a.py", "line": 1}]
    assert out["calls"] == [{"file": "build/scripts/a.py", "line": 4}]


def test_adrs_unreadable_file_exits_3(tmp_path):
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    (adr_dir / "ADR-001-x.md").mkdir(parents=True)
    assert probe.main(["--repo", str(tmp_path), "adrs", "--adr", "ADR-001"]) == 3
