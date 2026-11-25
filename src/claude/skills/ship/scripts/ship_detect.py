#!/usr/bin/env python3
"""Detect the ship context: VCS host, branch, base, HEAD, open PR, and mode.

Phase 1 of the ship driver (ADR-127). Prints result lines and ends on one
``NEXT:`` or ``STOP:`` line.

Result lines: HOST, REMOTE_HOST, BRANCH, BASE, HEAD, PR, PR_URL, PR_AUTHOR,
MODE. ``PR: none`` is printed only after a query that proved no open PR
exists; a failed query is a STOP, never ``PR: none``.

Exit codes (ADR-035): 0 NEXT, 1 logic STOP, 2 config STOP, 3 external STOP,
4 auth STOP.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path


def _load_common():  # pragma: no cover - runs only in a fresh interpreter; see test_ship_edges.py::test_script_runs_under_isolated_mode
    name = "_ship_common"
    path = Path(__file__).resolve().with_name(f"{name}.py")
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = _load_common()

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
    }
)
_NO_PR_SIGNAL = "no pull requests found"
_AUTH_SIGNALS = ("gh auth login", "authentication", "http 401", "az login", "unauthorized")


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
    lowered = stderr.lower()
    return any(signal in lowered for signal in _AUTH_SIGNALS)


def _query_halt(reason: str, done) -> Halt:
    detail = done.stderr.strip().splitlines()[-1:] or [f"exit {done.returncode}"]
    if _auth_failure(done.stderr):
        return Halt("auth-failed", common.EXIT_AUTH, detail[0])
    return Halt(reason, common.EXIT_EXTERNAL, detail[0])


def _default_base(root: Path) -> str:
    done = common.git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd=root)
    value = done.stdout.strip()
    if done.returncode == 0 and value.startswith("origin/"):
        candidate = value[len("origin/") :]
        if common.safe_ref(candidate):
            return candidate
    return "main"


def _github_pr(root: Path) -> tuple[int | None, str, str, bool | None] | Halt:
    done = common.run(["gh", "pr", "view", "--json", "number,author,state,url,isDraft"], cwd=root)
    if done.returncode != 0:
        if _NO_PR_SIGNAL in done.stderr.lower():
            return (None, "", "", None)
        return _query_halt("pr-query-failed", done)
    data = common.parse_json(done.stdout)
    if not isinstance(data, dict) or not isinstance(data.get("number"), int):
        return Halt("pr-query-failed", common.EXIT_EXTERNAL, "gh returned no PR number")
    if data.get("state") != "OPEN":
        return (None, "", "", None)
    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    draft = data.get("isDraft") if isinstance(data.get("isDraft"), bool) else None
    return (data["number"], str(data.get("url", "")), str(author.get("login") or ""), draft)


def _github_user(root: Path) -> str | Halt:
    done = common.run(["gh", "api", "user", "--jq", ".login"], cwd=root)
    login = done.stdout.strip()
    if done.returncode != 0 or not login:
        return _query_halt("user-query-failed", done)
    return login


def _ado_pr(root: Path, branch: str) -> tuple[int | None, str, str, bool | None] | Halt:
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
        return _query_halt("pr-query-failed", done)
    data = common.parse_json(done.stdout)
    if not isinstance(data, list):
        return Halt("pr-query-failed", common.EXIT_EXTERNAL, "az returned no PR list")
    if not data:
        return (None, "", "", None)
    first = data[0] if isinstance(data[0], dict) else {}
    pr_id = first.get("pullRequestId")
    if not isinstance(pr_id, int):
        return Halt("pr-query-failed", common.EXIT_EXTERNAL, "az returned no pullRequestId")
    repository = first.get("repository") if isinstance(first.get("repository"), dict) else {}
    web_url = str(repository.get("webUrl", ""))
    url = f"{web_url}/pullrequest/{pr_id}" if web_url else ""
    created_by = first.get("createdBy") if isinstance(first.get("createdBy"), dict) else {}
    draft = first.get("isDraft") if isinstance(first.get("isDraft"), bool) else None
    return (pr_id, url, str(created_by.get("uniqueName") or ""), draft)


def _ado_user(root: Path) -> str | Halt:
    done = common.run(
        ["az", "account", "show", "--query", "user.name", "--output", "tsv"], cwd=root
    )
    name = done.stdout.strip()
    if done.returncode != 0 or not name:
        return _query_halt("user-query-failed", done)
    return name


def detect(cwd: Path | None = None, base: str | None = None) -> Context | Halt:
    """Return the ship context, or the Halt that stops the run."""
    root = common.repo_root(cwd)
    if root is None:
        return Halt("no-repo", common.EXIT_CONFIG, "not inside a git work tree")
    origin = common.git(["remote", "get-url", "origin"], cwd=root)
    if origin.returncode != 0 or not origin.stdout.strip():
        return Halt("no-origin", common.EXIT_CONFIG, "origin remote is not configured")
    host_name = common.remote_host(origin.stdout)
    if host_name is None:
        return Halt("unsupported-remote", common.EXIT_CONFIG, "origin is a local path")
    host = common.classify_host(host_name)
    branch_done = common.git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    branch = branch_done.stdout.strip()
    if branch_done.returncode != 0 or branch in ("", "HEAD"):
        return Halt("detached-head", common.EXIT_CONFIG, "HEAD is not on a branch")
    if not common.safe_ref(branch):
        return Halt("bad-arguments", common.EXIT_CONFIG, "branch name is not a plain ref")
    head = common.git(["rev-parse", "HEAD"], cwd=root).stdout.strip()
    target = base or _default_base(root)

    pr_query = _github_pr(root) if host == "github" else _ado_pr(root, branch)
    if isinstance(pr_query, Halt):
        return pr_query
    pr, pr_url, author, pr_draft = pr_query
    mode = "owner"
    if pr is not None:
        # Owner mode on an open PR needs a positive identity match. A PR whose
        # author the host did not return cannot prove the branch is yours.
        if not author.strip():
            return Halt(
                "pr-author-unknown",
                common.EXIT_EXTERNAL,
                f"PR {pr} has no author in the host reply",
            )
        me = _github_user(root) if host == "github" else _ado_user(root)
        if isinstance(me, Halt):
            return me
        if author.strip().lower() != me.strip().lower():
            mode = "contributor"
    if mode == "owner" and pr is None and branch == target:
        return Halt("on-base-branch", common.EXIT_LOGIC, f"on {target}; create a feature branch")
    return Context(root, host, host_name, branch, target, head, pr, pr_url, author, mode, pr_draft)


def add_context_lines(result, ctx: Context, *, pr_key: str = "PR") -> None:
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


def build_parser():
    parser = common.ResultParser(prog=SCRIPT, description="Detect the ship context.")
    parser.add_argument("--base", default=None, help="Target branch (default: origin HEAD)")
    common.add_output_format_arg(parser)
    return parser


def run(argv: list[str]) -> tuple[object, str, Path | None]:
    result = common.Result(SCRIPT, REASONS)
    try:
        args = build_parser().parse_args(argv)
    except common.UsageError as exc:
        return result.stop("bad-arguments", common.EXIT_CONFIG, exc), common.peek_format(argv), None
    fmt = common.resolve_format(args.output_format)
    if args.base is not None and not common.safe_ref(args.base):
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
