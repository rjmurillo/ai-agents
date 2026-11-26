"""Read the open PR for the current branch from gh or az.

Stdlib only, Python 3.10 floor. ``github_pr`` and ``ado_pr`` return a ``PrQuery``
on success. A command that failed returns its ``Completed``, and a reply that did
not parse returns a ``str`` detail. ``ship_detect`` turns either into its ``Halt``;
this module never imports it, so the one ``Halt`` type stays shared.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import _ship_common as common
else:
    common = sys.modules["_ship_common"]

# number, URL, author, draft, target branch; number None means no open PR.
PrQuery = tuple[int | None, str, str, bool | None, str]
_NO_PR_SIGNAL = "no pull requests found"
_NO_OPEN_PR: PrQuery = (None, "", "", None, "")


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
