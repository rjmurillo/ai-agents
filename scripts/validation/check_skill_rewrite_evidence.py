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

- ``tests/evals/<name>-scenarios.json`` at head, frozen (decision 7 item 8):
  no commit changes it with the skill, and every commit that touches the
  skill holds head's blob. No kept scenario's ``expected_verdict`` changes
  since the merge base (item 10);
- each scenario dropped since the merge base listed in ``retired.json`` with
  a test that exists at head;
- results files that are append-only on the branch: an edit or delete of
  one fails (item 9), and so does a file missing at head or changed since the
  first commit on the branch that added it, which catches a merge that drops
  a run held by either parent;
- a results file recording the head prompt-surface sha256. Among those that
  also record the head scenario-file sha256, the deciding run is the one
  whose adding commit is an ancestor of every other's (one on the base ref
  counts by its own commit, so it precedes a branch run). Two added on
  parallel branches, or in one commit, have no first: the check fails closed
  and never picks the passing one. Only a skill fix, which starts a new first
  run, clears it. When none record the head scenario sha256,
  the same rule runs over the prompt-surface matches and fails on that
  identity. The deciding file must match the other identities: prompt path,
  scenario path and sha256, a base commit that is an ancestor of the base
  ref, and a model;
- a merge-base scenario file that parses, when one exists;
- the verdict recomputed from the per-run labels, plus the decision 7
  floors (``skill_rewrite_evidence.verify_results``);
- no change in the same branch to a module this check or the runner
  imports (``_JUDGE_PATHS``).

``retired.json`` is ``{"retired": [{"scenario": "<id>", "test":
"<path>::[<Class>::]<name>"}]}``. Pytest must collect it, per pyproject.toml:
the file is ``tests/**/test_*.py``, each class starts with ``Test``, the
function starts with ``test_`` and sits in that class chain. A ``[param]`` id
fails, since only a run can confirm one: name the function without it.
``prompt_path`` is the repository-relative rendered file ``--prompt`` takes.

A skill tagged ``reference`` that the branch touches also fails when its
``allowed-tools`` holds a grant outside a read-only allowlist. Bash is
allowed only for a read-only command or a script under the skill's own
``scripts/``. A wider grant makes it a driver under decision 1, so the tag
would dodge trigger 2. This rule goes past decision 9; the ADR-127 security
seat asked for it.

Limits, which stay with the reviewer: this check cannot prove a model ran
(a hand-built results file with matching hashes passes); a rebase can drop
a failed run or move the scenario commit; a PR that edits this check or the
runner changes what it does (the same-branch rule stops honest drift only);
and ``security_critical`` comes from the results file, since nothing
records which skills are security-critical.

EXIT CODES (ADR-035): 0 = no findings (prints examined counts); 1 =
findings; 2 = git or config error, including no base ref resolved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
sys.path[:0] = [p for p in (str(_REPO_ROOT), str(_SCRIPT_DIR)) if p not in sys.path]

from skill_rewrite_context import EVIDENCE_ROOT, RETIRED_FILE, Context  # noqa: E402
from skill_rewrite_evidence import Expected, load_runner, verify_results  # noqa: E402
from skill_rewrite_scenarios import load_scenarios  # noqa: E402
from skill_rewrite_skills import (  # noqa: E402
    MOVE_MIN_LINES,
    Git,
    GitError,
    SkillSide,
    moved_lines,
    read_skill,
    reference_grant_findings,
)

EXIT_OK, EXIT_FINDINGS, EXIT_CONFIG = 0, 1, 2
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


def _is_results_file(path: str, results_dir: str) -> bool:
    return (
        path.startswith(results_dir)
        and path.endswith(".json")
        and not path.endswith(f"/{RETIRED_FILE}")
    )


def _head_blob_findings(
    ctx: Context, results_dir: str, added: dict[str, int], flagged: set[str]
) -> list[str]:
    """Each results file the branch added, or that the base ref holds, must reach head unchanged.

    ``Context.changes`` sees a path only when a commit differs from every
    parent. A merge that takes one parent's tree for a path, by dropping a
    file the other parent holds, never shows there. Comparing head to the blob
    at the first add needs no per-commit view, whichever parent held the file.
    A path already named by the per-commit scan is not repeated. A base-ref
    results file must reach head with its base blob; ``retired.json`` may change.
    """
    at_head = ctx.git.tree_blobs(ctx.head, results_dir)
    problems = []
    on_base = ctx.git.tree_blobs(ctx.merge_base, results_dir)
    for path, blob in sorted(on_base.items()):
        if (
            _is_results_file(path, results_dir)
            and path not in flagged
            and at_head.get(path) != blob
        ):
            state = "is missing at HEAD" if path not in at_head else "differs at HEAD"
            problems.append(f"{path} from the base ref {state}; results files are append-only")
    for path, index in sorted(added.items()):
        commit = ctx.commits[index]
        if path in flagged or at_head.get(path) == ctx.git.tree_blobs(commit, path)[path]:
            continue
        state = (
            "is missing at HEAD"
            if path not in at_head
            else "differs at HEAD from its first-added version"
        )
        problems.append(f"{path} {state} (added in {commit[:10]}); results files are append-only")
    return problems


def _results_history(ctx: Context, results_dir: str) -> tuple[dict[str, int], list[str]]:
    """When each results file was added, and every edit, delete, or hidden change of one.

    Results files are append-only (ADR-127 decision 7 item 9): a later run is
    a new file, so the first one keeps setting the verdict.
    """
    added: dict[str, int] = {}
    problems = []
    flagged: set[str] = set()
    for index, commit in enumerate(ctx.commits):
        for path, status in ctx.changes(commit).items():
            if not _is_results_file(path, results_dir):
                continue
            # ``--cc`` prints one letter per parent for a merge: ``AA`` is an add.
            is_add = set(status) == {"A"}
            if is_add and path not in added:
                added[path] = index
            elif is_add:
                flagged.add(path)
                problems.append(
                    f"{path} is added again in {commit[:10]}; results files are append-only"
                )
            else:
                flagged.add(path)
                problems.append(
                    f"{path} is edited or deleted in {commit[:10]}; results files are append-only"
                )
    return added, problems + _head_blob_findings(ctx, results_dir, added, flagged)


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


def _identity_value(result: object, key: str) -> object:
    identity = result.get("identity") if isinstance(result, dict) else None
    return identity.get(key) if isinstance(identity, dict) else None


def verify_skill(ctx: Context, name: str, head: SkillSide) -> list[str]:
    """Findings for one gated skill's evidence."""
    scen, scenario_problems = load_scenarios(ctx, name)
    problems: list[str] = list(scenario_problems)
    if scen is None:
        return problems
    results_dir = f"{EVIDENCE_ROOT}/{name}/"
    parsed, read_problems = _load_results(ctx, results_dir)
    problems += read_problems
    if problems:
        return problems
    head_sha = hashlib.sha256(head.surface.encode("utf-8")).hexdigest()
    scenarios_sha = hashlib.sha256(scen.data).hexdigest()
    matching = [
        p for p, r in parsed.items() if _identity_value(r, "prompt_surface_sha256") == head_sha
    ]
    if not matching:
        return [
            f"no results file under {results_dir} records the HEAD prompt surface sha256 {head_sha}"
        ]
    added, history = _results_history(ctx, results_dir)
    if history:
        return history
    # A file for an earlier suite of the same prompt must not decide the first run.
    # With no file for this suite, fall back so verify_results names the mismatch.
    this_suite = [
        p for p in matching if _identity_value(parsed[p], "scenarios_sha256") == scenarios_sha
    ]
    first, ambiguous = _deciding_run(ctx, sorted(this_suite or matching), added)
    if first is None:
        return ambiguous
    expected = Expected(
        prompt_path=str(head.skill_md_path),
        prompt_surface_sha256=head_sha,
        scenarios_path=scen.path,
        scenarios_sha256=scenarios_sha,
        scenarios=tuple(scen.rows),
    )
    found = verify_results(ctx.runner, parsed[first], expected)
    base_commit = parsed[first]["identity"].get("base_commit")
    ancestor = None if found else ctx.git.is_ancestor(str(base_commit), ctx.base_ref)
    if ancestor is None and not found:
        found.append(f"identity.base_commit {base_commit} is not a commit in this clone")
    elif ancestor is False:
        found.append(f"identity.base_commit {base_commit} is not an ancestor of {ctx.base_ref}")
    return [f"{first}: {f}" for f in found]


def _adding_commit(ctx: Context, path: str, added: dict[str, int]) -> str | None:
    """The commit that added *path*: the base ref's log for a base file, else the branch scan.

    A path the base ref holds with head's blob keeps the base add, so a copy
    cannot hide an older failed run; the branch scan sees a merge's own add.
    """
    base_blob = ctx.git.tree_blobs(ctx.base_ref, path).get(path)
    at_base = base_blob is not None and base_blob == ctx.git.tree_blobs(ctx.head, path).get(path)
    if not at_base and path in added:
        return ctx.commits[added[path]]
    found: str | None = ctx.git.adding_commit(ctx.base_ref if at_base else ctx.head, path)
    return found


def _deciding_run(
    ctx: Context, paths: list[str], added: dict[str, int]
) -> tuple[str | None, list[str]]:
    """The results file whose adding commit precedes every other candidate's, or findings.

    A traversal order cannot pick the first run: two files added on parallel
    branches have no first, and picking the passing one would let a failed
    run hide. Such a pair, or two first candidates added in one commit, fails closed.
    """
    if len(paths) == 1:
        return paths[0], []
    adds: dict[str, str] = {}
    for path in paths:
        commit = _adding_commit(ctx, path, added)
        if commit is None:
            return None, [
                f"{path} has no adding commit in the history, so the first run is unknown"
            ]
        adds[path] = commit
    first = [
        p
        for p in paths
        if not any(
            adds[o] != adds[p] and ctx.git.is_ancestor(adds[o], adds[p]) is True for o in paths
        )
    ]
    if len(first) == 1:
        return first[0], []
    twin = next((o for o in first[1:] if adds[o] == adds[first[0]]), None)
    where = "in the same commit" if twin else "on parallel branches"
    return None, [_ambiguous(first[0], twin or first[1], where)]


def _ambiguous(one: str, other: str, where: str) -> str:
    return (
        f"results files {one} and {other} were added {where}, so the first run is "
        "ambiguous; results files are append-only, so fix the skill to start a new first run"
    )


# A gated change may not also change the code that judges it: every repo
# module this check imports, the runner and its imports included.
# ``test_judge_paths_cover_every_imported_module`` recomputes that closure.
_JUDGE_PATHS = (
    "scripts/__init__.py",
    "scripts/cli_exec.py",
    "scripts/eval/eval-prompt-change.py",
    "scripts/eval/_",
    # The whole package: a new module or subpackage could shadow an imported one.
    "scripts/hook_utilities/",
    "scripts/validation/__init__.py",
    "scripts/validation/check_skill_rewrite_evidence.py",
    "scripts/validation/checks_common.py",
    "scripts/validation/evidence.py",
    "scripts/validation/models.py",
    "scripts/validation/pre_pr_console.py",
    "scripts/validation/skill_rewrite_context.py",
    "scripts/validation/skill_rewrite_evidence.py",
    "scripts/validation/skill_rewrite_scenarios.py",
    "scripts/validation/skill_rewrite_skills.py",
    "scripts/validation/subprocess_runner.py",
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
    errors = [e for e in (base.error, side.error, side.tools_error) if e and side.skill_md_path]
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
    # Pin both symbolic refs once, so the diff and every later read see the same commits.
    head = git.text("rev-parse", "--verify", f"{head}^{{commit}}").strip()
    base_ref = git.text("rev-parse", "--verify", f"{base_ref}^{{commit}}").strip()
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
