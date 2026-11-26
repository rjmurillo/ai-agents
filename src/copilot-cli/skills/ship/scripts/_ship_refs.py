"""Check a branch name git accepts, such as the target of an open PR (ADR-127).

``safe_ref`` in ``_ship_common`` is the reviewed allowlist for a name the user
types: it admits letters, digits, ``.``, ``_``, ``/``, and ``-`` only. A host
may hold a valid branch outside it, such as ``release/2026+hotfix``. This
module accepts those, by the rules of ``git check-ref-format`` for
``refs/heads/<name>``, so a valid target is never refused for its spelling.
A typed ``--base`` passes this check too; ``ship_detect`` then holds it to
the open PR's target, and to ``safe_ref`` when no PR is open.

Stricter than git, on purpose: a name over 255 characters, the name ``HEAD``,
and any control character git would admit (C1 controls and Unicode line
breaks) are refused, because a name is printed on one result line. A name
that starts with ``-`` is refused as well: git forbids it for a branch, and it
would read as an option in an argument list. A name is only ever an argv
element or a ``refs/remotes/<remote>/<name>`` path element, never a shell or
revision expression.

Stdlib only, Python 3.10 floor. ``tests/skills/ship/test_ship_target_branch.py``
runs the real ``git check-ref-format`` over accepted, rejected, and stricter
names, so the two cannot drift silently.
"""

from __future__ import annotations

import re

MAX_BRANCH_CHARS = 255
# git: ASCII control characters, DEL, space, and ~ ^ : ? * [ \ are never allowed.
# Added here: C1 controls and the Unicode line breaks (see the module docstring).
_FORBIDDEN_RE = re.compile(r"[\x00-\x20\x7f-\x9f\u2028\u2029~^:?*\[\\]")


def valid_branch(name: str) -> bool:
    """Return whether ``name`` is a branch git accepts under ``refs/heads/``, and safe to print."""
    if not name or len(name) > MAX_BRANCH_CHARS or name in ("HEAD", "@"):
        return False
    if name.startswith(("-", "/")) or name.endswith(("/", ".")):
        return False
    if ".." in name or "//" in name or "@{" in name or _FORBIDDEN_RE.search(name):
        return False
    return not any(part.startswith(".") or part.endswith(".lock") for part in name.split("/"))
