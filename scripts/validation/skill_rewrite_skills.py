"""Read one skill at one git ref, for the ADR-127 evidence check.

``check_skill_rewrite_evidence.py`` owns the gate. This module owns the
read-only git access, the prompt surface, the ``metadata.shape`` and
``allowed-tools`` frontmatter, the ``reference`` grant allowlist, and the
moved-line count behind trigger 4.
"""

from __future__ import annotations

import ast
import difflib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [p for p in (str(_REPO_ROOT),) if p not in sys.path]

from scripts.hook_utilities.frontmatter_block import split_frontmatter  # noqa: E402

SHAPES = frozenset({"driver", "reference"})
_CONSTRUCTORS = frozenset({"__init__", "__new__"})
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

    def tree_blobs(self, ref: str, prefix: str) -> dict[str, str]:
        """Path to blob id for each file at *ref* under *prefix* (a file or a directory)."""
        out = self._run("ls-tree", "-r", "-z", ref, "--", prefix).stdout
        entries = filter(None, out.decode("utf-8", "replace").split("\0"))
        return {path: meta.split()[2] for meta, _, path in (e.partition("\t") for e in entries)}

    def adding_commit(self, ref: str, path: str) -> str | None:
        """The newest commit reachable from *ref* that added *path*, or None when none shows it.

        A merge shows no diff without ``-m``, so a file that only a merge
        commit introduced has no entry here. ``--topo-order`` puts every
        child before its parents, so the first line is the newest add: the
        one that put the file at *ref*, not an older add of a path that was
        deleted and reused. ``--literal-pathspecs`` stops a file named
        ``*.json`` from matching its neighbours.
        """
        out = self.text(
            "--literal-pathspecs",
            "log",
            "--full-history",
            "--topo-order",
            "--diff-filter=A",
            "--format=%H",
            ref,
            "--",
            path,
        )
        shas = out.split()
        return shas[0] if shas else None

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
    """Fill shape and grants from the leading block.

    The fences come from ``scripts/hook_utilities/frontmatter_block.py``, so
    a ``----`` or ``--- `` fence reads here as it does for every other check.
    The YAML load stays ``yaml.safe_load``: a skill file that repeats a key
    is the frontmatter validator's finding, not this one.
    """
    split = split_frontmatter(side.skill_md)
    try:
        front = yaml.safe_load(split.raw) if split.found else None
    except yaml.YAMLError as exc:
        side.error = f"{ref}: frontmatter is not valid YAML: {exc}"
        return
    front = front if isinstance(front, dict) else {}
    metadata = front.get("metadata")
    shape = metadata.get("shape") if isinstance(metadata, dict) else None
    valid = isinstance(shape, str) and shape in SHAPES
    if shape is not None and not valid:
        side.error = f"{ref}: metadata.shape is {shape!r}; it must be driver or reference"
    side.shape = shape if valid else None
    tools = front.get("allowed-tools")
    if isinstance(tools, list) and all(isinstance(t, str) for t in tools):
        tools = ", ".join(tools)
    if tools is not None and not isinstance(tools, str):
        side.tools_error = f"allowed-tools is a {type(tools).__name__}, not a string or list"
    side.allowed_tools = tools if isinstance(tools, str) else ""


def _split_grants(allowed_tools: str) -> list[str]:
    """Split on commas outside parentheses; blank segments are dropped.

    The whole string is consumed, so a token the grant pattern cannot match
    stays visible to the caller. A pattern that only searched would skip it.
    """
    grants, depth, start = [], 0, 0
    for index, char in enumerate(allowed_tools):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        elif char == "," and depth == 0:
            grants.append(allowed_tools[start:index].strip())
            start = index + 1
    grants.append(allowed_tools[start:].strip())
    return [g for g in grants if g]


def reference_grant_findings(name: str, allowed_tools: str) -> list[str]:
    """Grants outside the `reference` allowlist (ADR-127 decision 1).

    Bash is allowed only for a read-only command or for an interpreter that
    runs a script under this skill's own ``scripts/`` directory. A reference
    skill whose own script pushes is still a driver; a reviewer owns that.

    Every comma-separated token must parse as ``Tool`` or ``Tool(inner)``.
    A token that does not, such as ``*`` or ``mcp__x__*``, is a finding: the
    frontmatter validator reads ``*`` as a live wildcard grant.
    """
    own_script = re.compile(rf"^{_INTERPRETER}\S*skills/{re.escape(name)}/scripts/\S*$")
    problems = []
    grants = _split_grants(allowed_tools)
    for grant in grants:
        match = _GRANT.fullmatch(grant)
        if match is None:
            problems.append(f"shape is reference but allowed-tools grants {grant}")
            continue
        tool, inner = match.group("tool"), match.group("inner")
        if tool == "Bash":
            ok = (
                inner is not None
                and "," not in inner
                and not _UNSAFE_BASH.search(inner)
                and bool(_READ_BASH.match(inner.strip()) or own_script.match(inner.strip()))
            )
        else:
            ok = inner is None and (
                tool in _REFERENCE_TOOLS
                or bool(_READ_MCP.match(tool) and not _MCP_WRITE_WORD.search(tool.split("__")[-1]))
            )
        if not ok:
            problems.append(f"shape is reference but allowed-tools grants {grant}")
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


# What pytest collects, from [tool.pytest.ini_options] in pyproject.toml:
# testpaths = ["tests"], python_files = ["test_*.py"],
# python_classes = ["Test*"], python_functions = ["test_*"].
# TestCollectionRules.test_constants_match_pyproject fails when they drift.
PYTEST_ROOT = "tests"
PYTEST_FILE_GLOB = "test_*.py"
PYTEST_CLASS_PREFIX = "Test"
PYTEST_FUNC_PREFIX = "test_"


def is_collected_file(path: str) -> bool:
    """True when pytest collects *path*: under ``tests/`` with a ``test_*.py`` name."""
    parts = PurePosixPath(path).parts
    return (
        len(parts) > 1
        and parts[0] == PYTEST_ROOT
        and ".." not in parts
        and fnmatchcase(parts[-1], PYTEST_FILE_GLOB)
    )


def defines_test(source: str, classes: list[str], func: str) -> bool:
    """True when pytest would collect *func*, defined directly in nested *classes* of *source*.

    *classes* and *func* are the segments of a pytest node id after the path.
    Every class must start with ``Test`` and *func* with ``test_``. A
    ``[param]`` id is False: a parameter id exists only at run time, so no
    static read of *source* can confirm it. An empty segment, or a file that
    does not parse, is False. So is a test that ``__test__ = False`` turns
    off in its module or class chain, which pytest skips. So is a class in
    the chain that defines ``__init__`` or ``__new__``: pytest 9 skips it
    with a warning (``_pytest/python.py``). So is a name a later statement
    rebinds, such as ``test_x = None``: pytest reads the final binding. Whether
    the file itself is collected is ``is_collected_file``'s question, not this one's.
    """
    named_like_tests = func.startswith(PYTEST_FUNC_PREFIX) and "[" not in func
    if not named_like_tests or not all(c.startswith(PYTEST_CLASS_PREFIX) for c in classes):
        return False
    try:
        body = ast.parse(source).body
    except SyntaxError:
        return False
    if _turns_off_collection(body, {classes[0] if classes else func}):
        return False
    for name in classes:
        found = _final_binding(body, name)
        if not isinstance(found, ast.ClassDef) or _turns_off_collection(found.body, {func}):
            return False
        if _defines_constructor(found.body):
            return False
        body = found.body
    return isinstance(_final_binding(body, func), (ast.FunctionDef, ast.AsyncFunctionDef))


def _final_binding(body: list[ast.stmt], name: str) -> ast.stmt | None:
    """The last statement directly in *body* that binds *name*, or None.

    A def, a class, an import, ``del``, or an assignment with a value binds.
    A binding nested in ``if`` or ``try`` is not read: no static read knows
    which branch runs.
    """
    found = None
    for node in body:
        if name in _bound_names(node):
            found = node
    return found


def _bound_names(node: ast.stmt) -> set[str]:
    """Names *node* binds or deletes at its own level."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {(a.asname or a.name).split(".")[0] for a in node.names}
    targets: list[ast.expr] = []
    if isinstance(node, (ast.Assign, ast.Delete)):
        targets = node.targets
    elif isinstance(node, ast.AugAssign) or (
        isinstance(node, ast.AnnAssign) and node.value is not None
    ):
        targets = [node.target]
    stores = (ast.Store, ast.Del)
    return {
        n.id
        for t in targets
        for n in ast.walk(t)
        if isinstance(n, ast.Name) and isinstance(n.ctx, stores)
    }


def _defines_constructor(body: list[ast.stmt]) -> bool:
    """True when a class *body* defines ``__init__`` or ``__new__``; pytest 9 skips that class."""
    funcs = (ast.FunctionDef, ast.AsyncFunctionDef)
    return any(isinstance(n, funcs) and n.name in _CONSTRUCTORS for n in body)


def _turns_off_collection(body: list[ast.stmt], names: set[str]) -> bool:
    """True when *body* sets ``__test__`` falsy, directly or as ``<name>.__test__`` for a name."""
    for node in body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        # pytest skips on any falsy __test__, not only False.
        if not (isinstance(value, ast.Constant) and not value.value):
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "__test__":
                return True
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "__test__"
                and isinstance(target.value, ast.Name)
                and target.value.id in names
            ):
                return True
    return False
