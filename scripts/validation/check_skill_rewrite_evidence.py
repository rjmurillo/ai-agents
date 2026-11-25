#!/usr/bin/env python3
"""Block an ADR-127 gated skill change that lacks valid eval evidence.

ADR-127 decision 9 requires a deterministic check that calls no model. For
each skill the branch changes, this script decides whether the change is
gated (decision 7) and, if so, verifies the committed results under
``evals/skill-rewrites/<name>/``. ADR-057 (Amendment 2026-11-25) scopes this
blocking gate to gated changes. Every other prompt file stays advisory.

What counts as a gated change, read from ``git diff <merge-base> <head>``.
``<head>`` is ``--head-ref``: CI passes the PR head commit, so CI hashes the
same tree the author ran the eval on, not the synthetic merge commit.

1. ``metadata.shape`` in the rendered ``SKILL.md`` changes. Adding
   ``reference`` where no shape existed is exempt (decision 7).
2. The skill is ``driver`` on either side and its prompt surface changed.
   The surface is the rendered ``SKILL.md`` plus each ``references/*.md``.
3. The branch touches ``evals/skill-rewrites/<name>/``. That is the author
   declaring a gated change, which covers a gap-audit row (trigger 3).
4. At least ``MOVE_MIN_LINES`` lines leave ``SKILL.md`` and reappear verbatim
   in a ``references/*.md`` file: a section moved out. This is a precision
   measure; a reworded or split move slips past it.

A new skill has no base to hold against, and a deleted one has nothing to
run, so neither is gated. A new skill that lands beside a deleted one may be
a rename, so it is gated and its eval uses the runner's ``--renamed-from``.

Not mechanical, so not detected: an untagged skill that decision 1 says must
be a driver; a step moved into a script, since prose and code share no
lines; a section moved and reworded in one commit; and a gap-audit row the
author does not declare. A reviewer still owns those.

For a gated skill the check requires, and fails closed without:

- ``tests/evals/<name>-scenarios.json`` at head, frozen after the first
  commit that touches the prompt surface (decision 7 item 8), with no kept
  scenario's ``expected_verdict`` changed since the merge base (item 10);
- each scenario dropped since the merge base listed in ``retired.json`` with
  a test that exists at head;
- results files that are append-only on the branch: an edit or delete of
  one fails (item 9);
- a results file recording the head prompt-surface sha256. Of those, the
  one the branch added first sets the verdict, and it must match the other
  identities: prompt path, scenario path and sha256, a base commit that is
  an ancestor of the base ref, and a model;
- the verdict recomputed from the per-run labels, plus the decision 7
  floors (``skill_rewrite_evidence.verify_results``);
- no change in the same branch to the runner or to this check.

``retired.json`` is ``{"retired": [{"scenario": "<id>", "test":
"<path>::<name>"}]}``. ``prompt_path`` must be the repository-relative path
of the rendered file, as ``--prompt`` takes it.

A skill tagged ``reference`` that the branch touches also fails when its
``allowed-tools`` holds a grant outside a read-only allowlist. Bash is
allowed only for a read-only command or a script under the skill's own
``scripts/``. A wider grant makes it a driver under decision 1, so the tag
would dodge trigger 2. This rule goes past decision 9; the ADR-127 security
seat asked for it.

Limits, which stay with the reviewer:

- This check cannot prove a model ran. A hand-built results file with
  matching hashes passes.
- The branch history is the author's. A rebase can drop a failed run or
  move the scenario commit before this check reads the branch.
- A PR that edits this check or the runner changes what this check does.
  The same-branch rule above stops honest drift only.
- ``security_critical`` is read from the results file. Nothing records which
  skills are security-critical.

EXIT CODES (ADR-035): 0 = no findings (prints examined counts); 1 =
findings; 2 = git or config error, including no base ref resolved.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
sys.path[:0] = [p for p in (str(_REPO_ROOT), str(_SCRIPT_DIR)) if p not in sys.path]

import yaml  # noqa: E402
from skill_rewrite_evidence import Expected, load_runner, verify_results  # noqa: E402

EXIT_OK, EXIT_FINDINGS, EXIT_CONFIG = 0, 1, 2
SHAPES = frozenset({"driver", "reference"})
EVIDENCE_ROOT = "evals/skill-rewrites"
RETIRED_FILE = "retired.json"
# Trigger 4: at least this many SKILL.md lines of at least this length must
# reappear verbatim in references/. Measured on 400 first-parent commits of
# main to c0b72f8539 (2026-11-25): 5 skill changes in 4 commits fire. In
# each, SKILL.md shrank and a reference file gained the removed lines.
MOVE_MIN_LINES = 3
MOVE_MIN_CHARS = 32

_SKILL_PATH_PATTERNS = (
    re.compile(r"^templates/skills/(?P<n>[^/]+)\.SKILL\.md\.tmpl$"),
    re.compile(r"^src/claude/skills/(?P<n>[^/]+)/"),
    re.compile(r"^\.claude/skills/(?P<n>[^/]+)/"),
    re.compile(r"^tests/evals/(?P<n>[^/]+)-scenarios\.json$"),
    re.compile(rf"^{EVIDENCE_ROOT}/(?P<n>[^/]+)/"),
)
_SKILL_DIRS = ("src/claude/skills/{n}", ".claude/skills/{n}")

# A `reference` skill may hold only these grants (ADR-127 decision 1). An
# allowlist, not a denylist: a denylist of push and PR-write forms leaked
# `git -C . push`, `uv:*`, and list-form grants in review.
_READ_TOOLS = frozenset(
    {
        "Read",
        "Grep",
        "Glob",
        "LS",
        "Skill",
        "Task",
        "Agent",
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
    r"|git branch --show-current|date|ls|wc|mkdir|python3 -m json\.tool)(?:[: ]|$)"
)
_INTERPRETER = r"(?:python3|uv run --frozen python)(?: -I)?\s*:?\s*"
# A Bash grant holding a path climb or a shell operator can chain past the
# command it names, so it never counts as read-only.
# `git diff --output` writes a file and `--ext-diff` runs a program.
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

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        proc = self._run("merge-base", "--is-ancestor", ancestor, descendant, ok_codes=(0, 1, 128))
        return proc.returncode == 0


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
                tool in _READ_TOOLS
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


def changed_paths(git: Git, merge_base: str, head: str) -> dict[str, str]:
    """Map each path changed from *merge_base* to *head* to its status letter."""
    raw = git.text("diff", "--name-status", "-z", "--no-renames", merge_base, head)
    parts = [p for p in raw.split("\0") if p]
    return {parts[i + 1]: parts[i][0] for i in range(0, len(parts) - 1, 2)}


def skill_names(paths: dict[str, str]) -> set[str]:
    names = set()
    for path in paths:
        for pattern in _SKILL_PATH_PATTERNS:
            match = pattern.match(path)
            if match:
                names.add(match.group("n"))
    return names


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


def gate_reasons(name: str, base: SkillSide, head: SkillSide, paths: dict[str, str]) -> list[str]:
    """The ADR-127 decision 7 triggers this branch fires for *name*."""
    reasons = []
    if base.shape != head.shape and not (base.shape is None and head.shape == "reference"):
        reasons.append(f"metadata.shape changes from {base.shape} to {head.shape}")
    if "driver" in (base.shape, head.shape) and base.surface != head.surface:
        reasons.append("the prompt surface of a driver skill changes")
    if any(p.startswith(f"{EVIDENCE_ROOT}/{name}/") for p in paths):
        reasons.append(f"the branch changes {EVIDENCE_ROOT}/{name}/")
    moved = moved_lines(base, head)
    if base.skill_md_path and moved >= MOVE_MIN_LINES:
        reasons.append(f"{moved} lines move from SKILL.md into references/")
    return reasons


@dataclass
class Context:
    git: Git
    base_ref: str
    head: str
    merge_base: str
    commits: list[str]
    runner: ModuleType

    def changes(self, commit: str) -> dict[str, str]:
        """Path to status for one commit. ``--cc`` keeps a merge's own edits."""
        raw = self.git.text(
            "diff-tree",
            "--no-commit-id",
            "-r",
            "-z",
            "--cc",
            "--name-status",
            "--no-renames",
            commit,
        )
        parts = [p for p in raw.split("\0") if p]
        return {parts[i + 1]: parts[i] for i in range(0, len(parts) - 1, 2)}


def _freeze_findings(ctx: Context, name: str, scenario_path: str) -> list[str]:
    surface = (
        f"templates/skills/{name}.SKILL.md.tmpl",
        *(f"{d.format(n=name)}/" for d in _SKILL_DIRS),
    )
    last_scenario = first_surface = None
    for index, commit in enumerate(ctx.commits):
        files = ctx.changes(commit)
        if scenario_path in files:
            last_scenario = index
        if first_surface is None and any(f.startswith(surface) for f in files):
            first_surface = index
    if last_scenario is not None and first_surface is not None and last_scenario >= first_surface:
        return [
            f"{scenario_path} changes in or after the first prompt-surface commit; "
            "scenarios land in their own earlier commit and stay frozen"
        ]
    return []


def _scenario_ids(data: bytes) -> list[str] | None:
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    rows = parsed.get("scenarios") if isinstance(parsed, dict) else None
    if not isinstance(rows, list) or not all(isinstance(r, dict) and "id" in r for r in rows):
        return None
    return [str(r["id"]) for r in rows]


def _retired_findings(ctx: Context, name: str, dropped: list[str]) -> list[str]:
    if not dropped:
        return []
    path = f"{EVIDENCE_ROOT}/{name}/{RETIRED_FILE}"
    if path not in ctx.git.files(ctx.head, path):
        return [f"scenarios {dropped} were dropped and {path} does not exist"]
    try:
        rows = json.loads(ctx.git.blob(ctx.head, path)).get("retired")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        rows = None
    if not isinstance(rows, list):
        return [f"{path} is not valid JSON with a 'retired' list"]
    tests = {r.get("scenario"): r.get("test") for r in rows if isinstance(r, dict)}
    problems = []
    for sid in dropped:
        test = tests.get(sid)
        if not isinstance(test, str) or "::" not in test:
            problems.append(f"dropped scenario {sid} has no replacing test in {path}")
            continue
        test_path, func = test.split("::", 1)[0], test.rsplit("::", 1)[-1]
        found = test_path in ctx.git.files(ctx.head, test_path)
        if not found or f"def {func}(" not in ctx.git.blob(ctx.head, test_path).decode(
            "utf-8", "replace"
        ):
            problems.append(f"dropped scenario {sid}: test {test} does not exist at HEAD")
    return problems


def _results_history(ctx: Context, results_dir: str) -> tuple[dict[str, int], list[str]]:
    """When each results file was added, and every edit or delete of one.

    Results files are append-only (ADR-127 decision 7 item 9): a later run is
    a new file, so the first one keeps setting the verdict.
    """
    added: dict[str, int] = {}
    problems = []
    for index, commit in enumerate(ctx.commits):
        for path, status in ctx.changes(commit).items():
            if not path.startswith(results_dir) or not path.endswith(".json"):
                continue
            if path.endswith(f"/{RETIRED_FILE}"):
                continue
            if status == "A" and path not in added:
                added[path] = index
            elif status == "A":
                problems.append(
                    f"{path} is added again in {commit[:10]}; results files are append-only"
                )
            else:
                problems.append(
                    f"{path} is edited or deleted in {commit[:10]}; results files are append-only"
                )
    return added, problems


def _label_findings(base_bytes: bytes, scenarios: list[dict[str, Any]]) -> list[str]:
    """A kept scenario may not change its label (ADR-127 decision 7 item 10)."""
    try:
        rows = json.loads(base_bytes).get("scenarios")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return []
    if not isinstance(rows, list):
        return []
    before = {str(r.get("id")): r.get("expected_verdict") for r in rows if isinstance(r, dict)}
    return [
        f"scenario {s['id']} changes expected_verdict from {before[str(s['id'])]!r} "
        f"to {s['expected_verdict']!r}; a label never changes to pass"
        for s in scenarios
        if str(s["id"]) in before and before[str(s["id"])] != s["expected_verdict"]
    ]


def verify_skill(ctx: Context, name: str, head: SkillSide) -> list[str]:
    """Findings for one gated skill's evidence."""
    scenario_path = f"tests/evals/{name}-scenarios.json"
    if scenario_path not in ctx.git.files(ctx.head, scenario_path):
        return [f"{scenario_path} does not exist; a gated skill needs a scenario file"]
    scenario_bytes = ctx.git.blob(ctx.head, scenario_path)
    try:
        scenarios = json.loads(scenario_bytes)["scenarios"]
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError):
        return [f"{scenario_path} is not valid scenario JSON"]
    head_ids = _scenario_ids(scenario_bytes)
    if head_ids is None or not all("expected_verdict" in s for s in scenarios):
        return [f"{scenario_path} has a scenario with no id or expected_verdict"]
    problems = _freeze_findings(ctx, name, scenario_path)
    if scenario_path in ctx.git.files(ctx.merge_base, scenario_path):
        base_ids = _scenario_ids(ctx.git.blob(ctx.merge_base, scenario_path)) or []
        problems += _retired_findings(ctx, name, [i for i in base_ids if i not in head_ids])
        problems += _label_findings(ctx.git.blob(ctx.merge_base, scenario_path), scenarios)
    results_dir = f"{EVIDENCE_ROOT}/{name}/"
    result_paths = [
        p
        for p in ctx.git.files(ctx.head, results_dir)
        if p.endswith(".json") and not p.endswith(f"/{RETIRED_FILE}")
    ]
    if not result_paths:
        return [*problems, f"no results file under {results_dir}; run the eval with --output there"]
    head_sha = hashlib.sha256(head.surface.encode("utf-8")).hexdigest()
    parsed: dict[str, Any] = {}
    for path in result_paths:
        try:
            parsed[path] = json.loads(ctx.git.blob(ctx.head, path))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append(f"{path} is not readable JSON: {exc}")
    if problems:
        return problems
    matching = [
        p
        for p, r in parsed.items()
        if isinstance(r, dict)
        and isinstance(r.get("identity"), dict)
        and r["identity"].get("prompt_surface_sha256") == head_sha
    ]
    if not matching:
        return [
            f"no results file under {results_dir} records the HEAD prompt surface sha256 {head_sha}"
        ]
    added, history = _results_history(ctx, results_dir)
    if history:
        return history
    order = {p: added.get(p, -1) for p in matching}
    first = min(order.values())
    expected = Expected(
        prompt_path=str(head.skill_md_path),
        prompt_surface_sha256=head_sha,
        scenarios_path=scenario_path,
        scenarios_sha256=hashlib.sha256(scenario_bytes).hexdigest(),
        scenarios=tuple(scenarios),
    )
    for path in sorted(p for p, i in order.items() if i == first):
        found = verify_results(ctx.runner, parsed[path], expected)
        base_commit = parsed[path]["identity"].get("base_commit")
        if not found and not ctx.git.is_ancestor(str(base_commit), ctx.base_ref):
            found.append(f"identity.base_commit {base_commit} is not an ancestor of {ctx.base_ref}")
        problems += [f"{path}: {f}" for f in found]
    return problems


# A gated change may not also change the code that judges it.
_JUDGE_PATHS = (
    "scripts/eval/eval-prompt-change.py",
    "scripts/eval/_",
    "scripts/validation/check_skill_rewrite_evidence.py",
    "scripts/validation/skill_rewrite_evidence.py",
)


def run_check(git: Git, base_ref: str, head: str = "HEAD") -> tuple[list[str], int, int]:
    """Return (findings, skills examined, gated skills)."""
    merge_base = git.text("merge-base", base_ref, head).strip()
    paths = changed_paths(git, merge_base, head)
    commits = git.text("rev-list", "--reverse", "--topo-order", f"{merge_base}..{head}").split()
    ctx = Context(git, base_ref, head, merge_base, commits, load_runner())
    findings: list[str] = []
    examined = gated = 0
    sides = {
        n: (read_skill(git, merge_base, n), read_skill(git, head, n))
        for n in sorted(skill_names(paths))
    }
    deleted = any(b.skill_md_path and not h.skill_md_path for b, h in sides.values())
    for name, (base, side) in sides.items():
        if side.skill_md_path is None and base.skill_md_path is None:
            if any(p.startswith(f"{EVIDENCE_ROOT}/{name}/") for p in paths):
                findings.append(f"{EVIDENCE_ROOT}/{name}/ names no skill")
            continue
        examined += 1
        errors = [e for e in (base.error, side.error, side.tools_error) if e]
        if errors:
            findings += [f"{name}: {e}" for e in errors]
            continue
        if side.shape == "reference":
            findings += [f"{name}: {f}" for f in reference_grant_findings(name, side.allowed_tools)]
        if side.skill_md_path is None:
            print(f"[skill-rewrite-evidence] {name} is deleted; nothing to evaluate")
            continue
        if base.skill_md_path is None and not deleted:
            print(f"[skill-rewrite-evidence] {name} is new; it has no base to hold against")
            continue
        reasons = gate_reasons(name, base, side, paths)
        if base.skill_md_path is None:
            reasons.append("a new skill lands beside a deleted one, so it may be a rename")
        if not reasons:
            continue
        gated += 1
        print(f"[skill-rewrite-evidence] {name} is gated: {'; '.join(reasons)}")
        judge = sorted(p for p in paths if p.startswith(_JUDGE_PATHS))
        if judge:
            findings.append(f"{name}: a gated change may not also change {judge}")
        findings += [f"{name}: {f}" for f in verify_skill(ctx, name, side)]
    return findings, examined, gated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], allow_abbrev=False)
    parser.add_argument("--repo-root", default=str(_REPO_ROOT), help="Repository root path.")
    parser.add_argument("--base-ref", default=None, help="Base ref (default: resolved PR base).")
    parser.add_argument(
        "--head-ref",
        default="HEAD",
        help="Commit under test. CI passes the PR head, not the synthetic merge commit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    base_ref = args.base_ref
    if base_ref is None:
        from checks_common import _resolve_default_base_ref

        base_ref = _resolve_default_base_ref(root)
        if base_ref is None:
            # A blocking gate that cannot see the diff has not run. Say so.
            print("[skill-rewrite-evidence] no base ref resolved; pass --base-ref", file=sys.stderr)
            return EXIT_CONFIG
    try:
        findings, examined, gated = run_check(Git(root), base_ref, args.head_ref)
    except GitError as exc:
        print(f"[skill-rewrite-evidence] {exc}", file=sys.stderr)
        return EXIT_CONFIG
    for finding in findings:
        print(f"[skill-rewrite-evidence] FAIL {finding}")
    print(
        f"[skill-rewrite-evidence] {len(findings)} findings; {examined} changed skills "
        f"examined, {gated} gated (ADR-127 decision 9)"
    )
    return EXIT_FINDINGS if findings else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
