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
  commit that touches the skill (decision 7 item 8), with no kept
  scenario's ``expected_verdict`` changed since the merge base (item 10);
- each scenario dropped since the merge base listed in ``retired.json`` with
  a test that exists at head;
- results files that are append-only on the branch: an edit or delete of
  one fails (item 9);
- a results file recording the head prompt-surface sha256. The first one
  committed sets the verdict (one already on the base ref counts as first)
  and must match the other identities: prompt path, scenario path and
  sha256, a base commit that is an ancestor of the base ref, and a model;
- a merge-base scenario file that parses, when one exists;
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
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
sys.path[:0] = [p for p in (str(_REPO_ROOT), str(_SCRIPT_DIR)) if p not in sys.path]

from skill_rewrite_evidence import Expected, load_runner, verify_results  # noqa: E402
from skill_rewrite_skills import (  # noqa: E402
    _SKILL_DIRS,
    MOVE_MIN_LINES,
    Git,
    GitError,
    SkillSide,
    moved_lines,
    read_skill,
    reference_grant_findings,
)

EXIT_OK, EXIT_FINDINGS, EXIT_CONFIG = 0, 1, 2
EVIDENCE_ROOT = "evals/skill-rewrites"
RETIRED_FILE = "retired.json"
_SKILL_PATH_PATTERNS = (
    re.compile(r"^templates/skills/(?P<n>[^/]+)\.SKILL\.md\.tmpl$"),
    re.compile(r"^src/claude/skills/(?P<n>[^/]+)/"),
    re.compile(r"^\.claude/skills/(?P<n>[^/]+)/"),
    re.compile(r"^tests/evals/(?P<n>[^/]+)-scenarios\.json$"),
    re.compile(rf"^{EVIDENCE_ROOT}/(?P<n>[^/]+)/"),
)


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
    _changes: dict[str, dict[str, str]] = field(default_factory=dict)

    def changes(self, commit: str) -> dict[str, str]:
        """Path to status for one commit. ``--cc`` keeps a merge's own edits."""
        if commit in self._changes:
            return self._changes[commit]
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
        self._changes[commit] = {parts[i + 1]: parts[i] for i in range(0, len(parts) - 1, 2)}
        return self._changes[commit]


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
            f"{scenario_path} changes in or after the first commit that touches the skill; "
            "scenarios land in their own earlier commit and stay frozen"
        ]
    return []


def _scenario_rows(data: bytes) -> list[dict[str, Any]] | None:
    """The scenario rows, each a mapping with an ``id``, or None when the file is not that."""
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    rows = parsed.get("scenarios") if isinstance(parsed, dict) else None
    if not isinstance(rows, list) or not all(isinstance(r, dict) and "id" in r for r in rows):
        return None
    return rows


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


def _label_findings(base: list[dict[str, Any]], head: list[dict[str, Any]]) -> list[str]:
    """A kept scenario may not change its label (ADR-127 decision 7 item 10)."""
    before = {str(r["id"]): r.get("expected_verdict") for r in base}
    return [
        f"scenario {s['id']} changes expected_verdict from {before[str(s['id'])]!r} "
        f"to {s['expected_verdict']!r}; a label never changes to pass"
        for s in head
        if str(s["id"]) in before and before[str(s["id"])] != s["expected_verdict"]
    ]


@dataclass
class _Scenarios:
    path: str
    data: bytes
    rows: list[dict[str, Any]]


def _load_scenarios(ctx: Context, name: str) -> tuple[_Scenarios | None, list[str]]:
    """The head scenario file, plus findings against the merge base."""
    path = f"tests/evals/{name}-scenarios.json"
    if path not in ctx.git.files(ctx.head, path):
        return None, [f"{path} does not exist; a gated skill needs a scenario file"]
    data = ctx.git.blob(ctx.head, path)
    rows = _scenario_rows(data)
    if rows is None:
        return None, [f"{path} is not valid scenario JSON with an id on every scenario"]
    if not all("expected_verdict" in r for r in rows):
        return None, [f"{path} has a scenario with no expected_verdict"]
    problems = _freeze_findings(ctx, name, path)
    if path in ctx.git.files(ctx.merge_base, path):
        base = _scenario_rows(ctx.git.blob(ctx.merge_base, path))
        if base is None:
            return None, [
                f"{path} does not parse at the merge base, so dropped scenarios and "
                "label changes cannot be checked"
            ]
        head_ids = {str(r["id"]) for r in rows}
        dropped = [str(r["id"]) for r in base if str(r["id"]) not in head_ids]
        problems += _retired_findings(ctx, name, dropped)
        problems += _label_findings(base, rows)
    return _Scenarios(path, data, rows), problems


def _load_results(ctx: Context, results_dir: str) -> tuple[dict[str, Any], list[str]]:
    """Every results file under *results_dir* at head, parsed."""
    paths = [
        p
        for p in ctx.git.files(ctx.head, results_dir)
        if p.endswith(".json") and not p.endswith(f"/{RETIRED_FILE}")
    ]
    if not paths:
        return {}, [f"no results file under {results_dir}; run the eval with --output there"]
    parsed: dict[str, Any] = {}
    problems = []
    for path in paths:
        try:
            parsed[path] = json.loads(ctx.git.blob(ctx.head, path))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append(f"{path} is not readable JSON: {exc}")
    return parsed, problems


def _surface_sha(result: object) -> object:
    identity = result.get("identity") if isinstance(result, dict) else None
    return identity.get("prompt_surface_sha256") if isinstance(identity, dict) else None


def verify_skill(ctx: Context, name: str, head: SkillSide) -> list[str]:
    """Findings for one gated skill's evidence."""
    scen, problems = _load_scenarios(ctx, name)
    if scen is None:
        return problems
    results_dir = f"{EVIDENCE_ROOT}/{name}/"
    parsed, read_problems = _load_results(ctx, results_dir)
    problems += read_problems
    if problems:
        return problems
    head_sha = hashlib.sha256(head.surface.encode("utf-8")).hexdigest()
    matching = [p for p, r in parsed.items() if _surface_sha(r) == head_sha]
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
        scenarios_path=scen.path,
        scenarios_sha256=hashlib.sha256(scen.data).hexdigest(),
        scenarios=tuple(scen.rows),
    )
    for path in sorted(p for p, i in order.items() if i == first):
        found = verify_results(ctx.runner, parsed[path], expected)
        base_commit = parsed[path]["identity"].get("base_commit")
        ancestor = None if found else ctx.git.is_ancestor(str(base_commit), ctx.base_ref)
        if ancestor is None and not found:
            found.append(f"identity.base_commit {base_commit} is not a commit in this clone")
        elif ancestor is False:
            found.append(f"identity.base_commit {base_commit} is not an ancestor of {ctx.base_ref}")
        problems += [f"{path}: {f}" for f in found]
    return problems


# A gated change may not also change the code that judges it.
_JUDGE_PATHS = (
    "scripts/eval/eval-prompt-change.py",
    "scripts/eval/_",
    "scripts/validation/check_skill_rewrite_evidence.py",
    "scripts/validation/skill_rewrite_evidence.py",
    "scripts/validation/skill_rewrite_skills.py",
    "scripts/validation/checks_ci_parity.py",
    "scripts/validation/pre_pr_sequence.py",
    ".github/workflows/pr-validation.yml",
)


def _log(message: str) -> None:
    print(f"[skill-rewrite-evidence] {message}")


def _gate_or_skip(
    name: str, base: SkillSide, side: SkillSide, paths: dict[str, str], deleted: bool
) -> list[str]:
    """The gate reasons for one readable skill; empty when it is not gated."""
    if side.skill_md_path is None:
        _log(f"{name} is deleted; nothing to evaluate")
        return []
    if base.skill_md_path is None and not deleted:
        _log(f"{name} is new; it has no base to hold against")
        return []
    reasons = gate_reasons(name, base, side, paths)
    if base.skill_md_path is None:
        reasons.append("a new skill lands beside a deleted one, so it may be a rename")
    return reasons


def _examine(
    ctx: Context,
    name: str,
    sides: tuple[SkillSide, SkillSide],
    paths: dict[str, str],
    deleted: bool,
) -> tuple[list[str], bool]:
    """Findings for one changed skill, and whether it is gated."""
    base, side = sides
    errors = [e for e in (base.error, side.error, side.tools_error) if e]
    if errors:
        return [f"{name}: {e}" for e in errors], False
    findings = []
    if side.shape == "reference":
        findings = [f"{name}: {f}" for f in reference_grant_findings(name, side.allowed_tools)]
    reasons = _gate_or_skip(name, base, side, paths, deleted)
    if not reasons:
        _log(f"{name} is not gated: no ADR-127 decision 7 trigger fired")
        return findings, False
    _log(f"{name} is gated: {'; '.join(reasons)}")
    judge = sorted(p for p in paths if p.startswith(_JUDGE_PATHS))
    if judge:
        findings.append(f"{name}: a gated change may not also change {judge}")
    findings += [f"{name}: {f}" for f in verify_skill(ctx, name, side)]
    return findings, True


def run_check(git: Git, base_ref: str, head: str = "HEAD") -> tuple[list[str], int, int]:
    """Return (findings, skills examined, gated skills)."""
    merge_base = git.text("merge-base", base_ref, head).strip()
    paths = changed_paths(git, merge_base, head)
    commits = git.text("rev-list", "--reverse", "--topo-order", f"{merge_base}..{head}").split()
    ctx = Context(git, base_ref, head, merge_base, commits, load_runner())
    sides = {
        n: (read_skill(git, merge_base, n), read_skill(git, head, n))
        for n in sorted(skill_names(paths))
    }
    deleted = any(b.skill_md_path and not h.skill_md_path for b, h in sides.values())
    findings: list[str] = []
    examined = gated = 0
    for name, pair in sides.items():
        if pair[0].skill_md_path is None and pair[1].skill_md_path is None:
            if any(p.startswith(f"{EVIDENCE_ROOT}/{name}/") for p in paths):
                findings.append(f"{EVIDENCE_ROOT}/{name}/ names no skill")
            continue
        examined += 1
        found, is_gated = _examine(ctx, name, pair, paths, deleted)
        findings += found
        gated += is_gated
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
    except (ImportError, OSError, SyntaxError) as exc:
        print(f"[skill-rewrite-evidence] cannot load the eval runner: {exc}", file=sys.stderr)
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
