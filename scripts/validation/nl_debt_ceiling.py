"""Base-ref ceiling for the NL structural debt ratchet (issue #6506).

Split out of ``check_nl_structural_debt.py`` to keep that file under the taste
file-size ceiling. The ratchet's baseline lives in the PR head, so on its own it
lets a branch raise its own allowance. This module reads the baseline recorded at
the fork point of HEAD and a base ref, merges it with the working-tree one so the
working-tree file can only tighten the allowance, and compares a measurement with
the result.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.ci.count_ratchet import git_environment

Baseline = dict[str, dict[str, Any]]

COUNT_SECTIONS = ("duplicate_blocks", "cohesion")
"""Sections that map a key to a positive count. The stricter allowance is the lower count."""

KEY_SECTIONS = ("cardinality",)
"""Sections that map a key to text. The stricter allowance is the keys both baselines hold."""

SECTIONS = (*COUNT_SECTIONS, *KEY_SECTIONS)

GIT_TIMEOUT_SECONDS = 30
"""Bound on each git read. A hung read becomes ``BaseRefError`` (exit 3), not a stalled gate."""


class BaseRefError(Exception):
    """Git cannot name a fork point or read the baseline at the base ref."""


def _git(repo_root: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run git in ``repo_root`` with every ``GIT_*`` variable removed.

    An exported ``GIT_DIR`` (set by ``git push`` for a linked worktree) beats
    ``-C`` and would read another checkout, so the ambient environment is not
    passed through (``scripts/ci/count_ratchet.py:git_environment``).
    """
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *argv],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=git_environment(),
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise BaseRefError(
            f"git {argv[0]} did not finish within {GIT_TIMEOUT_SECONDS}s: {exc}"
        ) from exc
    except OSError as exc:
        raise BaseRefError(f"git could not be launched: {exc}") from exc


def _absent_at(root: Path, sha: str, baseline_rel: str) -> bool:
    """True when commit ``sha`` records no file at ``baseline_rel`` (the bootstrap case).

    ``ls-tree`` exits 0 with empty output for an absent path and non-zero for a
    path it will not look up, so an unreadable tree raises instead of reading as
    "first run", which would skip the comparison (``count_ratchet.baseline_absent_at_ref``
    documents the split). It runs through ``_git`` so it carries the same timeout.
    """
    listed = _git(root, "ls-tree", sha, "--", baseline_rel)
    if listed.returncode != 0:
        detail = listed.stderr.strip() or "git ls-tree failed"
        raise BaseRefError(f"could not list {baseline_rel} at {sha[:12]}: {detail}")
    return listed.stdout.strip() == ""


def ceiling_baseline(
    repo_root: Path,
    base_ref: str | None,
    baseline_rel: str,
    parse: Callable[[str, str], Baseline],
) -> Baseline | None:
    """Return the baseline recorded at the fork point of HEAD and ``base_ref``.

    None means no ceiling applies, and the run says why on stderr. With no ref the
    working-tree baseline is the only allowance, which a branch can edit; the run
    states that rather than reporting a ratchet it did not apply. With a ref, None
    means the fork point records no baseline yet: the branch introduces the
    ratchet, so there is no earlier ceiling to raise. Every other failure raises:
    an unnamed fork point (shallow clone, unrelated history) or an unreadable
    ref must not read as "nothing to compare against", or the gate fails open.
    ``parse`` validates the document and raises on a malformed one.

    The fork point, not the ref tip, so a base that burned debt down after the
    branch forked is not blamed on the branch. In CI the checkout is the PR
    merge commit, whose fork point with the base is the base tip.
    """
    if base_ref is None:
        print("[NOTE] no base ref: the working-tree baseline is the only ceiling", file=sys.stderr)
        return None
    root = repo_root.resolve()
    # `--` keeps a ref that starts with `-` from being read as a git option.
    fork = _git(root, "merge-base", "--", "HEAD", base_ref)
    fork_sha = fork.stdout.strip()
    if fork.returncode != 0 or not fork_sha:
        detail = fork.stderr.strip() or "no common ancestor"
        raise BaseRefError(
            f"no merge base between HEAD and {base_ref} ({detail}); a mistyped ref needs "
            "fixing, a shallow clone needs more history (git fetch --unshallow)"
        )
    where = f"{base_ref} (fork {fork_sha[:12]})"
    if _absent_at(root, fork_sha, baseline_rel):
        print(f"[WARN] {baseline_rel} is absent at {where}: bootstrap run", file=sys.stderr)
        return None
    shown = _git(root, "show", f"{fork_sha}:{baseline_rel}")
    if shown.returncode != 0:
        detail = shown.stderr.strip() or "git show failed"
        raise BaseRefError(f"could not read {baseline_rel} at {where}: {detail}")
    ceiling = parse(shown.stdout, f"{baseline_rel} at {where}")
    print(f"[NOTE] ceiling read from {baseline_rel} at {where}", file=sys.stderr)
    return ceiling


def tighten(baseline: Baseline, ceiling: Baseline) -> Baseline:
    """Return the stricter of two baselines: a key survives only where both hold it.

    A working-tree entry above, or absent from, the ceiling is a raise this
    branch made. It must not widen the allowance.
    """
    tightened: Baseline = {}
    for section in COUNT_SECTIONS:
        held = ceiling[section]
        tightened[section] = {
            key: min(value, held[key]) for key, value in baseline[section].items() if key in held
        }
    for section in KEY_SECTIONS:
        tightened[section] = {
            key: value for key, value in baseline[section].items() if key in ceiling[section]
        }
    return tightened


def _allowed_label(allowed: int, recorded: int) -> str:
    """Name the source of an allowance: a recorded value above it was capped by the base ref."""
    if recorded > allowed:
        return f"base-ref ceiling {allowed} (working-tree baseline says {recorded})"
    return f"baseline {allowed}"


def compare(
    current: dict[str, dict[str, Any]],
    baseline: dict[str, dict[str, Any]],
    ceiling: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (growth, shrink) findings; growth always fails, shrink demands a baseline update.

    Growth is measured against the stricter of ``baseline`` and ``ceiling`` (the
    baseline recorded at the base ref), so a raised working-tree baseline cannot
    cover new debt. Shrink is measured against ``baseline`` alone: the working-tree
    file must record every burn-down.
    """
    growth: list[str] = []
    shrink: list[str] = []
    allowance = baseline if ceiling is None else tighten(baseline, ceiling)
    for key, count in current["duplicate_blocks"].items():
        allowed = allowance["duplicate_blocks"].get(key, 0)
        if count > allowed:
            label = _allowed_label(allowed, baseline["duplicate_blocks"].get(key, 0))
            growth.append(f"duplicate block {key}: {count} shared windows, {label}")
    for key in current["cardinality"]:
        if key not in allowance["cardinality"]:
            note = " (listed in the working-tree baseline, absent at the base ref)"
            note = note if key in baseline["cardinality"] else ""
            growth.append(f"stale count {key}: write `{current['cardinality'][key]}` instead{note}")
    for key, spread in current["cohesion"].items():
        allowed = allowance["cohesion"].get(key, 0)
        if spread > allowed:
            label = _allowed_label(allowed, baseline["cohesion"].get(key, 0))
            growth.append(f"low cohesion {key}: {spread} unrelated roots, {label}")
    for key, allowed in baseline["cohesion"].items():
        if current["cohesion"].get(key, 0) < allowed:
            shrink.append(f"low cohesion {key} shrank below baseline {allowed}")
    for key, allowed in baseline["duplicate_blocks"].items():
        if current["duplicate_blocks"].get(key, 0) < allowed:
            shrink.append(f"duplicate block {key} shrank below baseline {allowed}")
    shrink.extend(
        f"stale count {key} is gone"
        for key in baseline["cardinality"]
        if key not in current["cardinality"]
    )
    return sorted(growth), sorted(shrink)


def remediation(capped: bool = False) -> str:
    text = (
        "Fix, in order of preference: delete the repeated text; keep one owner and "
        "depend on it; drop the derived count; split a rule that claims unrelated roots by "
        "responsibility. Do not resync copies, because a "
        "synchronized copy keeps the obligation. To lock in a burn-down, run "
        "`uv run python scripts/validation/check_nl_structural_debt.py --update-baseline`."
    )
    if not capped:
        return text
    return text + (
        " A ceiling taken from the base ref cannot be raised on the branch, and "
        "`--update-baseline` will not clear it."
    )


def default_base_ref(repo_root: Path) -> str | None:
    """Base ref for the local gate, or None when nothing resolves (non-git harnesses).

    Imported at call time: ``checks_common`` pulls in the pre-PR runner helpers,
    which a plain CLI run does not need.
    """
    from checks_common import _refresh_remote_base, _resolve_default_base_ref

    base_ref: str | None = _resolve_default_base_ref(repo_root)
    if base_ref is not None:
        failure = _refresh_remote_base(base_ref, repo_root)
        if failure:
            print(
                f"[WARN] could not refresh {base_ref} ({failure}); "
                "continuing with the local ref, which may be stale",
                file=sys.stderr,
            )
    return base_ref
