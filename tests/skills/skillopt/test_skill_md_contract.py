"""Bind the skillopt SKILL.md contract to the shipped scripts.

The SKILL.md documents triggers, script paths, exit codes, and verdict names.
These tests read the rendered SKILL.md from every shipped root and run the
bundled scripts from an unrelated working directory, so prose drift goes red.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_REL = Path("skills") / "skillopt"
SHIPPED_ROOTS = (".claude", "src/claude", "src/copilot-cli", "src/codex")
TRIGGERS = (
    "optimize this skill",
    "make this skill better",
    "compress these skills safely",
    "tune this prompt against an eval",
)
VERDICTS = ("ACCEPT_PARETO", "REJECT", "REJECT_UNVERIFIED", "REJECT_NULL_CONTROL")
BUNDLED = (
    "scripts/skillopt.py",
    "scripts/mine_sessions.py",
    "scripts/_skillopt_patching.py",
    "scripts/_skillopt_gates.py",
    "scripts/_skillopt_buffer.py",
    "scripts/_mine_records.py",
    "scripts/_mine_handoff.py",
    "scripts/_mine_sources.py",
    "references/eval-set-format.md",
    "references/slow-section-convention.md",
    "references/mechanism.md",
    "references/cross-machine-mining.md",
    "references/example-eval.json",
    "references/example-incumbent-results.json",
    "references/example-candidate-results.json",
)
EXCLUDED = ("scripts/mine.sh", "baselines", "pilots", "references/candidate-review.md")


def _skill_dir(root: str) -> Path:
    return REPO_ROOT / root / SKILL_REL


def _skill_md(root: str = ".claude") -> str:
    return (_skill_dir(root) / "SKILL.md").read_text(encoding="utf-8")


def _run(script: str, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    path = _skill_dir(".claude") / "scripts" / script
    return subprocess.run(
        [sys.executable, str(path), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _write_json(path: Path, data: object) -> str:
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("root", SHIPPED_ROOTS)
def test_install_exposes_triggers_and_tooling(root: str) -> None:
    skill_dir = _skill_dir(root)
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: skillopt\n")
    for trigger in TRIGGERS:
        assert trigger in text
    for rel in BUNDLED:
        assert (skill_dir / rel).is_file(), rel
    for rel in EXCLUDED:
        assert not (skill_dir / rel).exists(), rel


def test_every_plugin_root_install_is_a_shipped_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT / "scripts" / "validation"))
    from check_plugin_frontmatter_self_containment import plugin_roots

    installed = {root for root in plugin_roots(REPO_ROOT) if _skill_dir(root).is_dir()}
    assert installed, "no plugin root ships skillopt"
    assert installed - set(SHIPPED_ROOTS) == set()


@pytest.mark.parametrize("root", SHIPPED_ROOTS)
def test_shipped_copies_are_byte_identical(root: str) -> None:
    for rel in BUNDLED:
        source = (_skill_dir(".claude") / rel).read_bytes()
        assert (_skill_dir(root) / rel).read_bytes() == source, rel


def test_skill_md_documents_every_verdict_and_boundary() -> None:
    text = _skill_md()
    for verdict in VERDICTS:
        assert verdict in text
    for term in ("ACCEPTED_NOT_DEPLOYED", "skillforge", "context-optimizer", "py -3"):
        assert term in text
    assert "~/Documents" not in text
    assert "SOUL.md" not in text


def test_skill_md_invocations_use_plugin_root_python3() -> None:
    text = _skill_md()
    prefix = (
        'python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/skillopt/scripts/'
    )
    assert prefix + 'skillopt.py" --help' in text
    assert prefix + 'mine_sessions.py" --help' in text


def test_documented_help_runs_from_unrelated_directory(tmp_path: Path) -> None:
    for script in ("skillopt.py", "mine_sessions.py"):
        result = _run(script, "--help", cwd=tmp_path)
        assert result.returncode == 0, result.stderr


def test_worked_example_accepts_from_its_directory() -> None:
    refs = _skill_dir(".claude") / "references"
    result = _run(
        "skillopt.py",
        "pair-gate",
        "--eval",
        "example-eval.json",
        "--incumbent-results",
        "example-incumbent-results.json",
        "--candidate-results",
        "example-candidate-results.json",
        cwd=refs,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["verdict"] == "ACCEPT_PARETO"
    assert report["gains"] == ["t8"]
    assert report["regressions"] == []


def test_documented_exit_codes_for_pair_gate(tmp_path: Path) -> None:
    eval_path = _write_json(tmp_path / "eval.json", {"splits": {"sel": ["a", "b"]}})
    incumbent = _write_json(tmp_path / "inc.json", {"a": True, "b": False})
    regress = _write_json(tmp_path / "reg.json", {"a": False, "b": True})
    unverified = _write_json(tmp_path / "unv.json", {"a": True, "b": "UNVERIFIED"})
    gain = _write_json(tmp_path / "gain.json", {"a": True, "b": True})
    null = _write_json(tmp_path / "null.json", {"a": True, "b": True})

    def gate(candidate: str, *extra: str) -> tuple[int, str]:
        result = _run(
            "skillopt.py",
            "pair-gate",
            "--eval",
            eval_path,
            "--incumbent-results",
            incumbent,
            "--candidate-results",
            candidate,
            *extra,
            cwd=tmp_path,
        )
        verdict = json.loads(result.stdout)["verdict"] if result.stdout else ""
        return result.returncode, verdict

    assert gate(gain) == (0, "ACCEPT_PARETO")
    assert gate(regress) == (1, "REJECT")
    assert gate(unverified) == (1, "REJECT_UNVERIFIED")
    assert gate(gain, "--null-results", null) == (1, "REJECT_NULL_CONTROL")

    empty = _write_json(tmp_path / "empty.json", {"splits": {"sel": []}})
    result = _run(
        "skillopt.py",
        "pair-gate",
        "--eval",
        empty,
        "--incumbent-results",
        incumbent,
        "--candidate-results",
        gain,
        cwd=tmp_path,
    )
    assert result.returncode == 2


def test_documented_exit_codes_for_exposed_selection(tmp_path: Path) -> None:
    eval_path = _write_json(
        tmp_path / "eval.json", {"splits": {"sel": ["a", "b"]}, "exposed": ["b"]}
    )
    results = _write_json(tmp_path / "r.json", {"a": True, "b": True})
    result = _run(
        "skillopt.py",
        "pair-gate",
        "--eval",
        eval_path,
        "--incumbent-results",
        results,
        "--candidate-results",
        results,
        cwd=tmp_path,
    )
    assert result.returncode == 2


def test_documented_exit_codes_for_apply_and_buffer(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_bytes(b"# Skill\n\n## Rules\n")
    original = target.read_bytes()
    patches = _write_json(tmp_path / "p.json", [{"op": "append", "text": "- new rule"}])
    evals = _write_json(tmp_path / "eval.json", {"splits": {"sel": ["t1"]}})

    same = _run(
        "skillopt.py",
        "apply",
        "--eval",
        evals,
        "--skill",
        str(target),
        "--patches",
        patches,
        "--budget",
        "1",
        "--out",
        str(target),
        cwd=tmp_path,
    )
    assert same.returncode == 2
    assert target.read_bytes() == original

    over = _run(
        "skillopt.py",
        "apply",
        "--eval",
        evals,
        "--skill",
        str(target),
        "--patches",
        patches,
        "--budget",
        "0",
        "--out",
        str(tmp_path / "c.md"),
        cwd=tmp_path,
    )
    assert over.returncode == 2

    buffer = str(tmp_path / "rejected.jsonl")
    novel = _run(
        "skillopt.py", "buffer-check", "--buffer", buffer, "--patches", patches, cwd=tmp_path
    )
    assert (novel.returncode, novel.stdout.strip()) == (1, "NOVEL")
    added = _run(
        "skillopt.py",
        "buffer-add",
        "--buffer",
        buffer,
        "--patches",
        patches,
        "--score",
        "0.5",
        "--incumbent",
        "0.5",
        cwd=tmp_path,
    )
    assert added.returncode == 0
    known = _run(
        "skillopt.py", "buffer-check", "--buffer", buffer, "--patches", patches, cwd=tmp_path
    )
    assert (known.returncode, known.stdout.strip()) == (0, "KNOWN-BAD")


def test_documented_exit_codes_for_scalar_gate_and_hash(tmp_path: Path) -> None:
    accept = _run("skillopt.py", "gate", "--candidate", "0.6", "--incumbent", "0.5", cwd=tmp_path)
    tie = _run("skillopt.py", "gate", "--candidate", "0.5", "--incumbent", "0.5", cwd=tmp_path)
    assert (accept.returncode, accept.stdout.strip()) == (0, "ACCEPT")
    assert (tie.returncode, tie.stdout.strip()) == (1, "REJECT")

    target = tmp_path / "t.md"
    target.write_bytes(b"x")
    mismatch = _run("skillopt.py", "hash", str(target), "--expect", "0" * 64, cwd=tmp_path)
    assert mismatch.returncode == 1
    assert "MISMATCH" in mismatch.stdout
