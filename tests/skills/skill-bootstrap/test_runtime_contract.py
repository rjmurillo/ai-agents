"""Run the command lines SKILL.md documents, under the host contract.

The host runs each documented line through a shell, from the consumer
repository, with the plugin root exported in the environment. Unit tests that
import the script cannot catch a wrong path expression or a flag the script
no longer accepts. These tests extract the lines from SKILL.md, fill the
placeholders, and execute them with `bash -c`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from bootstrap_helpers import write

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / ".claude"
SKILL_MD = PLUGIN_ROOT / "skills" / "skill-bootstrap" / "SKILL.md"
LINE_RE = re.compile(r'^\s*(python3 "\$\{COPILOT_PLUGIN_ROOT.*)$', re.MULTILINE)
OPTIONAL_RE = re.compile(r"\s*\[[^\]]*\]")
SKILL_NAME = "demo-change-control"


def _documented_commands(snap: Path) -> dict[str, str]:
    """Return the documented command per subcommand, placeholders filled."""
    commands: dict[str, str] = {}
    for line in LINE_RE.findall(SKILL_MD.read_text(encoding="utf-8")):
        if "bootstrap_boundary.py" not in line:
            continue
        match = re.search(r'bootstrap_boundary\.py" (snapshot|plan|verify)\b', line)
        assert match, f"python3 line names no subcommand: {line}"
        text = OPTIONAL_RE.sub("", line)
        for placeholder, value in (
            ("<project>-<lens>", SKILL_NAME),
            ("<new-skill>", SKILL_NAME),
            ("<output-root>", ".claude/skills"),
            ("<project>", "demo"),
            ("<snapshot path>", str(snap)),
        ):
            text = text.replace(placeholder, value)
        assert "<" not in text, f"unfilled placeholder: {text}"
        commands[match.group(1)] = text
    return commands


def _host_env(plugin_root: Path | None) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")
    }
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    return env


def _bash(command: str, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", command],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_skill_md_documents_one_command_per_subcommand(tmp_path: Path) -> None:
    commands = _documented_commands(tmp_path / "snap.json")

    assert sorted(commands) == ["plan", "snapshot", "verify"]


def test_documented_commands_run_in_sequence_from_a_consumer_repo(
    repo: Path, tmp_path: Path
) -> None:
    snap = tmp_path / "scratch" / "snapshot.json"
    commands = _documented_commands(snap)
    env = _host_env(PLUGIN_ROOT)

    snapshot = _bash(commands["snapshot"], repo, env)
    plan = _bash(commands["plan"], repo, env)
    write(repo, f".claude/skills/{SKILL_NAME}/SKILL.md")
    verify = _bash(commands["verify"], repo, env)

    assert snapshot.returncode == 0, snapshot.stdout + snapshot.stderr
    assert snap.is_file()
    assert plan.returncode == 0, plan.stdout + plan.stderr
    assert verify.returncode == 0, verify.stdout + verify.stderr


def test_documented_verify_fails_when_the_run_writes_outside_the_named_skill(
    repo: Path, tmp_path: Path
) -> None:
    snap = tmp_path / "scratch" / "snapshot.json"
    commands = _documented_commands(snap)
    env = _host_env(PLUGIN_ROOT)
    assert _bash(commands["snapshot"], repo, env).returncode == 0
    write(repo, f".claude/skills/{SKILL_NAME}/SKILL.md")
    write(repo, "docs/stray.md")

    verify = _bash(commands["verify"], repo, env)

    assert verify.returncode == 1, verify.stdout + verify.stderr
    assert "docs/stray.md" in verify.stdout


def test_documented_snapshot_fails_when_no_plugin_root_resolves_the_script(
    tmp_path: Path,
) -> None:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    subprocess.run(["git", "-C", str(consumer), "init", "-q"], check=True)
    snap = tmp_path / "scratch" / "snapshot.json"
    commands = _documented_commands(snap)

    result = _bash(commands["snapshot"], consumer, _host_env(None))

    assert result.returncode != 0
    assert not snap.exists()


PS_ROOT_RE = re.compile(r"^\$root = .*$", re.MULTILINE)
PS_LINE_RE = re.compile(r'^python "\$root/.*$', re.MULTILINE)


def _documented_powershell(snap: Path) -> str:
    """Return the documented PowerShell root line plus its snapshot command."""
    text = SKILL_MD.read_text(encoding="utf-8")
    root_line = PS_ROOT_RE.search(text)
    command = PS_LINE_RE.search(text)
    assert root_line and command, "SKILL.md has no PowerShell form"
    filled = command.group(0).replace("<output-root>", ".claude/skills")
    filled = filled.replace("<snapshot path>", str(snap))
    assert "<" not in filled, f"unfilled placeholder: {filled}"
    return f"{root_line.group(0)}\n{filled}\nexit $LASTEXITCODE"


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")
def test_documented_powershell_form_skips_an_empty_copilot_root(repo: Path, tmp_path: Path) -> None:
    snap = tmp_path / "scratch" / "snapshot.json"
    env = _host_env(PLUGIN_ROOT)
    env["COPILOT_PLUGIN_ROOT"] = ""
    env["PATH"] = os.pathsep.join(
        [str(Path(shutil.which("python3") or "python3").parent), env["PATH"]]
    )
    script = _documented_powershell(snap).replace("python ", "python3 ", 1)

    result = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=repo,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert snap.is_file()


CAPABILITY_LINE_RE = re.compile(r'bootstrap_(mine|forms|drift|eval)\.py" (\w+)')


def _capability_commands(files: dict[str, Path]) -> list[tuple[str, str]]:
    """Return every documented non-boundary command, placeholders filled, in order."""
    commands: list[tuple[str, str]] = []
    for line in LINE_RE.findall(SKILL_MD.read_text(encoding="utf-8")):
        match = CAPABILITY_LINE_RE.search(line)
        if match is None:
            continue
        text = line
        for placeholder, value in (
            ("<new-skill>", SKILL_NAME),
            ("<output-root>", ".claude/skills"),
            ("<generated-prefix>", "src/"),
            ("<plan path>", str(files["plan"])),
            ("<cases path>", str(files["cases"])),
            ("<frozen path>", str(files["frozen"])),
            ("<results path>", str(files["results"])),
        ):
            text = text.replace(placeholder, value)
        assert "<" not in text, f"unfilled placeholder: {text}"
        commands.append((f"{match.group(1)} {match.group(2)}", text))
    return commands


def _seed_capability_run(repo: Path, scratch: Path) -> dict[str, Path]:
    """Write a consumer skill and the out-of-repo run files the documented lines read."""
    import json

    scratch.mkdir(parents=True, exist_ok=True)
    write(repo, f".claude/skills/{SKILL_NAME}/SKILL.md", "Run `README.md` first.\n")
    write(repo, f".claude/skills/{SKILL_NAME}/scripts/gates.py", "print('ok')\n")
    write(
        repo,
        f".claude/skills/{SKILL_NAME}/reverify.json",
        json.dumps({"checks": [{"id": "R1", "kind": "path_exists", "path": "README.md"}]}),
    )
    files = {name: scratch / f"{name}.json" for name in ("plan", "cases", "frozen")}
    files["results"] = scratch / "results.jsonl"
    files["plan"].write_text(
        json.dumps(
            {
                "project": "demo",
                "mode": "workflow",
                "items": [
                    {
                        "id": "I1",
                        "skill": SKILL_NAME,
                        "lens": "change-control",
                        "claim": "Each path maps to its gates",
                        "evidence": ["commit abc1234"],
                        "computable": True,
                        "form": "instrument",
                        "script": "scripts/gates.py",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    files["cases"].write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "C1",
                        "skill": SKILL_NAME,
                        "source": "outcome:demo",
                        "prompt": "Which gates run?",
                        "grader": {"kind": "contains_all", "terms": ["lint"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    files["results"].write_text(
        "\n".join(
            json.dumps({"case_id": "C1", "condition": condition, "output": output})
            for condition, output in (("baseline", "none"), ("with_skill", "lint runs"))
        )
        + "\n",
        encoding="utf-8",
    )
    return files


def test_skill_md_documents_every_capability_subcommand(tmp_path: Path) -> None:
    files = {name: tmp_path / name for name in ("plan", "cases", "frozen", "results")}

    documented = {name for name, _ in _capability_commands(files)}

    assert documented == {
        "mine candidates",
        "mine claims",
        "forms check",
        "eval freeze",
        "eval score",
        "drift check",
    }


def test_documented_capability_commands_run_from_a_consumer_repo(
    repo: Path, tmp_path: Path
) -> None:
    files = _seed_capability_run(repo, tmp_path / "scratch")
    env = _host_env(PLUGIN_ROOT)

    results = [(name, _bash(command, repo, env)) for name, command in _capability_commands(files)]

    failed = [(name, r.returncode, r.stdout + r.stderr) for name, r in results if r.returncode]
    assert failed == [], failed
    assert files["frozen"].is_file()


def test_documented_capability_commands_fail_without_a_plugin_root(
    repo: Path, tmp_path: Path
) -> None:
    files = _seed_capability_run(repo, tmp_path / "scratch")
    shutil.rmtree(repo / ".claude" / "skills" / "skill-bootstrap", ignore_errors=True)

    results = [_bash(command, repo, _host_env(None)) for _, command in _capability_commands(files)]

    assert all(r.returncode != 0 for r in results)
