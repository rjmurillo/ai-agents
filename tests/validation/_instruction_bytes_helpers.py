"""Synthetic repository builder shared by the instruction_bytes tests (issue #5400)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.validation.instruction_bytes_fixtures import Fixture

FIXTURE = Fixture("T1", "synthetic", "pkg/mod.py", ("alpha",), ("scout",))


def write(root: Path, rel: str, text: str) -> int:
    """Write ``text`` under ``root`` and return its UTF-8 byte length."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def capability(owns: list[str] | None = None, depends_on: list[str] | None = None) -> str:
    """Render a frontmatter body carrying one valid capability block."""
    lines = ["metadata:", "  capability:", "    kind: reusable-primitive", "    status: active"]
    if owns:
        lines += ["    owns:", *(f"      - {n}" for n in owns)]
    if depends_on:
        lines += ["    depends-on:", *(f"      - {n}" for n in depends_on)]
    return "\n".join(lines) + "\n"


def artifact(name: str, front: str = "", body: str = "body\n") -> str:
    """Return a Markdown artifact with frontmatter and a one-line body."""
    return f"---\nname: {name}\n{front}---\n\n# {name}\n\n{body}"


def add_skill(root: Path, name: str, front: str = "", loaded: bool = True) -> int:
    """Write a skill template and its loaded ``.claude`` copy; return the loaded size."""
    text = artifact(name, front)
    write(root, f"templates/skills/{name}.SKILL.md.tmpl", text)
    return write(root, f".claude/skills/{name}/SKILL.md", text) if loaded else 0


def add_agent(root: Path, name: str, front: str = "") -> int:
    text = artifact(name, front)
    write(root, f"templates/agents/{name}.shared.md", text)
    return write(root, f".claude/agents/{name}.md", text)


def add_rule(root: Path, name: str, paths: list[str] | None, front: str = "") -> int:
    """Write a rule template and its ``.claude/rules`` copy; return the loaded size."""
    path_lines = "" if paths is None else "paths:\n" + "".join(f'  - "{p}"\n' for p in paths)
    text = artifact(name, path_lines + front)
    write(root, f"templates/rules/{name}.md", text)
    return write(root, f".claude/rules/{name}.md", text)


def build_repo(root: Path) -> dict[str, int]:
    """Create a small tree with every canonical group, and return loaded sizes by name.

    alpha depends on beta, beta on gamma, and scout on alpha, so one fixture
    exercises a transitive dependency chain across skills and an agent.
    """
    sizes = {
        "alpha": add_skill(root, "alpha", capability(["alpha-cap"], ["beta-cap"])),
        "beta": add_skill(root, "beta", capability(["beta-cap"], ["gamma-cap"])),
        "gamma": add_skill(root, "gamma", capability(["gamma-cap"])),
        "plain": add_skill(root, "plain"),
        "scout": add_agent(root, "scout", capability(depends_on=["alpha-cap"])),
        "py-rule": add_rule(root, "py-rule", ["**/*.py"]),
        "doc-rule": add_rule(root, "doc-rule", ["docs/**"]),
        "always": add_rule(root, "always", ["**"]),
    }
    sizes["agents-md"] = write(root, "AGENTS.md", "# agents\n")
    sizes["claude-md"] = write(root, "CLAUDE.md", "# claude\n")
    write(root, ".agents/governance/GOV.md", "# governance\n")
    write(root, "src/copilot-cli/skills/alpha/SKILL.md", "generated copy\n")
    write(root, ".github/instructions/py.instructions.md", "---\napplyTo: '**'\n---\nx\n")
    return sizes


def init_git(root: Path) -> None:
    """Initialise a git repository at ``root`` with a fixed identity."""
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    git(root, "config", "commit.gpgsign", "false")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def commit_all(root: Path, message: str = "snapshot") -> str:
    """Stage everything, commit, and return the new commit SHA."""
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")
