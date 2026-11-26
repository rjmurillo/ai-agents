#!/usr/bin/env python3
"""Title, body, and paths-in-diff checks for ship_pr.py (ADR-127).

``ship_pr.py check`` and ``publish`` call ``run_checks``. Each check adds one
``CHECK: <name>=<state>`` line. A check that could not run is reported as
``<name>:not-run`` and is never a pass.

The paths-in-diff check never runs code from the branch being shipped
(owner ruling, 2026-11-25, on security finding 1 of the ship review: the
rejected alternative ran the checkout copy through uv). It reads the
validator and its import closure from the base branch with
``git show origin/<base>:<path>``, writes them to a private temporary tree
(directory 0700, files 0600), and runs that copy under this interpreter with
``-I``. The body file and the branch diff are its data; git reads the diff
from the checkout. ``uv`` is not used, so the branch's lockfile builds nothing.

Accepted trade-off: a PR that changes the validator itself is checked by the
base version until it merges.

When the base has no validator, or the base copy cannot run (exit 2 or a
crash), the check reports ``paths=NOT-RUN``. That is never a pass.

vendor-portability: declared. The validator path names the consumer
repository's own ``scripts/validation/pr_description.py`` on its base branch.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import _ship_common as common
    from ship_detect import Context
else:
    _HERE = Path(__file__).resolve(strict=True).parent  # the real entry, never a symlink's dir
    if "_ship_common" not in sys.modules:  # pragma: no cover - fresh interpreter only
        _s = importlib.util.spec_from_file_location("_ship_common", _HERE / "_ship_common.py")
        _s.loader.exec_module(
            sys.modules.setdefault("_ship_common", importlib.util.module_from_spec(_s))
        )
    common = sys.modules["_ship_common"]

BODY_MARKER = "<!-- replace with PR body -->"
BASE_VALIDATOR = "scripts/validation/pr_description.py"
# The validator imports scripts.github_core from its own tree, so the base
# copy needs the base copy of that package beside it.
BASE_CLOSURE_FILES = ("scripts/__init__.py",)
BASE_CLOSURE_DIRS = ("scripts/github_core",)
VALIDATOR_TIMEOUT_SECONDS = 300
# The same rule as validate_pr_description.py's _CONVENTIONAL_COMMIT_PATTERN;
# test_ship_review_findings.py fails if the two drift apart.
_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|chore|ci|build|revert)"
    r"(\(.+\))?!?: .+"
)
# Built with chr() so a formatter cannot turn escapes into the banned bytes.
_DASHES = (chr(0x2013), chr(0x2014))
_TITLE_FORBIDDEN = ('"', "$", "`")


def _validate_description() -> Path:
    return common.skill_script("github", "pr", "validate_pr_description.py")


def title_problem(title: str) -> str | None:
    if not title.strip() or title != title.strip():
        return "title is empty or padded"
    if title.startswith(("@", "-")):
        return "title must not start with @ or -"
    if any(dash in title for dash in _DASHES):
        return "title has an em or en dash"
    if any(char in title for char in _TITLE_FORBIDDEN):
        return "title has a quote, dollar sign, or backtick"
    if common.CONTROL_RE.search(title):
        return "title has a control character"
    if not _CONVENTIONAL_RE.match(title):
        return "title is not a conventional commit"
    return None


def body_problem(text: str) -> str | None:
    if BODY_MARKER in text:
        return "body still holds the replace-with-PR-body marker"
    if any(dash in text for dash in _DASHES):
        return "body has an em or en dash"
    # The same rule as pr_validations.validate_no_escaped_newlines: a body made
    # of literal backslash-n sequences, with no real line break.
    if "\\n" in text and "\n" not in text.strip():
        return "body has an escaped newline"
    if not text.strip():
        return "body is empty"
    return None


def _not_run(result: common.Result, reason: str) -> None:
    result.add("CHECK", f"paths=NOT-RUN {reason}; compare the body to the diff by hand")


def _base_files(ctx: Context, ref: str) -> list[str] | None:
    """Repository paths to copy from ``ref``, or None when it has no validator."""
    if common.git(["cat-file", "-e", f"{ref}:{BASE_VALIDATOR}"], cwd=ctx.root).returncode != 0:
        return None
    files = [BASE_VALIDATOR]
    files += [
        f
        for f in BASE_CLOSURE_FILES
        if common.git(["cat-file", "-e", f"{ref}:{f}"], cwd=ctx.root).returncode == 0
    ]
    for directory in BASE_CLOSURE_DIRS:
        listing = common.git(["ls-tree", "-r", "--name-only", ref, "--", directory], cwd=ctx.root)
        files += [line for line in listing.stdout.splitlines() if line.endswith(".py")]
    return files


def _write_private_tree(ctx: Context, ref: str, files: list[str], tree: Path) -> str | None:
    """Copy each base file into ``tree`` with owner-only modes; the failure cause, or None."""
    for rel in files:
        parts = Path(rel).parts
        if not parts or parts[0] != "scripts" or ".." in parts or Path(rel).is_absolute():
            return f"{rel}: path outside scripts/"
        shown = common.git(["show", f"{ref}:{rel}"], cwd=ctx.root)
        if shown.returncode != 0:
            return f"{rel}: " + common.cause_line(shown.stderr, f"git show exit {shown.returncode}")
        target = tree.joinpath(*parts)
        try:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            with os.fdopen(os.open(target, flags, 0o600), "w", encoding="utf-8") as handle:
                handle.write(shown.stdout)
        except OSError as exc:
            return f"{rel}: {exc.strerror or exc}"
    return None


def _check_paths(ctx: Context, body_file: Path, base: str, result: common.Result) -> bool | None:
    """Run the base branch's paths-in-diff validator from a private copy.

    Returns True on a pass, False on a failure, and None when it could not run.
    A None is not a pass: the model must compare the paths by hand.
    """
    # The full remote-tracking name: a tag named origin/<base> cannot shadow it.
    ref = f"refs/remotes/origin/{base}"
    shown = f"origin/{base}"
    files = _base_files(ctx, ref)
    if files is None:
        _not_run(result, f"{shown} has no path validator")
        return None
    with tempfile.TemporaryDirectory(prefix="ship-validator-") as directory:
        tree = Path(directory)
        failure = _write_private_tree(ctx, ref, files, tree)
        if failure:
            _not_run(result, f"could not copy the validator from {shown} ({failure})")
            return None
        done = common.run(
            [
                sys.executable,
                "-I",
                str(tree / BASE_VALIDATOR),
                "--body-file",
                str(body_file),
                "--base",
                ref,
            ],
            cwd=ctx.root,
            timeout=VALIDATOR_TIMEOUT_SECONDS,
        )
    if done.returncode == 0:
        result.add("CHECK", "paths=PASS")
        return True
    if done.returncode != 1 or "Traceback (most recent call last)" in done.stderr:
        cause = common.cause_line(done.stderr, f"exit {done.returncode}")
        _not_run(result, f"the {shown} validator could not run (exit {done.returncode}): {cause}")
        return None
    result.add("CHECK", f"paths=FAIL exit={done.returncode}")
    for finding in critical_findings(done.stdout)[:10]:
        result.add("FINDING", finding)
    return False


def critical_findings(output: str) -> list[str]:
    """``<issue>: <file>`` for each ``[CRITICAL]`` block the validator printed."""
    findings: list[str] = []
    issue = None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("[CRITICAL]"):
            issue = stripped[len("[CRITICAL]") :].strip() or "critical"
        elif issue and stripped.startswith("File:"):
            findings.append(f"{issue}: {stripped[len('File:') :].strip()}")
            issue = None
    return findings or [
        line for line in output.splitlines() if line.strip().startswith("[CRITICAL]")
    ]


def _check_ado_description(
    ctx: Context, title: str, body_file: Path, result: common.Result
) -> bool:
    """Run the offline Azure DevOps description validator; return False on a failure."""
    helper = _validate_description()
    if not helper.is_file():
        result.add("CHECK", "description=FAIL validate_pr_description.py not found")
        return False
    done = common.run(
        [sys.executable, "-I", str(helper), "--title", title, "--body-file", str(body_file)],
        cwd=ctx.root,
    )
    problem = description_problem(done.returncode, done.stdout, done.stderr)
    if problem:
        result.add("CHECK", f"description=FAIL {problem}")
        return False
    result.add("CHECK", "description=PASS")
    return True


def description_problem(returncode: int, stdout: str, stderr: str = "") -> str | None:
    """Read validate_pr_description.py's JSON report; None when it holds no error.

    Without --fail-on-violation the helper exits 0 even on an error, so the
    report's ErrorCount decides, not the exit code. A nonzero exit carries the
    helper's last stderr line.
    """
    if returncode != 0:
        cause = common.cause_line(stderr, "")
        return f"exit={returncode}" + (f": {cause}" if cause else "")
    start = stdout.find("{")
    report = common.parse_json(stdout[start:]) if start >= 0 else None
    if not isinstance(report, dict) or not isinstance(report.get("ErrorCount"), int):
        return "the validator report did not parse"
    if report["ErrorCount"] == 0:
        return None
    raw_validations = report.get("Validations")
    validations = raw_validations if isinstance(raw_validations, dict) else {}
    for name, item in validations.items():
        if isinstance(item, dict) and item.get("Status") == "FAIL":
            return f"{name}: {item.get('Message', '')}".strip()
    return f"errors={report['ErrorCount']}"


def _report(result: common.Result, name: str, problem: str | None) -> bool:
    result.add("CHECK", f"{name}={'FAIL ' + problem if problem else 'PASS'}")
    return problem is None


def run_checks(
    ctx: Context, title: str, body_file: Path, base: str, result: common.Result
) -> list[str]:
    """Run every body and title check; add CHECK lines; return failed check names.

    A check that could not run is reported as ``<name>:not-run``.
    """
    text = body_file.read_text(encoding="utf-8", errors="replace")
    outcomes: list[tuple[str, bool | None]] = [
        ("title", _report(result, "title", title_problem(title))),
        ("body", _report(result, "body", body_problem(text))),
        ("paths", _check_paths(ctx, body_file, base, result)),
    ]
    # A title or body that failed its own check never reaches a helper's argv.
    if ctx.host == "ado" and all(ok for _name, ok in outcomes[:2]):
        outcomes.append(("description", _check_ado_description(ctx, title, body_file, result)))
    failed = [name for name, ok in outcomes if ok is False]
    return failed + [f"{name}:not-run" for name, ok in outcomes if ok is None]


def split_not_run(outcome: list[str]) -> tuple[list[str], bool]:
    """Separate real failures from the paths check that could not run."""
    failed = [name for name in outcome if not name.endswith(":not-run")]
    return failed, len(failed) != len(outcome)
