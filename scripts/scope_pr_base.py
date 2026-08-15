#!/usr/bin/env python3
"""PR base resolution for the scope gate.

The scope gate measures a branch against main. A stacked PR sits on another
PR, so measured against main it carries every file its whole stack touched,
which is not the surface any reviewer of that PR reads.

This module owns the three pieces that let the gate ask "what is this PR
really built on": the remote-prefix normalization, the gh lookup, and the
credibility test that decides whether a second measurement may be trusted.

It deliberately does not own the orchestration. ``detect_scope_explosion``
keeps that, so this module has no dependency on scope detection and the two
can be tested apart.

Everything here can only ever *remove* a block, so every function fails
closed: an uncertain answer is None or False, and the caller keeps whatever
the main-relative measurement said.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from scripts.detect_scope_explosion import ScopeResult

GH_TIMEOUT_SECONDS = 5

_PLAIN_BRANCH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_RESERVED_BRANCH_NAMES = frozenset({"HEAD", "FETCH_HEAD", "ORIG_HEAD", "MERGE_HEAD"})


def _is_plain_branch_name(name: str) -> bool:
    """Return True when ``name`` is an ordinary branch name and nothing else.

    The resolved base reaches git as ``origin/<name>``, so a name that carries
    revision syntax resolves to something other than a branch. ``HEAD`` is the
    clearest case: ``origin/HEAD`` resolves to the remote's default branch, so
    a base of ``HEAD`` would silently measure against a branch nobody named.

    The pattern also rejects a leading dash, ``..`` range syntax, ``~`` and
    ``^`` walk syntax, ``:`` and ``@{`` selectors, whitespace, and an empty
    string. It is deliberately narrower than ``git check-ref-format``: this is
    an allowlist for the shapes real branch names take, not a parser, and the
    cost of rejecting an exotic-but-legal name is that the original block
    stands.
    """
    if not name or name in _RESERVED_BRANCH_NAMES:
        return False
    if ".." in name or name.endswith((".lock", "/")):
        return False
    return bool(_PLAIN_BRANCH_NAME.fullmatch(name))


def strip_remote_prefix(base: str) -> str:
    """Return ``base`` without a leading ``origin/``.

    The pre-push hook passes ``--base-branch origin/main`` while the
    pre-commit hook passes nothing and defaults to ``main``. Both name the
    same branch, so comparisons against a resolved PR base have to normalize
    first or every pre-push run looks like a base mismatch.
    """
    prefix = "origin/"
    return base[len(prefix) :] if base.startswith(prefix) else base


def resolve_pr_base_branch(branch: str) -> str | None:
    """Return the base branch of the single open PR for ``branch``, else None.

    Queries ``gh pr list --state open --head <branch>`` and accepts the answer
    only when exactly one open PR matches and that PR's head branch lives in
    this repository. All three of those are load bearing:

    * ``--state open``. ``gh pr view`` falls back to a closed or merged PR when
      no open one exists. Verified against gh 2.97.0: on a branch whose PR had
      already merged, ``gh pr view`` returned that PR with ``state=MERGED``.
      A reused branch would then be measured against a dead PR's base.
    * exactly one match. Several open PRs can share a head branch, and picking
      one of them is a guess. No answer is better than a guess here, because
      the guess can only ever remove a block.
    * head branch in this repository. ``--head`` filters on the branch name
      alone, so a pull request opened from a fork whose head branch happens to
      share this branch's name matches too. When the local branch has no PR of
      its own, that fork PR would be the single match, and a stranger would be
      choosing the base this gate measures against. ``isCrossRepository`` is
      false only when head and base live in the same repository, so requiring
      it to be false confines the answer to branches a collaborator pushed
      here.

    Returns None when gh is absent, unauthenticated, offline, or when the
    branch has no open PR. Every one of those is a normal local state, so the
    caller must treat None as "no better answer available" rather than an
    error.

    Known limitation: in a ``pr-<number>`` worktree the local branch name can
    differ from the PR's head branch, so no PR matches and this returns None.
    That leaves the original main-relative block in place, which is the
    behavior before this function existed. It never invents a base.
    ``scripts/validation/checks_common.py`` carries an upstream-head fallback
    for that case (added for issue #4382, closed 2026-08-04); it is
    deliberately not reused here, because it would widen a lookup whose only
    power is to remove a block.

    The five second timeout is deliberate. This runs inside a git hook, and a
    hook that waits on a hung network call is worse than a hook that measures
    against the wrong base.
    """
    if not shutil.which("gh"):
        return None
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--head",
                branch,
                "--json",
                "baseRefName,isCrossRepository",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GH_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list) or len(payload) != 1:
        return None
    entry = payload[0]
    if not isinstance(entry, dict):
        return None
    if entry.get("isCrossRepository") is not False:
        return None
    base = entry.get("baseRefName")
    if not isinstance(base, str):
        return None
    return base.strip() if _is_plain_branch_name(base.strip()) else None


def is_credible_rescope(
    rescoped: ScopeResult | None,
    blocked: ScopeResult,
    is_ancestor: Callable[[str, str], bool],
) -> bool:
    """Return True when ``rescoped`` is a believable narrowing of ``blocked``.

    Three conditions have to hold, and each one exists because its absence
    looked like a clean pass:

    * The result is not None.
    * Both measurements name the same branch. Each call re-reads HEAD, so
      nothing in the types binds them together. A checkout landing between
      them substitutes a different branch, and if that branch is stacked on
      the same parent its small file count and its ancestry both check out.
      The original branch's block clears on a number that was never measured
      against it. The branch name is already on the record, so comparing it
      is the whole fix.
    * The file count is positive. ``get_index_files_against_ref`` now raises
      ``ScopeDetectionError`` on any nonzero ``git diff``. Quoted rather than
      paraphrased, because this branch is the whole reason the condition exists,
      ``scripts/detect_scope_explosion.py:201-203``::

          if result.returncode != 0:
              raise ScopeDetectionError(
                  f"git diff --cached against {base_ref} failed (rc={result.returncode}): "

      ``rescope_against_pr_base`` catches that exception and keeps the original
      block, so a zero-file result now means a real empty diff rather than a
      failed re-measurement. That still is not a branch a scope gate needs to
      unblock, so zero is refused here too.
    * The two measurements forked from the same history, and the rescoped one
      forked later. See below.

    The fork-point test is what makes the second number comparable to the
    first. ``blocked.merge_base`` is where this branch left the main-relative
    base; ``rescoped.merge_base`` is where it left the PR base. A genuine stack
    leaves main first and its stack base second, so the first is a strict
    ancestor of the second.

    An earlier version tested path-set containment instead, on the reasoning
    that a stacked surface is a subset of the main-relative surface. That is
    false. Verified on a constructed repository: main holds 52 files, the
    parent changes all 52, and the child reverts one of them to main's content.
    The child changes 51 files against main and exactly 1 against its parent,
    and that 1 file is absent from the main-relative set because the child
    agrees with main about it. Containment rejected an honest one-file stacked
    PR and left it blocked at 51, which is the case this whole path exists to
    fix. Containment is neither necessary nor sufficient; ancestry is a
    property of the graph rather than of the diff.

    Strictness matters in the other direction too. An unrelated branch that
    merely happens to be reachable shares main's fork point exactly, so
    requiring a *strict* ancestor rejects it. So does naming the base already
    measured, which would be a no-op.

    ``is_ancestor`` is injected rather than imported to keep this module free
    of a runtime dependency on the scope detector, which imports this one.

    Refusing here keeps the original block, which is the safe direction.
    """
    if rescoped is None:
        return False
    if rescoped.file_count <= 0:
        return False
    if rescoped.current_branch != blocked.current_branch:
        return False
    if not rescoped.merge_base or not blocked.merge_base:
        return False
    if rescoped.merge_base == blocked.merge_base:
        return False
    return is_ancestor(blocked.merge_base, rescoped.merge_base)
