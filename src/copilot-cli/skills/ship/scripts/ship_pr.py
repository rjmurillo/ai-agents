#!/usr/bin/env python3
"""Create the feature branch, prepare and check the PR body, push, and open the PR.

Phases 3 and 4 of the ship driver (ADR-127). Owns every step the retired
``push-pr`` skill held after the model writes the body. Subcommands:

  branch  --name <type>/<slug>       create and switch to a feature branch
  prepare [--base B]                 allocate the scratch body file
  check   --title T --body-file F    title, body, paths-in-diff, ADO rules
  publish --title T --body-file F    push, then create the PR (or reuse one)

``publish`` refuses contributor mode, a dirty tree, an unreviewed HEAD
(unless ``--draft``), and any failed ``check``. It never creates a commit and
never force-pushes: a rejected push is ``STOP: push-rejected`` for a human.
On Azure DevOps it passes only ``--title``, ``--description @<checked file>``,
``--target-branch``, ``--draft``, and ``--output json``, and stops when the
returned description is still the ``@path`` text.

vendor-portability: declared. ``check`` runs the repository's own
``scripts/validation/pr_description.py`` when the consumer checkout has it,
and reports ``paths=NOT-RUN`` otherwise.

Exit codes (ADR-035): 0 NEXT, 1 logic STOP, 2 config STOP, 3 external STOP,
4 auth STOP.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import sys
import uuid
from pathlib import Path


def _load(
    name: str,
):  # pragma: no cover - runs only in a fresh interpreter; see test_ship_edges.py::test_script_runs_under_isolated_mode
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


common = _load("_ship_common")
detect_mod = _load("ship_detect")
preflight_mod = _load("ship_preflight")

SCRIPT = "ship_pr.py"
_IS_WINDOWS = os.name == "nt"
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
        "pr-create-failed",
        "description-upload-failed",
        "paths-not-checked",
    }
)
BODY_MARKER = "<!-- replace with PR body -->"
LOCAL_PATH_CHECK = Path("scripts") / "validation" / "pr_description.py"
PUSH_TIMEOUT_SECONDS = 3600
_BRANCH_RE = re.compile(
    r"^(feat|fix|docs|refactor|test|chore|ci|build|perf|style|revert)/[a-z0-9][a-z0-9-]{1,60}$"
)
_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9][a-z0-9._/-]*\))?!?: \S.{0,198}$"
)
# Built with chr() so a formatter cannot turn escapes into the banned bytes.
_DASHES = (chr(0x2013), chr(0x2014))
_TITLE_FORBIDDEN = ('"', "$", "`")
_GITHUB_PR_URL_RE = re.compile(r"https://[^\s/]+/[^\s/]+/[^\s/]+/pull/(\d+)")
_REJECTED_SIGNALS = ("[rejected]", "non-fast-forward", "fetch first", "updates were rejected")
_PUSH_AUTH_SIGNALS = (
    "authentication failed",
    "permission denied",
    "could not read username",
    "403",
)


def _new_pr() -> Path:
    return common.skill_script("github", "pr", "new_pr.py")


def _validate_description() -> Path:
    return common.skill_script("github", "pr", "validate_pr_description.py")


def cmd_branch(args, result, root: Path):
    if not _BRANCH_RE.match(args.name):
        return result.stop("bad-branch-name", common.EXIT_LOGIC, "use <type>/<3-5-word-slug>")
    done = common.git(["switch", "-c", args.name], cwd=root)
    if done.returncode != 0:
        return result.stop("branch-create-failed", common.EXIT_LOGIC, done.stderr.strip()[:200])
    result.add("BRANCH", args.name)
    return result.next("commit-then-review")


def _windows_body_file(root: Path) -> Path:
    directory = root / common.SCRATCH_REL
    directory.mkdir(parents=True, exist_ok=True)
    template = root / ".github" / "PULL_REQUEST_TEMPLATE.md"
    seed = BODY_MARKER + "\n"
    if template.is_file():
        seed += template.read_text(encoding="utf-8", errors="replace")
    path = directory / f"pr-body-{uuid.uuid4()}.md"
    path.write_text(seed, encoding="utf-8")
    return path


def cmd_prepare(args, result, root: Path):
    if _IS_WINDOWS:
        path = _windows_body_file(root)
        result.add("BODY_FILE", path.relative_to(root).as_posix())
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
        return result.stop("prepare-failed", common.EXIT_CONFIG, done.stderr.strip()[-200:])
    result.add("BODY_FILE", path_text[0])
    return result.next("write-body")


def title_problem(title: str) -> str | None:
    if not title.strip() or title != title.strip():
        return "title is empty or padded"
    if title.startswith(("@", "-")):
        return "title must not start with @ or -"
    if any(dash in title for dash in _DASHES):
        return "title has an em or en dash"
    if any(char in title for char in _TITLE_FORBIDDEN):
        return "title has a quote, dollar sign, or backtick"
    if not _CONVENTIONAL_RE.match(title):
        return "title is not a conventional commit"
    return None


def body_problem(text: str) -> str | None:
    if BODY_MARKER in text:
        return "body still holds the replace-with-PR-body marker"
    if any(dash in text for dash in _DASHES):
        return "body has an em or en dash"
    if "\\n" in text:
        return "body has an escaped newline"
    if not text.strip():
        return "body is empty"
    return None


def _check_paths(ctx, body_file: Path, base: str, result) -> bool | None:
    """Run the checkout's paths-in-diff validator when present.

    Returns True on a pass, False on a failure, and None when it could not run.
    A None is not a pass: the model must compare the paths by hand.
    """
    local_check = ctx.root / LOCAL_PATH_CHECK
    uv = shutil.which("uv")
    if not (local_check.is_file() and uv):
        result.add(
            "CHECK", "paths=NOT-RUN no local path validator; compare the body to the diff by hand"
        )
        return None
    done = common.run(
        [
            uv,
            "run",
            "--frozen",
            "python",
            "-I",
            str(LOCAL_PATH_CHECK),
            "--body-file",
            str(body_file),
            "--base",
            f"origin/{base}",
        ],
        cwd=ctx.root,
        timeout=300,
    )
    if done.returncode == 0:
        result.add("CHECK", "paths=PASS")
        return True
    result.add("CHECK", f"paths=FAIL exit={done.returncode}")
    findings = [
        line for line in done.stdout.splitlines() if "not in diff" in line or "CRITICAL" in line
    ]
    for line in findings[:10]:
        result.add("FINDING", line)
    return False


def _check_ado_description(ctx, title: str, body_file: Path, result) -> bool:
    """Run the offline Azure DevOps description validator; return False on a failure."""
    helper = _validate_description()
    if not helper.is_file():
        result.add("CHECK", "description=FAIL validate_pr_description.py not found")
        return False
    done = common.run(
        [sys.executable, "-I", str(helper), "--title", title, "--body-file", str(body_file)],
        cwd=ctx.root,
    )
    if done.returncode != 0 or re.search(r"(?m)^\s*Errors\b", done.stdout):
        result.add("CHECK", f"description=FAIL exit={done.returncode}")
        return False
    result.add("CHECK", "description=PASS")
    return True


def _report(result, name: str, problem: str | None) -> bool:
    result.add("CHECK", f"{name}={'FAIL ' + problem if problem else 'PASS'}")
    return problem is None


def run_checks(ctx, title: str, body_file: Path, base: str, result) -> list[str]:
    """Run every body and title check; add CHECK lines; return failed check names.

    A check that could not run is reported as ``<name>:not-run``.
    """
    text = body_file.read_text(encoding="utf-8", errors="replace")
    outcomes: list[tuple[str, bool | None]] = [
        ("title", _report(result, "title", title_problem(title))),
        ("body", _report(result, "body", body_problem(text))),
        ("paths", _check_paths(ctx, body_file, base, result)),
    ]
    if ctx.host == "ado":
        outcomes.append(("description", _check_ado_description(ctx, title, body_file, result)))
    failed = [name for name, ok in outcomes if ok is False]
    return failed + [f"{name}:not-run" for name, ok in outcomes if ok is None]


def _split(outcome: list[str]) -> tuple[list[str], bool]:
    """Separate real failures from the paths check that could not run."""
    failed = [name for name in outcome if not name.endswith(":not-run")]
    return failed, len(failed) != len(outcome)


def _detect(args, result):
    ctx = detect_mod.detect(base=args.base)
    if isinstance(ctx, detect_mod.Halt):
        result.stop(ctx.reason, ctx.code, ctx.detail)
        return None
    detect_mod.add_context_lines(result, ctx, pr_key="PR_AT_PREFLIGHT")
    return ctx


def _body_file(args, result, ctx) -> Path | None:
    body = common.confine_body_file(args.body_file, ctx.root)
    if body is None:
        result.stop(
            "bad-body-file",
            common.EXIT_CONFIG,
            "body file must be a regular file in the scratch directory",
        )
    return body


def cmd_check(args, result, _root: Path):
    ctx = _detect(args, result)
    if ctx is None:
        return result
    body = _body_file(args, result, ctx)
    if body is None:
        return result
    failed, paths_not_run = _split(run_checks(ctx, args.title, body, ctx.base, result))
    if failed:
        return result.stop("check-failed", common.EXIT_LOGIC, ",".join(failed))
    return result.next("compare-paths-by-hand" if paths_not_run else "publish")


def _push(ctx, result):
    refspec = f"refs/heads/{ctx.branch}:refs/heads/{ctx.branch}"
    done = common.git(
        ["push", "--set-upstream", "origin", refspec], cwd=ctx.root, timeout=PUSH_TIMEOUT_SECONDS
    )
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
    else:
        last = done.stderr.strip().splitlines()[-1:] or [f"exit {done.returncode}"]
        result.stop("push-failed", common.EXIT_EXTERNAL, last[0])
    return False


def _create_github(ctx, args, body: Path, result):
    helper = _new_pr()
    if not helper.is_file():
        return result.stop("pr-create-failed", common.EXIT_CONFIG, "new_pr.py not found")
    argv = [sys.executable, "-I", str(helper), "--title", args.title, "--base", ctx.base]
    if _IS_WINDOWS:
        argv.extend(["--body", body.read_text(encoding="utf-8", errors="replace")])
    else:
        argv.extend(["--body-file", str(body)])
    if args.draft:
        argv.append("--draft")
    done = common.run(argv, cwd=ctx.root, timeout=180)
    match = _GITHUB_PR_URL_RE.search(done.stdout)
    if done.returncode != 0 or match is None:
        last = done.stderr.strip().splitlines()[-1:] or [f"exit {done.returncode}"]
        return result.stop("pr-create-failed", common.EXIT_EXTERNAL, last[0])
    result.add("PR", f"host=github number={match.group(1)} url={match.group(0)}")
    return result.next("discharge")


def _create_ado(ctx, args, body: Path, result):
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
        halt = detect_mod._query_halt("pr-create-failed", done)
        return result.stop(halt.reason, halt.code, halt.detail)
    data = common.parse_json(done.stdout)
    if not isinstance(data, dict) or not isinstance(data.get("pullRequestId"), int):
        return result.stop("pr-create-failed", common.EXIT_EXTERNAL, "az returned no pullRequestId")
    pr_id = data["pullRequestId"]
    repository = data.get("repository") if isinstance(data.get("repository"), dict) else {}
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


def _review_gate(ctx, args, result) -> bool:
    """Refuse a dirty tree or an unreviewed HEAD; return False after a STOP."""
    tree = preflight_mod.check_tree(ctx.root)
    if isinstance(tree, preflight_mod.Halt):
        result.stop(tree.reason, tree.code, tree.detail)
        return False
    if tree.failed:
        result.stop("tree-dirty", common.EXIT_LOGIC, tree.detail)
        return False
    reviewed = preflight_mod.check_reviewed(ctx, args.draft, args.require_axis)
    if isinstance(reviewed, preflight_mod.Halt):
        result.stop(reviewed.reason, reviewed.code, reviewed.detail)
        return False
    result.add("CHECK", f"reviewed={reviewed.state} {reviewed.detail}".rstrip())
    if reviewed.state not in ("PASS", "SKIPPED"):
        result.stop("head-not-reviewed", common.EXIT_LOGIC, reviewed.detail)
        return False
    return True


def _checked_snapshot(ctx, args, body: Path, result) -> Path | None:
    """Snapshot the body once, check the snapshot, and return it; None after a STOP.

    The host gets the snapshot, never the original path, so the bytes that
    passed the checks are the bytes that publish.
    """
    snapshot = common.write_private(
        ctx.root, "pr-body-publish", ".md", body.read_text(encoding="utf-8", errors="replace")
    )
    if snapshot is None:
        result.stop("bad-body-file", common.EXIT_CONFIG, "could not write the body snapshot")
        return None
    failed, paths_not_run = _split(run_checks(ctx, args.title, snapshot, ctx.base, result))
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


def cmd_publish(args, result, _root: Path):
    ctx = _detect(args, result)
    if ctx is None:
        return result
    if ctx.mode == "contributor":
        return result.stop(
            "contributor-mode", common.EXIT_LOGIC, "the open PR belongs to another author"
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


def build_parser():
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
        if name == "publish":
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


def run(argv: list[str]):
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
    for axis in getattr(args, "require_axis", []):
        if not re.match(r"^[a-z][a-z0-9-]*$", axis):
            return (
                result.stop(
                    "bad-arguments",
                    common.EXIT_CONFIG,
                    "--require-axis must be a lowercase axis name",
                ),
                fmt,
                None,
            )
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
