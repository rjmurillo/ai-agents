#!/usr/bin/env python3
"""Detect the ship context: VCS host, branch, base, HEAD, open PR, and mode.

Phase 1 of the ship driver (ADR-127). Prints result lines and ends on one
``NEXT:`` or ``STOP:`` line.

Result lines: HOST, REMOTE_HOST, BRANCH, BASE, HEAD, PR, PR_URL, PR_AUTHOR,
PR_DRAFT, MODE. ``PR: none`` is printed only after a query that proved no open PR
exists; a failed query is a STOP, never ``PR: none``.

Exit codes (ADR-035): 0 NEXT, 1 logic STOP, 2 config STOP, 3 external STOP,
4 auth STOP.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import _ship_common as common
    import _ship_refs as refs_mod
    import _ship_windows as windows_mod
else:
    _HERE = Path(__file__).resolve(strict=True).parent  # the real entry, never a symlink's dir
    if "_ship_common" not in sys.modules:  # pragma: no cover - fresh interpreter only
        _s = importlib.util.spec_from_file_location("_ship_common", _HERE / "_ship_common.py")
        _s.loader.exec_module(
            sys.modules.setdefault("_ship_common", importlib.util.module_from_spec(_s))
        )
    common = sys.modules["_ship_common"]
    windows_mod = common.load_sibling("_ship_windows")
    refs_mod = common.load_sibling("_ship_refs")

SCRIPT = "ship_detect.py"
REASONS = frozenset(
    {
        "bad-arguments",
        "no-repo",
        "no-origin",
        "unsupported-remote",
        "detached-head",
        "on-base-branch",
        "pr-query-failed",
        "user-query-failed",
        "auth-failed",
        "pr-author-unknown",
        "unsafe-checkout",
        "base-mismatch",
    }
)
# number, URL, author, draft, target branch; number None means no open PR.
PrQuery = tuple[int | None, str, str, bool | None, str]
_NO_PR_SIGNAL = "no pull requests found"
# Phrases a CLI prints for an auth failure. Bare words such as "authentication"
# also appear in echoed branch names and titles, so they are not signals.
_AUTH_SIGNALS = (
    "gh auth login",
    "authentication failed",
    "authentication required",
    "http 401",
    "401 unauthorized",
    "bad credentials",
    "az login",
)
# gh echoes a branch or title in double quotes: that is user data, never a cause.
# Single quotes stay, since az prints its own advice that way (Please run 'az login').
_QUOTED_RE = re.compile(r'"[^"]*"')


@dataclass(frozen=True)
class Context:
    root: Path
    host: str
    remote_host: str
    branch: str
    base: str
    head: str
    pr: int | None
    pr_url: str
    pr_author: str
    mode: str
    pr_draft: bool | None = None


@dataclass(frozen=True)
class Halt:
    reason: str
    code: int
    detail: str = ""


def _auth_failure(stderr: str) -> bool:
    lowered = _QUOTED_RE.sub(" ", stderr).lower()
    return any(signal in lowered for signal in _AUTH_SIGNALS)


def query_halt(reason: str, done: common.Completed) -> Halt:
    """A Halt naming the cause: auth signals anywhere in stderr win over the last line."""
    lines = [line for line in done.stderr.splitlines() if line.strip()]
    auth = [line for line in lines if _auth_failure(line)]
    detail = auth[-1:] or [common.cause_line(done.stderr, f"exit {done.returncode}")]
    if _auth_failure(done.stderr):
        return Halt("auth-failed", common.EXIT_AUTH, detail[0])
    return Halt(reason, common.EXIT_EXTERNAL, detail[0])


def default_branch(root: Path) -> str:
    """The origin default branch: origin/HEAD, else origin/main or origin/master, else main."""
    done = common.git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd=root)
    value = done.stdout.strip()
    if done.returncode == 0 and value.startswith("origin/"):
        candidate = value[len("origin/") :]
        if common.safe_ref(candidate):
            return candidate
    for candidate in ("main", "master"):
        probe = ["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{candidate}"]
        if common.git(probe, cwd=root).returncode == 0:
            return candidate
    return "main"


# A branch ship never publishes from, whatever --base says.
PROTECTED_BRANCHES = frozenset({"main", "master"})


def protected_branches(base: str, origin_default: str) -> frozenset[str]:
    """The branches no owner run may ship from: main, master, the base, the origin default."""
    return PROTECTED_BRANCHES | {base, origin_default}


_NO_OPEN_PR: PrQuery = (None, "", "", None, "")


def _github_pr(root: Path) -> PrQuery | Halt:
    fields = "number,author,state,url,isDraft,baseRefName"
    done = common.run(["gh", "pr", "view", "--json", fields], cwd=root)
    if done.returncode != 0:
        if _NO_PR_SIGNAL in done.stderr.lower():
            return _NO_OPEN_PR
        return query_halt("pr-query-failed", done)
    data = common.parse_json(done.stdout)
    if not isinstance(data, dict) or not isinstance(data.get("number"), int):
        return Halt("pr-query-failed", common.EXIT_EXTERNAL, "gh returned no PR number")
    if data.get("state") != "OPEN":
        return _NO_OPEN_PR
    raw_author = data.get("author")
    author = raw_author if isinstance(raw_author, dict) else {}
    draft = data.get("isDraft") if isinstance(data.get("isDraft"), bool) else None
    login = str(author.get("login") or "")
    target = str(data.get("baseRefName") or "")
    return (data["number"], str(data.get("url", "")), login, draft, target)


def _github_user(root: Path, host_name: str) -> str | Halt:
    # gh api ignores the origin remote, so name the host: on GitHub Enterprise
    # the login must come from the same host as the PR author.
    done = common.run(["gh", "api", "user", "--jq", ".login", "--hostname", host_name], cwd=root)
    login = done.stdout.strip()
    if done.returncode != 0 or not login:
        return query_halt("user-query-failed", done)
    return login


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


def _ado_pr(root: Path, branch: str, base: str | None = None) -> PrQuery | Halt:
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
        return query_halt("pr-query-failed", done)
    data = common.parse_json(done.stdout)
    if not isinstance(data, list):
        return Halt("pr-query-failed", common.EXIT_EXTERNAL, "az returned no PR list")
    if not data:
        return _NO_OPEN_PR
    chosen = _ado_row_for_base(data, base)
    first = chosen if isinstance(chosen, dict) else {}
    pr_id = first.get("pullRequestId")
    if not isinstance(pr_id, int):
        return Halt("pr-query-failed", common.EXIT_EXTERNAL, "az returned no pullRequestId")
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


def _ado_user(root: Path) -> str | Halt:
    done = common.run(
        ["az", "account", "show", "--query", "user.name", "--output", "tsv"], cwd=root
    )
    name = done.stdout.strip()
    if done.returncode != 0 or not name:
        return query_halt("user-query-failed", done)
    return name


def unsafe_checkout(root: Path) -> Halt | None:
    """On Windows, a Halt when ``root`` holds a file CreateProcess would run for git, gh, or az.

    CreateProcess searches the current directory before ``PATH``. Helpers run
    with the checkout root as their directory, and a bare git they spawn
    themselves is searched there first, so a committed ``git.exe`` would run in
    place of git (CWE-427). ``common.run`` resolves its own names on ``PATH``,
    so the check of this process's directory is defense in depth: it holds if a
    helper is ever run without ``cwd``. Elsewhere the check does not apply.
    """
    if not common.on_windows():
        return None
    places = dict.fromkeys([root.resolve(), Path.cwd().resolve()])
    planted = [
        str(place / name) for place in places for name in windows_mod.planted_programs(place)
    ]
    if not planted:
        return None
    detail = (
        f"{', '.join(planted)} would run instead of the installed program on Windows; "
        "remove or rename it"
    )
    return Halt("unsafe-checkout", common.EXIT_CONFIG, detail)


def _checkout(cwd: Path | None) -> tuple[Path, str, str, str, str] | Halt:
    """Return root, host, remote host, branch, and HEAD of the local checkout."""
    root = common.repo_root(cwd)
    if root is None:
        return Halt("no-repo", common.EXIT_CONFIG, "not inside a git work tree")
    unsafe = unsafe_checkout(root)
    if unsafe is not None:
        return unsafe
    origin = common.git(["remote", "get-url", "origin"], cwd=root)
    if origin.returncode != 0 or not origin.stdout.strip():
        return Halt("no-origin", common.EXIT_CONFIG, "origin remote is not configured")
    host_name = common.remote_host(origin.stdout)
    if host_name is None:
        return Halt(
            "unsupported-remote",
            common.EXIT_CONFIG,
            "origin is not an https, ssh, or scp-style remote",
        )
    branch_done = common.git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    branch = branch_done.stdout.strip()
    if branch_done.returncode != 0 or branch in ("", "HEAD"):
        return Halt("detached-head", common.EXIT_CONFIG, "HEAD is not on a branch")
    if not common.safe_ref(branch):
        return Halt("bad-arguments", common.EXIT_CONFIG, "branch name is not a plain ref")
    head = common.git(["rev-parse", "HEAD"], cwd=root).stdout.strip()
    return root, common.classify_host(host_name), host_name, branch, head


def _mode(root: Path, host: str, pr: int | None, author: str, host_name: str) -> str | Halt:
    """Return owner or contributor. An open PR needs a positive identity match."""
    if pr is None:
        return "owner"
    # A PR whose author the host did not return cannot prove the branch is yours.
    if not author.strip():
        return Halt(
            "pr-author-unknown", common.EXIT_EXTERNAL, f"PR {pr} has no author in the host reply"
        )
    me = _github_user(root, host_name) if host == "github" else _ado_user(root)
    if isinstance(me, Halt):
        return me
    return "owner" if author.strip().lower() == me.strip().lower() else "contributor"


def _pr_base(pr: int, pr_target: str, base: str | None) -> str | Halt:
    """The base of open PR ``pr``: its target branch, which ``--base`` may only repeat.

    The host named the target, so it need only be a branch git accepts, such as
    ``release/2026+hotfix``. It reaches git as one argv element or a
    ``refs/remotes/origin/<target>`` path, never as an option or a shell word.
    """
    if not pr_target or not refs_mod.valid_branch(pr_target):
        return Halt("pr-query-failed", common.EXIT_EXTERNAL, f"PR {pr} has no target branch")
    if base is not None and base != pr_target:
        detail = f"--base {base} is not the target of open PR {pr}, {pr_target}"
        return Halt("base-mismatch", common.EXIT_CONFIG, detail)
    return pr_target


def base_arg_ok(base: str) -> bool:
    """Whether ``--base`` may reach ``detect``: a plain ref, or a valid branch an open PR may target.

    ``detect`` then holds a branch outside the plain-ref rule to the open PR's own target.
    """
    return common.safe_ref(base) or refs_mod.valid_branch(base)


def detect(cwd: Path | None = None, base: str | None = None) -> Context | Halt:
    """Return the ship context, or the Halt that stops the run."""
    checkout = _checkout(cwd)
    if isinstance(checkout, Halt):
        return checkout
    root, host, host_name, branch, head = checkout
    origin_default = default_branch(root)
    target = base or origin_default
    pr_query = _github_pr(root) if host == "github" else _ado_pr(root, branch, base)
    if isinstance(pr_query, Halt):
        return pr_query
    pr, pr_url, author, pr_draft, pr_target = pr_query
    mode = _mode(root, host, pr, author, host_name)
    if isinstance(mode, Halt):
        return mode
    if pr is not None:
        # An open PR fixes the base: its diff is against its own target branch.
        pr_base = _pr_base(pr, pr_target, base)
        if isinstance(pr_base, Halt):
            return pr_base
        target = pr_base
    elif base is not None and not common.safe_ref(base):
        # A new PR sends --base to the host and, on Windows, through cmd.exe: the strict rule.
        return Halt("bad-arguments", common.EXIT_CONFIG, "--base is not a plain ref")
    # The same set publish refuses, so the refusal comes in phase 1.
    if mode == "owner" and pr is None and branch in protected_branches(target, origin_default):
        return Halt("on-base-branch", common.EXIT_LOGIC, f"on {branch}; create a feature branch")
    return Context(root, host, host_name, branch, target, head, pr, pr_url, author, mode, pr_draft)


def add_context_lines(result: common.Result, ctx: Context, *, pr_key: str = "PR") -> None:
    result.add("HOST", ctx.host)
    result.add("REMOTE_HOST", ctx.remote_host)
    result.add("BRANCH", ctx.branch)
    result.add("BASE", ctx.base)
    result.add("HEAD", ctx.head)
    result.add(pr_key, ctx.pr if ctx.pr is not None else "none")
    if ctx.pr_url:
        result.add("PR_URL", ctx.pr_url)
    if ctx.pr_author:
        result.add("PR_AUTHOR", ctx.pr_author)
    if ctx.pr is not None:
        result.add("PR_DRAFT", "unknown" if ctx.pr_draft is None else str(ctx.pr_draft).lower())
    result.add("MODE", ctx.mode)


def build_parser() -> common.ResultParser:
    parser = common.ResultParser(prog=SCRIPT, description="Detect the ship context.")
    parser.add_argument("--base", default=None, help="Target branch (default: origin HEAD)")
    common.add_output_format_arg(parser)
    return parser


def run(argv: list[str]) -> tuple[common.Result, str, Path | None]:
    result = common.Result(SCRIPT, REASONS)
    try:
        args = build_parser().parse_args(argv)
    except common.UsageError as exc:
        return result.stop("bad-arguments", common.EXIT_CONFIG, exc), common.peek_format(argv), None
    fmt = common.resolve_format(args.output_format)
    if args.base is not None and not base_arg_ok(args.base):
        return (
            result.stop("bad-arguments", common.EXIT_CONFIG, "--base is not a plain ref"),
            fmt,
            None,
        )
    ctx = detect(base=args.base)
    if isinstance(ctx, Halt):
        return result.stop(ctx.reason, ctx.code, ctx.detail), fmt, common.repo_root()
    add_context_lines(result, ctx)
    result.next("validate-only" if ctx.mode == "contributor" else "preflight")
    return result, fmt, ctx.root


def main(argv: list[str] | None = None) -> int:
    result, fmt, root = run(sys.argv[1:] if argv is None else argv)
    return common.emit(result, fmt, root)


if (
    __name__ == "__main__"
):  # pragma: no cover - runs only in a fresh interpreter; see test_ship_edges.py::test_script_runs_under_isolated_mode
    raise SystemExit(main())
