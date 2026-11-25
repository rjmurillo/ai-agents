#!/usr/bin/env python3
"""Title, body, and paths-in-diff checks for ship_pr.py (ADR-127).

``ship_pr.py check`` and ``publish`` call ``run_checks``. Each check adds one
``CHECK: <name>=<state>`` line. A check that could not run is reported as
``<name>:not-run`` and is never a pass.

vendor-portability: declared. ``_check_paths`` runs the repository's own
``scripts/validation/pr_description.py`` when the consumer checkout has it,
and reports ``paths=NOT-RUN`` otherwise.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
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

BODY_MARKER = "<!-- replace with PR body -->"
LOCAL_PATH_CHECK = Path("scripts") / "validation" / "pr_description.py"
_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9][a-z0-9._/-]*\))?!?: \S.{0,198}$"
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
    # A title or body that failed its own check never reaches a helper's argv.
    if ctx.host == "ado" and all(ok for _name, ok in outcomes[:2]):
        outcomes.append(("description", _check_ado_description(ctx, title, body_file, result)))
    failed = [name for name, ok in outcomes if ok is False]
    return failed + [f"{name}:not-run" for name, ok in outcomes if ok is None]


def split_not_run(outcome: list[str]) -> tuple[list[str], bool]:
    """Separate real failures from the paths check that could not run."""
    failed = [name for name in outcome if not name.endswith(":not-run")]
    return failed, len(failed) != len(outcome)
