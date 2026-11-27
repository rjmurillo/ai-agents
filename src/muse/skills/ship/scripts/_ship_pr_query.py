"""Read the open PR for the current branch, and check the branch names a PR can target.

Stdlib only, Python 3.10 floor. ``github_pr`` and ``ado_pr`` return a ``PrQuery``
on success. A command that failed returns its ``Completed``, and a reply that did
not parse returns a ``str`` detail. ``ship_detect`` turns either into its ``Halt``;
this module never imports it, so the one ``Halt`` type stays shared.

``base_remote`` finds the git remote that holds the open PR's target branch: ``origin``,
or, when the PR belongs to another repository as with a fork, the remote that names it.

``valid_branch`` checks a branch name git accepts, such as the target of an open
PR, including the typed ``--base``. ``safe_ref`` in ``_ship_common`` is the
reviewed allowlist for a name the user types: it admits letters, digits, ``.``,
``_``, ``/``, and ``-`` only. A host may hold a valid branch outside it, such as
``release/2026+hotfix``. ``valid_branch`` accepts those, by the rules of
``git check-ref-format`` for ``refs/heads/<name>``, so a valid target is never
refused for its spelling. A typed ``--base`` passes this check too;
``ship_detect`` then holds it to the open PR's target, and to ``safe_ref`` when
no PR is open.

Stricter than git, on purpose: a name over 255 characters, the name ``HEAD``,
and any control character git would admit (C1 controls and Unicode line
breaks) are refused, because a name is printed on one result line. A name
that starts with ``-`` is refused as well: git forbids it for a branch, and it
would read as an option in an argument list. A name is only ever an argv
element or a ``refs/remotes/<remote>/<name>`` path element, never a shell or
revision expression.

``tests/skills/ship/test_ship_target_branch.py`` runs the real
``git check-ref-format`` over accepted, rejected, and stricter names, so the
two cannot drift silently.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import _ship_common as common
    import _ship_repo as repo_mod
else:
    common = sys.modules["_ship_common"]
    repo_mod = common.load_sibling("_ship_repo")

# number, URL, author, draft, target branch; number None means no open PR.
PrQuery = tuple[int | None, str, str, bool | None, str]
_NO_PR_SIGNAL = "no pull requests found"
_NO_OPEN_PR: PrQuery = (None, "", "", None, "")
MAX_BRANCH_CHARS = 255
# git: ASCII control characters, DEL, space, and ~ ^ : ? * [ \ are never allowed.
# Added here: C1 controls and the Unicode line breaks (see the module docstring).
_FORBIDDEN_RE = re.compile(r"[\x00-\x20\x7f-\x9f\u2028\u2029~^:?*\[\\]")


def github_pr(root: Path) -> PrQuery | common.Completed | str:
    fields = "number,author,state,url,isDraft,baseRefName"
    done = common.run(["gh", "pr", "view", "--json", fields], cwd=root)
    if done.returncode != 0:
        if _NO_PR_SIGNAL in done.stderr.lower():
            return _NO_OPEN_PR
        return done
    data = common.parse_json(done.stdout)
    if not isinstance(data, dict) or not isinstance(data.get("number"), int):
        return "gh returned no PR number"
    if data.get("state") != "OPEN":
        return _NO_OPEN_PR
    raw_author = data.get("author")
    author = raw_author if isinstance(raw_author, dict) else {}
    draft = data.get("isDraft") if isinstance(data.get("isDraft"), bool) else None
    login = str(author.get("login") or "")
    target = str(data.get("baseRefName") or "")
    return (data["number"], str(data.get("url", "")), login, draft, target)


def base_remote(root: Path, pr: int | None, pr_url: str) -> tuple[str | None, str]:
    """The remote that holds the PR's target branch, and the repository label to show for it.

    ``origin`` with an empty label when no other repository owns the PR. For a PR that
    belongs to another repository, the remote that names it with the ``<owner>/<repo>``
    label; ``None`` with that label when no remote names it.
    """
    owner = repo_mod.upstream(root, pr, pr_url)
    if owner is None:
        return "origin", ""
    return repo_mod.remote_for(root, owner), f"{owner.owner}/{owner.repo}"


def _ado_row_for_base(rows: list[object], base: str | None) -> object:
    """The active PR to use. Several can share a source branch, each with its own target.

    With ``--base``, the first row that targets it; when none does, the first row,
    so ``detect`` still stops with ``base-mismatch``. Without ``--base``, the first row.
    """
    if base is None:
        return rows[0]
    wanted = f"refs/heads/{base}"
    matching = [row for row in rows if isinstance(row, dict) and row.get("targetRefName") == wanted]
    return (matching or rows)[0]


def ado_pr(root: Path, branch: str, base: str | None = None) -> PrQuery | common.Completed | str:
    done = common.run(
        [
            "az",
            "repos",
            "pr",
            "list",
            "--source-branch",
            f"refs/heads/{branch}",
            "--status",
            "active",
            "--output",
            "json",
        ],
        cwd=root,
    )
    if done.returncode != 0:
        return done
    data = common.parse_json(done.stdout)
    if not isinstance(data, list):
        return "az returned no PR list"
    if not data:
        return _NO_OPEN_PR
    chosen = _ado_row_for_base(data, base)
    first = chosen if isinstance(chosen, dict) else {}
    pr_id = first.get("pullRequestId")
    if not isinstance(pr_id, int):
        return "az returned no pullRequestId"
    raw_repository = first.get("repository")
    repository = raw_repository if isinstance(raw_repository, dict) else {}
    web_url = str(repository.get("webUrl", ""))
    url = f"{web_url}/pullrequest/{pr_id}" if web_url else ""
    raw_created_by = first.get("createdBy")
    created_by = raw_created_by if isinstance(raw_created_by, dict) else {}
    draft = first.get("isDraft") if isinstance(first.get("isDraft"), bool) else None
    target = str(first.get("targetRefName") or "")
    target = target[len("refs/heads/") :] if target.startswith("refs/heads/") else ""
    return (pr_id, url, str(created_by.get("uniqueName") or ""), draft, target)


def valid_branch(name: str) -> bool:
    """Return whether ``name`` is a branch git accepts under ``refs/heads/``, and safe to print."""
    if not name or len(name) > MAX_BRANCH_CHARS or name in ("HEAD", "@"):
        return False
    if name.startswith(("-", "/")) or name.endswith(("/", ".")):
        return False
    if ".." in name or "//" in name or "@{" in name or _FORBIDDEN_RE.search(name):
        return False
    return not any(part.startswith(".") or part.endswith(".lock") for part in name.split("/"))
