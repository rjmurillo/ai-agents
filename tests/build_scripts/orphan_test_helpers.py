"""Temp-repository builders shared by the orphan scan and prune tests (issue #7224).

Destructive cases run in temp git repositories, never the real tree.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import orphan_outputs as oo  # noqa: E402

_GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")

_CODEX_YAML = """schemaVersion: "1.0"
provider: "codex"
artifacts:
  skills:
    sourceDir: "src/claude/skills"
    outputDir: "src/codex/skills"
    mode: "directory-copy"
    excludeFilenames: ["AGENTS.md", "CLAUDE.md"]
"""

_CURSOR_YAML = """schemaVersion: "1.0"
provider: "cursor"
artifacts:
  agents:
    sourceDir: "src/claude/agents"
    outputDir: "src/cursor/agents"
    excludeFilenames: ["AGENTS.md", "CLAUDE.md"]
"""

_VSCODE_YAML = """schemaVersion: "1.0"
provider: "vscode"
legacy:
  outputDir: "src/vs-code-agents"
  fileExtension: ".agent.md"
"""

_BINPLACE_YAML = """schemaVersion: "1.0"
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
    link: true
"""

_SKILL_TREES = ("src/claude/skills", "src/codex/skills")
AGENT_TREES = (
    ("src/claude/agents", ".md"),
    ("src/cursor/agents", ".md"),
    ("src/vs-code-agents", ".agent.md"),
)


def git(root: Path, *args: str) -> None:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_VARS}
    cmd = [
        "git",
        "-C",
        str(root),
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "commit.gpgsign=false",
        *args,
    ]
    subprocess.run(cmd, check=True, capture_output=True, env=env)


def symlink_or_skip(link: Path, target: str | Path) -> None:
    """Create ``link`` -> ``target``, or skip where the platform denies symlinks.

    Windows without Developer Mode raises ``OSError``; some Python builds raise
    ``NotImplementedError``. Follows ``test_sync_slim_agents._symlink_or_skip``.
    """
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable; issue #4632: {exc}")


def _skip_unless_git_records_symlinks(root: Path) -> None:
    """Skip when git stored an install link as a regular file (``core.symlinks=false``)."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_VARS}
    done = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-s", "--", ".claude"],
        capture_output=True,
        check=True,
        env=env,
        text=True,
    )
    modes = {line.split()[0] for line in done.stdout.splitlines() if line.strip()}
    if modes != {"120000"}:
        pytest.skip(f"git did not record install links as symlinks (modes: {sorted(modes)})")


def write(path: Path, text: str = "x\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def add_skill(root: Path, name: str, *, with_template: bool = True, support: bool = False) -> None:
    if with_template:
        write(root / "templates" / "skills" / f"{name}.SKILL.md.tmpl", "---\nname: x\n---\n")
    for tree in _SKILL_TREES:
        write(root / tree / name / "SKILL.md", "---\nname: x\n---\n")
        if support and tree == "src/claude/skills":
            write(root / tree / name / "references" / "notes.md")
    symlink_or_skip(root / ".claude" / "skills" / name, f"../../src/claude/skills/{name}")


def add_agent(root: Path, stem: str, *, with_template: bool = True) -> None:
    if with_template:
        write(root / "templates" / "agents" / f"{stem}.shared.md")
        write(root / "templates" / "agents" / f"{stem}.claude.md.tmpl")
        write(root / "templates" / "agents" / f"{stem}.copilot.md.tmpl")
    for tree, suffix in AGENT_TREES:
        write(root / tree / f"{stem}{suffix}", "agent\n")
    symlink_or_skip(
        root / ".claude" / "agents" / f"{stem}.md", f"../../src/claude/agents/{stem}.md"
    )


def make_repo(root: Path) -> Path:
    """Build and commit a small repository with two skills and two agents."""
    root.mkdir()
    write(root / "templates" / "platforms" / "codex.yaml", _CODEX_YAML)
    write(root / "templates" / "platforms" / "cursor.yaml", _CURSOR_YAML)
    write(root / "templates" / "platforms" / "vscode.yaml", _VSCODE_YAML)
    write(root / "templates" / "platforms" / "binplace.yaml", _BINPLACE_YAML)
    add_skill(root, "alpha")
    add_skill(root, "beta")
    add_agent(root, "planner")
    add_agent(root, "critic")
    git(root, "init", "-q")
    git(root, "add", "-A")
    _skip_unless_git_records_symlinks(root)
    git(root, "commit", "-q", "-m", "seed")
    return root


def names(found: oo.OrphanScan, root: Path) -> set[str]:
    return {o.path.relative_to(root.resolve()).as_posix() for o in found.orphans}


def delete_skill_template(root: Path, name: str) -> None:
    (root / "templates" / "skills" / f"{name}.SKILL.md.tmpl").unlink()


def delete_agent_templates(root: Path, stem: str) -> None:
    for path in (root / "templates" / "agents").glob(f"{stem}.*"):
        path.unlink()
