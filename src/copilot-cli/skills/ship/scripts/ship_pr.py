#!/usr/bin/env python3
"""Create the feature branch, prepare and check the PR body, push, and open the PR.

Phases 3 and 4 of the ship driver (ADR-127). Owns every step the ``push-pr``
skill holds after the model writes the body; #7587 retires that skill. Subcommands:

  branch  --name <type>/<slug>       create and switch to a feature branch
  prepare [--base B]                 allocate the scratch body file
  check   --title T --body-file F    title, body, paths-in-diff, ADO rules
  publish --title T --body-file F    push, then create the PR (or reuse one)

``publish`` refuses contributor mode, a base branch, a dirty tree, an
unreviewed HEAD, and any failed ``check``. ``--draft`` skips the review
marker only for a new draft PR or an open PR the host reports as a draft. It never creates a commit and
never force-pushes: a rejected push is ``STOP: push-rejected`` for a human.
On Azure DevOps it passes only ``--title``, ``--description @<checked file>``,
``--target-branch``, ``--draft``, and ``--output json``, and stops when the
returned description is still the ``@path`` text.

Exit codes (ADR-035): 0 NEXT, 1 logic STOP, 2 config STOP, 3 external STOP,
4 auth STOP.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import _ship_common as common
    import ship_detect as detect_mod
    import ship_pr_checks as checks_mod
    import ship_preflight as preflight_mod
    from ship_detect import Context, Halt
    from ship_pr_checks import run_checks, split_not_run
else:
    _HERE = Path(__file__).resolve(strict=True).parent  # the real entry, never a symlink's dir
    if "_ship_common" not in sys.modules:  # pragma: no cover - fresh interpreter only
        _s = importlib.util.spec_from_file_location("_ship_common", _HERE / "_ship_common.py")
        _s.loader.exec_module(
            sys.modules.setdefault("_ship_common", importlib.util.module_from_spec(_s))
        )
    common = sys.modules["_ship_common"]
    detect_mod = common.load_sibling("ship_detect")
    preflight_mod = common.load_sibling("ship_preflight")
    checks_mod = common.load_sibling("ship_pr_checks")
    Halt = detect_mod.Halt
    # The title, body, and paths checks live in ship_pr_checks.py.
    run_checks = checks_mod.run_checks
    split_not_run = checks_mod.split_not_run

SCRIPT = "ship_pr.py"
REASONS = preflight_mod.REASONS | frozenset(
    {
        "bad-branch-name",
        "branch-create-failed",
        "prepare-failed",
        "bad-body-file",
        "contributor-mode",
        "tree-dirty",
        "head-not-reviewed",
        "push-rejected",
        "push-failed",
        "push-interrupted",
        "push-locked",
        "pr-create-failed",
        "description-upload-failed",
        "paths-not-checked",
    }
)
BODY_MARKER = checks_mod.BODY_MARKER
# The run budget caps the push, less the PR create's reserve. A timeout kills its hooks.
PUSH_TIMEOUT_SECONDS = 540
PR_RESERVE_SECONDS = 120
_EXTERNAL_RETURN_CODES = (124, 126, 127)  # timeout, cannot run, not found
_RERUN_NOTE = "rerun publish; it detects an existing PR"
_TIMEOUT_NOTE = "check the remote, then rerun publish"
_LOCK_BUSY = "another push of this branch holds the shared push lock; rerun publish after it ends"
_BRANCH_RE = re.compile(
    r"^(feat|fix|docs|refactor|test|chore|ci|build|perf|style|revert)/[a-z0-9][a-z0-9-]{1,60}$"
)
_GITHUB_PR_URL_RE = re.compile(r"https://[^\s/]+/[^\s/]+/[^\s/]+/pull/(\d+)")
_REJECTED_SIGNALS = ("[rejected]", "non-fast-forward", "fetch first", "updates were rejected")
_PUSH_AUTH_SIGNALS = (
    "authentication failed",
    "permission denied",
    "could not read username",
    "returned error: 403",
    "http 403",
)


def _new_pr() -> Path:
    return common.skill_script("github", "pr", "new_pr.py")


def cmd_branch(args: argparse.Namespace, result: common.Result, root: Path) -> common.Result:
    if not _BRANCH_RE.fullmatch(args.name):
        return result.stop("bad-branch-name", common.EXIT_LOGIC, "use <type>/<3-5-word-slug>")
    done = common.git(["switch", "-c", args.name], cwd=root)
    if done.returncode != 0:
        return result.stop("branch-create-failed", common.EXIT_LOGIC, done.stderr.strip()[:200])
    result.add("BRANCH", args.name)
    return result.next("commit-then-review")


# Prints the base-ref seed from prepare_pr_body (argv: helper, root, base ref or "").
# It runs as a child through common.run, so child_env, the run budget, and the
# exit-code mapping apply, as they do to new_pr.py off Windows.
_SEED_CHILD = (
    "import importlib.util as u, pathlib, sys\n"
    "sys.stdout.reconfigure(encoding='utf-8')\n"
    "s = u.spec_from_file_location('prepare_pr_body', sys.argv[1])\n"
    "m = u.module_from_spec(s)\n"
    "s.loader.exec_module(m)\n"
    "try:\n"
    "    sys.stdout.write(m._seed_content(pathlib.Path(sys.argv[2]), sys.argv[3] or None))\n"
    "except m.PreparePrBodyError as exc:\n"
    "    sys.exit(str(exc))\n"
)


def _base_ref(base: str | None) -> str:
    """``origin/<base>`` as new_pr.py builds it, or "" for the default base ref."""
    if not base:
        return ""
    return base if base.startswith("origin/") else f"origin/{base}"


def _windows_body_file(args: argparse.Namespace, result: common.Result, root: Path) -> Path | None:
    """Seed a body file through the guarded scratch writer; None after a STOP."""
    helper = common.skill_script("github", "pr", "prepare_pr_body.py")
    if not helper.is_file():
        result.stop("prepare-failed", common.EXIT_CONFIG, "prepare_pr_body.py not found")
        return None
    argv = [sys.executable, "-I", "-c", _SEED_CHILD, str(helper), str(root), _base_ref(args.base)]
    done = common.run(argv, cwd=root)
    if done.returncode != 0:
        external = done.returncode in _EXTERNAL_RETURN_CODES or "cannot run git" in done.stderr
        code = common.EXIT_EXTERNAL if external else common.EXIT_CONFIG
        result.stop("prepare-failed", code, common.cause_line(done.stderr, "seed failed"))
        return None
    path = common.write_private(root, "pr-body", ".md", done.stdout)
    if path is None:
        result.stop("prepare-failed", common.EXIT_CONFIG, "scratch directory is unsafe")
    return path


def cmd_prepare(args: argparse.Namespace, result: common.Result, root: Path) -> common.Result:
    if common.on_windows():
        # The seed child runs git, which CreateProcess may find in the checkout first.
        unsafe = detect_mod.unsafe_checkout(root)
        if unsafe is not None:
            return result.stop(unsafe.reason, unsafe.code, unsafe.detail)
        path = _windows_body_file(args, result, root)
        if path is None:
            return result
        result.add("BODY_FILE", path.relative_to(root.resolve()).as_posix())
        return result.next("write-body")
    helper = _new_pr()
    if not helper.is_file():
        return result.stop("prepare-failed", common.EXIT_CONFIG, "new_pr.py not found")
    argv = [sys.executable, "-I", str(helper), "--prepare-body-file"]
    if args.base:
        argv.extend(["--base", args.base])
    done = common.run(argv, cwd=root)
    path_text = done.stdout.strip().splitlines()[-1:] if done.stdout.strip() else []
    if done.returncode != 0 or not path_text:
        code = (
            common.EXIT_EXTERNAL
            if done.returncode in _EXTERNAL_RETURN_CODES
            else common.EXIT_CONFIG
        )
        return result.stop("prepare-failed", code, done.stderr.strip()[-200:])
    result.add("BODY_FILE", path_text[0])
    return result.next("write-body")


def _detect(args: argparse.Namespace, result: common.Result) -> Context | None:
    ctx = detect_mod.detect(base=args.base)
    if isinstance(ctx, Halt):
        result.stop(ctx.reason, ctx.code, ctx.detail)
        return None
    detect_mod.add_context_lines(result, ctx, pr_key="PR_AT_PREFLIGHT")
    return ctx


def _read_body(body: Path, result: common.Result) -> str | None:
    """Read a body file as strict UTF-8; None after ``STOP: bad-body-file``.

    A lossy decode would publish U+FFFD in place of the author's bytes.
    """
    try:
        return body.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        result.stop("bad-body-file", common.EXIT_CONFIG, "body file is not UTF-8")
        return None


def _body_file(args: argparse.Namespace, result: common.Result, ctx: Context) -> Path | None:
    body = common.confine_body_file(args.body_file, ctx.root)
    if body is None:
        result.stop(
            "bad-body-file",
            common.EXIT_CONFIG,
            "body file must be a regular file in the scratch directory",
        )
        return None
    return body if _read_body(body, result) is not None else None


def cmd_check(args: argparse.Namespace, result: common.Result, _root: Path) -> common.Result:
    ctx = _detect(args, result)
    if ctx is None:
        return result
    body = _body_file(args, result, ctx)
    if body is None:
        return result
    failed, paths_not_run = split_not_run(run_checks(ctx, args.title, body, result))
    if failed:
        return result.stop("check-failed", common.EXIT_LOGIC, ",".join(failed))
    return result.next("compare-paths-by-hand" if paths_not_run else "publish")


def _push(ctx: Context, result: common.Result) -> bool:
    """Push under the shared per-branch push lock, so the commit guard sees the push."""
    with common.push_lock(ctx.branch) as lock:
        if lock == "busy":
            result.stop("push-locked", common.EXIT_EXTERNAL, _LOCK_BUSY)
            return False
        result.add("PUSH_LOCK", lock)
        return _push_now(ctx, result)


def _push_now(ctx: Context, result: common.Result) -> bool:
    timeout = max(1, min(PUSH_TIMEOUT_SECONDS, common.remaining_seconds() - PR_RESERVE_SECONDS))
    ref = f"refs/heads/{ctx.branch}"
    push = ["push", "--set-upstream", "origin", f"{ref}:{ref}"]
    try:
        done = common.git(push, cwd=ctx.root, timeout=timeout, group=not common.on_windows())
    except (KeyboardInterrupt, SystemExit) as exc:  # run killed the push's process group
        cause = "interrupted" if isinstance(exc, KeyboardInterrupt) else f"signal exit {exc.code}"
        result.stop("push-interrupted", common.EXIT_EXTERNAL, f"{cause}; {_TIMEOUT_NOTE}")
        return False
    if done.returncode == 0:
        result.add("PUSH", "pushed")
        return True
    lowered = done.stderr.lower()
    if any(signal in lowered for signal in _REJECTED_SIGNALS):
        result.stop(
            "push-rejected",
            common.EXIT_LOGIC,
            "remote has commits the branch lacks; a force push is a human action",
        )
    elif any(signal in lowered for signal in _PUSH_AUTH_SIGNALS):
        result.stop("auth-failed", common.EXIT_AUTH, "push was not authorized")
    elif done.returncode == 124:
        cause = common.cause_line(done.stderr, "push timed out")
        result.stop("push-failed", common.EXIT_EXTERNAL, f"{cause}; {_TIMEOUT_NOTE}")
    else:
        cause = common.cause_line(done.stderr, f"exit {done.returncode}")
        result.stop("push-failed", common.EXIT_EXTERNAL, cause)
    return False


def _create_halt(done: common.Completed) -> Halt:
    """The halt for a failed PR create; a timeout says the PR may already exist."""
    halt = detect_mod.query_halt("pr-create-failed", done)
    if done.returncode != 124:
        return halt
    return Halt(halt.reason, halt.code, f"{halt.detail} ({_RERUN_NOTE})")


def _create_github(
    ctx: Context, args: argparse.Namespace, body: Path, result: common.Result
) -> common.Result:
    helper = _new_pr()
    if not helper.is_file():
        return result.stop("pr-create-failed", common.EXIT_CONFIG, "new_pr.py not found")
    argv = [sys.executable, "-I", str(helper), "--title", args.title, "--base", ctx.base]
    if common.on_windows():
        argv.extend(["--body", body.read_text(encoding="utf-8")])
    else:
        argv.extend(["--body-file", str(body)])
    if args.draft:
        argv.append("--draft")
    done = common.run(argv, cwd=ctx.root, timeout=180)
    # new_pr.py echoes the title before gh prints the new PR URL, so a title
    # holding a PR URL must not win: take the last URL printed.
    matches = list(_GITHUB_PR_URL_RE.finditer(done.stdout))
    match = matches[-1] if matches else None
    if done.returncode != 0 or match is None:
        halt = _create_halt(done)
        # new_pr.py exits 2 on its own config error. Any other code is gh's,
        # and gh uses 1 for an API error and 4 for an auth error.
        if done.returncode == 4 or halt.code == common.EXIT_AUTH:
            return result.stop("auth-failed", common.EXIT_AUTH, halt.detail)
        code = common.EXIT_CONFIG if done.returncode == 2 else halt.code
        return result.stop(halt.reason, code, halt.detail)
    result.add("PR", f"host=github number={match.group(1)} url={match.group(0)}")
    return result.next("discharge")


def _create_ado(
    ctx: Context, args: argparse.Namespace, body: Path, result: common.Result
) -> common.Result:
    argv = [
        "az",
        "repos",
        "pr",
        "create",
        "--output",
        "json",
        "--title",
        args.title,
        "--description",
        f"@{body}",
        "--target-branch",
        ctx.base,
        "--draft",
        "true" if args.draft else "false",
    ]
    done = common.run(argv, cwd=ctx.root, timeout=180)
    if done.returncode != 0:
        halt = _create_halt(done)
        return result.stop(halt.reason, halt.code, halt.detail)
    data = common.parse_json(done.stdout)
    if not isinstance(data, dict) or not isinstance(data.get("pullRequestId"), int):
        return result.stop("pr-create-failed", common.EXIT_EXTERNAL, "az returned no pullRequestId")
    pr_id = data["pullRequestId"]
    raw_repository = data.get("repository")
    repository = raw_repository if isinstance(raw_repository, dict) else {}
    web_url = str(repository.get("webUrl", ""))
    url = f"{web_url}/pullrequest/{pr_id}" if web_url else "unknown"
    result.add("PR", f"host=ado number={pr_id} url={url}")
    if str(data.get("description", "")).startswith("@"):
        return result.stop(
            "description-upload-failed",
            common.EXIT_EXTERNAL,
            f"PR {pr_id} is open with the file path as its description; ask the user",
        )
    return result.next("discharge")


def _review_gate(ctx: Context, args: argparse.Namespace, result: common.Result) -> bool:
    """Refuse a dirty tree or an unreviewed HEAD; return False after a STOP."""
    tree = preflight_mod.check_tree(ctx.root)
    if isinstance(tree, Halt):
        result.stop(tree.reason, tree.code, tree.detail)
        return False
    if tree.failed:
        result.stop("tree-dirty", common.EXIT_LOGIC, tree.detail)
        return False
    reviewed = preflight_mod.check_reviewed(ctx, args.draft, args.require_axis)
    if isinstance(reviewed, Halt):
        result.stop(reviewed.reason, reviewed.code, reviewed.detail)
        return False
    result.add("CHECK", f"reviewed={reviewed.state} {reviewed.detail}".rstrip())
    if reviewed.state not in ("PASS", "SKIPPED"):
        result.stop("head-not-reviewed", common.EXIT_LOGIC, reviewed.detail)
        return False
    return True


def _checked_snapshot(
    ctx: Context, args: argparse.Namespace, body: Path, result: common.Result
) -> Path | None:
    """Snapshot the body once, check the snapshot, and return it; None after a STOP.

    The host gets the snapshot, never the original path, so the bytes that
    passed the checks are the bytes that publish.
    """
    text = _read_body(body, result)
    if text is None:
        return None
    snapshot = common.write_private(ctx.root, "pr-body-publish", ".md", text)
    if snapshot is None:
        result.stop("bad-body-file", common.EXIT_CONFIG, "could not write the body snapshot")
        return None
    failed, paths_not_run = split_not_run(run_checks(ctx, args.title, snapshot, result))
    if failed:
        result.stop("check-failed", common.EXIT_LOGIC, ",".join(failed))
        return None
    if paths_not_run and not args.paths_checked_by_hand:
        result.stop(
            "paths-not-checked",
            common.EXIT_LOGIC,
            "compare the body paths to the diff, then pass --paths-checked-by-hand",
        )
        return None
    if paths_not_run:
        result.add("CHECK", "paths=CHECKED-BY-HAND")
    return snapshot


def cmd_publish(args: argparse.Namespace, result: common.Result, _root: Path) -> common.Result:
    ctx = _detect(args, result)
    if ctx is None:
        return result
    if ctx.mode == "contributor":
        return result.stop(
            "contributor-mode", common.EXIT_LOGIC, "the open PR belongs to another author"
        )
    origin_default = detect_mod.default_branch(ctx.root)
    if ctx.branch in detect_mod.protected_branches(ctx.base, origin_default):
        return result.stop(
            "on-base-branch",
            common.EXIT_LOGIC,
            f"{ctx.branch} is a base branch; create a feature branch",
        )
    body = _body_file(args, result, ctx)
    if body is None or not _review_gate(ctx, args, result):
        return result
    snapshot = _checked_snapshot(ctx, args, body, result)
    if snapshot is None or not _push(ctx, result):
        return result
    if ctx.pr is not None:
        result.add("PR", f"host={ctx.host} number={ctx.pr} url={ctx.pr_url or 'unknown'} existing")
        return result.next("discharge")
    if ctx.host == "github":
        return _create_github(ctx, args, snapshot, result)
    return _create_ado(ctx, args, snapshot, result)


def build_parser() -> common.ResultParser:
    parser = common.ResultParser(prog=SCRIPT, description="Branch, check, push, and open the PR.")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=common.ResultParser)
    branch = sub.add_parser("branch")
    branch.add_argument("--name", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--base", default=None)
    for name in ("check", "publish"):
        command = sub.add_parser(name)
        command.add_argument("--title", required=True)
        command.add_argument("--body-file", required=True)
        command.add_argument("--base", default=None)
        if name == "publish":
            command.add_argument("--draft", action="store_true")
            command.add_argument("--require-axis", action="append", default=[])
            command.add_argument(
                "--paths-checked-by-hand",
                action="store_true",
                help="The model compared the body paths to the diff after paths=NOT-RUN",
            )
    common.add_output_format_arg(parser)
    # A subcommand repeats the flag without a default, so a value given before
    # the subcommand is not overwritten by the subparser's own default.
    for command in (branch, prepare, sub.choices["check"], sub.choices["publish"]):
        command.add_argument(
            "--output-format", choices=common.OUTPUT_FORMATS, default=argparse.SUPPRESS
        )
    return parser


_COMMANDS = {
    "branch": cmd_branch,
    "prepare": cmd_prepare,
    "check": cmd_check,
    "publish": cmd_publish,
}


def run(argv: list[str]) -> tuple[common.Result, str, Path | None]:
    result = common.Result(SCRIPT, REASONS)
    try:
        args = build_parser().parse_args(argv)
    except common.UsageError as exc:
        return result.stop("bad-arguments", common.EXIT_CONFIG, exc), common.peek_format(argv), None
    fmt = common.resolve_format(args.output_format)
    base = getattr(args, "base", None)
    if base is not None and not common.safe_ref(base):
        return (
            result.stop("bad-arguments", common.EXIT_CONFIG, "--base is not a plain ref"),
            fmt,
            None,
        )
    if not all(preflight_mod.AXIS_RE.fullmatch(axis) for axis in getattr(args, "require_axis", [])):
        message = "--require-axis must be a lowercase axis name"
        return result.stop("bad-arguments", common.EXIT_CONFIG, message), fmt, None
    root = common.repo_root()
    if root is None:
        return result.stop("no-repo", common.EXIT_CONFIG, "not inside a git work tree"), fmt, None
    return _COMMANDS[args.command](args, result, root), fmt, root


def main(argv: list[str] | None = None) -> int:
    result, fmt, root = run(sys.argv[1:] if argv is None else argv)
    return common.emit(result, fmt, root)


if (
    __name__ == "__main__"
):  # pragma: no cover - runs only in a fresh interpreter; see test_ship_edges.py::test_script_runs_under_isolated_mode
    raise SystemExit(main())
