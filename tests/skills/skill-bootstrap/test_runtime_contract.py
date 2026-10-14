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
import subprocess
from pathlib import Path

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
        match = re.search(r'bootstrap_boundary\.py" (snapshot|plan|verify)\b', line)
        assert match, f"python3 line names no subcommand: {line}"
        text = OPTIONAL_RE.sub("", line)
        for placeholder, value in (
            ("<project>-<lens>", SKILL_NAME),
            ("<new-skill>", SKILL_NAME),
            ("<each authored or updated skill>", SKILL_NAME),
            ("<output-root>", ".claude/skills"),
            ("<project>", "demo"),
            ("<snapshot path>", str(snap)),
            ("<path outside the repo>/snapshot.json", str(snap)),
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
