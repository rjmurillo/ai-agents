"""Read one skill at one git ref, for the ADR-127 evidence check.

``check_skill_rewrite_evidence.py`` owns the gate. This module owns the
read-only git access, the prompt surface, the ``metadata.shape`` and
``allowed-tools`` frontmatter, the ``reference`` grant allowlist, and the
moved-line count behind trigger 4.
"""

from __future__ import annotations

import difflib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SHAPES = frozenset({"driver", "reference"})
_SKILL_DIRS = ("src/claude/skills/{n}", ".claude/skills/{n}")


# Trigger 4: at least this many SKILL.md lines of at least this length must
# reappear verbatim in references/. Measured on 400 first-parent commits of
# main to c0b72f8539 (2026-11-25): 5 skill changes in 4 commits fire. In
# each, SKILL.md shrank and a reference file gained the removed lines.
MOVE_MIN_LINES = 3
MOVE_MIN_CHARS = 32

# A `reference` skill may hold only these grants (ADR-127 decision 1). An
# allowlist, not a denylist: a denylist of push and PR-write forms leaked
# `git -C . push`, `uv:*`, and list-form grants in review.
# Delegation tools (Task, Agent) are out: a subagent can hold any grant.
# Working-tree writes stay in, since ADR-127 decision 1 says a file write
# does not make a skill a driver; a write beside any Bash grant still fails.
_REFERENCE_TOOLS = frozenset(
    {
        "Read",
        "Grep",
        "Glob",
        "LS",
        "Skill",
        "TodoWrite",
        "Write",
        "Edit",
        "MultiEdit",
        "NotebookEdit",
        "WebFetch",
        "WebSearch",
        "AskUserQuestion",
    }
)
_READ_MCP = re.compile(r"^mcp__[\w-]+__(?:get|list|read|search|find|query)[\w-]*$")
_MCP_WRITE_WORD = re.compile(r"replace|write|create|delete|update|edit|set|add|insert|rename|move")
_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
_GRANT = re.compile(r"(?P<tool>[A-Za-z][\w.-]*)(?:\((?P<inner>[^)]*)\))?")
_READ_BASH = re.compile(
    r"^(?:git (?:diff|log|show|status|rev-parse|ls-files|ls-tree|merge-base|blame|cat-file)"
    r"|git branch --show-current|date|ls|wc|python3 -m json\.tool)(?:[: ]|$)"
)
_INTERPRETER = r"(?:python3|uv run --frozen python)(?: -I)?\s*:?\s*"
# A Bash grant holding a path climb or a shell operator can chain past the
# command it names, so it never counts as read-only. `git diff --output`
# writes a file and `--ext-diff` runs a program. This reads the grant text
# only: a `*` in a grant still lets the model add these flags at run time.
_UNSAFE_BASH = re.compile(
    r"\.\.|[;&|`<>]|\$\(|\s-O|--output|--ext-diff|--textconv|--open-files-in-pager"
)


class GitError(RuntimeError):
    """A git command failed; the check cannot see the repository state."""


class Git:
    """Read-only git access rooted at one repository."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _run(
        self, *args: str, ok_codes: tuple[int, ...] = (0,)
    ) -> subprocess.CompletedProcess[bytes]:
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.root), *args], capture_output=True, check=False, timeout=60
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitError(f"git {' '.join(args)}: {exc}") from exc
        if proc.returncode not in ok_codes:
            err = proc.stderr.decode("utf-8", "replace").strip()
            raise GitError(f"git {' '.join(args)} exited {proc.returncode}: {err}")
        return proc

    def text(self, *args: str) -> str:
        return self._run(*args).stdout.decode("utf-8", "replace")

    def files(self, ref: str, prefix: str) -> list[str]:
        out = self._run("ls-tree", "-r", "-z", "--name-only", ref, "--", prefix).stdout
        return [p for p in out.decode("utf-8", "replace").split("\0") if p]

    def blob(self, ref: str, path: str) -> bytes:
        return self._run("cat-file", "blob", f"{ref}:{path}").stdout

    def is_ancestor(self, ancestor: str, descendant: str) -> bool | None:
        """True or False, or None when git cannot find *ancestor* (exit 128)."""
        proc = self._run("merge-base", "--is-ancestor", ancestor, descendant, ok_codes=(0, 1, 128))
        return None if proc.returncode == 128 else proc.returncode == 0


@dataclass
class SkillSide:
    """One skill at one ref."""

    skill_md_path: str | None = None
    skill_md: str = ""
    references: dict[str, str] = field(default_factory=dict)
    shape: str | None = None
    allowed_tools: str = ""
    tools_error: str | None = None
    error: str | None = None

    @property
    def surface(self) -> str:
        """The text `load_prompt_surface_from_file` feeds the model."""
        return "\n".join([self.skill_md, *(self.references[k] for k in sorted(self.references))])


def _decode(data: bytes) -> str:
    """Decode as `Path.read_text` does: strict UTF-8, universal newlines."""
    return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def read_skill(git: Git, ref: str, name: str) -> SkillSide:
    """Load a skill's rendered prompt surface and frontmatter at *ref*."""
    side = SkillSide()
    for template in _SKILL_DIRS:
        base = template.format(n=name)
        listing = git.files(ref, f"{base}/")
        if f"{base}/SKILL.md" not in listing:
            continue
        side.skill_md_path = f"{base}/SKILL.md"
        try:
            side.skill_md = _decode(git.blob(ref, side.skill_md_path))
            for path in listing:
                rest = path.removeprefix(f"{base}/references/")
                if rest != path and "/" not in rest and rest.endswith(".md"):
                    side.references[rest] = _decode(git.blob(ref, path))
        except UnicodeDecodeError as exc:
            side.error = f"{ref}: prompt surface is not UTF-8: {exc}"
            return side
        _read_frontmatter(side, ref)
        return side
    return side


def _read_frontmatter(side: SkillSide, ref: str) -> None:
    match = re.match(r"^---\n(.*?)\n---\n", side.skill_md, re.DOTALL)
    try:
        front = yaml.safe_load(match.group(1)) if match else None
    except yaml.YAMLError as exc:
        side.error = f"{ref}: frontmatter is not valid YAML: {exc}"
        return
    front = front if isinstance(front, dict) else {}
    metadata = front.get("metadata")
    shape = metadata.get("shape") if isinstance(metadata, dict) else None
    if shape is not None and shape not in SHAPES:
        side.error = f"{ref}: metadata.shape is {shape!r}; it must be driver or reference"
    side.shape = shape if shape in SHAPES else None
    tools = front.get("allowed-tools")
    if isinstance(tools, list) and all(isinstance(t, str) for t in tools):
        tools = ", ".join(tools)
    if tools is not None and not isinstance(tools, str):
        side.tools_error = f"allowed-tools is a {type(tools).__name__}, not a string or list"
    side.allowed_tools = tools if isinstance(tools, str) else ""


def reference_grant_findings(name: str, allowed_tools: str) -> list[str]:
    """Grants outside the `reference` allowlist (ADR-127 decision 1).

    Bash is allowed only for a read-only command or for an interpreter that
    runs a script under this skill's own ``scripts/`` directory. A reference
    skill whose own script pushes is still a driver; a reviewer owns that.
    """
    own_script = re.compile(rf"^{_INTERPRETER}\S*skills/{re.escape(name)}/scripts/\S*$")
    problems = []
    for match in _GRANT.finditer(allowed_tools):
        tool, inner = match.group("tool"), match.group("inner")
        if tool == "Bash":
            ok = (
                inner is not None
                and not _UNSAFE_BASH.search(inner)
                and bool(_READ_BASH.match(inner.strip()) or own_script.match(inner.strip()))
            )
        else:
            ok = inner is None and (
                tool in _REFERENCE_TOOLS
                or bool(_READ_MCP.match(tool) and not _MCP_WRITE_WORD.search(tool.split("__")[-1]))
            )
        if not ok:
            problems.append(f"shape is reference but allowed-tools grants {match.group(0)}")
    grants = [m.group(0) for m in _GRANT.finditer(allowed_tools)]
    writes = sorted({g for g in grants if g in _WRITE_TOOLS})
    if writes and any(g.startswith("Bash") for g in grants):
        problems.append(
            f"shape is reference but allowed-tools grants {writes} beside a Bash grant; "
            "the model could write a script or a git config and run it"
        )
    return problems


def moved_lines(base: SkillSide, head: SkillSide) -> int:
    """Count lines removed from SKILL.md that reappear in an added reference line.

    Only lines of at least `MOVE_MIN_CHARS` count, so blank lines, headings,
    and table rules do not make a coincidental match.
    """
    removed = {
        line[2:].strip()
        for line in difflib.ndiff(base.skill_md.splitlines(), head.skill_md.splitlines())
        if line.startswith("- ") and len(line[2:].strip()) >= MOVE_MIN_CHARS
    }
    added: set[str] = set()
    for name, text in head.references.items():
        old = {line.strip() for line in base.references.get(name, "").splitlines()}
        added |= {line.strip() for line in text.splitlines()} - old
    return len(removed & added)
