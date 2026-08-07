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
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.detect_scope_explosion import ScopeResult

GH_TIMEOUT_SECONDS = 5


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
    only when exactly one open PR matches. Both halves of that are load
    bearing:

    * ``--state open``. ``gh pr view`` falls back to a closed or merged PR when
      no open one exists. Verified against gh 2.97.0: on a branch whose PR had
      already merged, ``gh pr view`` returned that PR with ``state=MERGED``.
      A reused branch would then be measured against a dead PR's base.
    * exactly one match. Several open PRs can share a head branch, and picking
      one of them is a guess. No answer is better than a guess here, because
      the guess can only ever remove a block.

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
                "baseRefName",
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
    base = str(entry.get("baseRefName") or "").strip()
    return base or None


def is_credible_rescope(rescoped: ScopeResult | None, blocked: ScopeResult) -> bool:
    """Return True when ``rescoped`` is a believable narrowing of ``blocked``.

    Two failure modes make an unbelievable result look like a clean pass, and
    both are silent:

    * ``get_index_files_against_ref`` returns ``[]`` on any nonzero ``git
      diff``, and ``detect_scope`` turns that into ``ScopeResult(file_count=0)``
      rather than None. A diff that fails against an otherwise-resolvable ref
      (a missing tree in a partial clone, for instance) therefore reads as
      "this PR changes nothing". A genuinely empty result is indistinguishable
      from that failure, so both are refused. A branch that changes nothing
      against its own base is not a branch a scope gate needs to unblock.
    * A file the main-relative measurement never saw means the two runs did not
      compare the same thing. A real stacked-base surface is a subset of the
      main-relative surface, because the stack base is downstream of main.

    Refusing here keeps the original block, which is the safe direction.
    """
    if rescoped is None:
        return False
    if rescoped.file_count <= 0:
        return False
    return set(rescoped.files).issubset(set(blocked.files))
