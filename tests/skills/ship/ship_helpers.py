"""Call helpers shared by the ship script tests."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "ship" / "scripts"


_ORDER = ("_ship_common", "ship_detect", "ship_preflight", "ship_pr")


def load_scripts():
    """Load the ship scripts from the source tree; return (common, detect, preflight, pr).

    A script not yet in the tree loads as None, so each slice's tests run alone.
    """
    loaded = []
    for name in _ORDER:
        path = SCRIPTS / f"{name}.py"
        if name not in sys.modules and path.is_file():
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        loaded.append(sys.modules.get(name))
    return tuple(loaded)


def invoke(module, argv: list[str], capsys) -> tuple[int, list[str]]:
    """Run ``module.main`` in human format; return the exit code and stdout lines."""
    code = module.main(
        [*argv, "--output-format", "human"] if "--output-format" not in argv else argv
    )
    lines = capsys.readouterr().out.splitlines()
    return code, lines


def values(lines: list[str], key: str) -> list[str]:
    prefix = f"{key}: "
    return [line[len(prefix) :] for line in lines if line.startswith(prefix)]


# Shared by test_ship_pr.py and test_ship_pr_publish.py.
GITHUB = "https://github.com/rjmurillo/ai-agents.git"
ADO = "https://dev.azure.com/contoso/p/_git/r"
TITLE = "feat(ship): add the driver"
PR_URL = "https://github.com/rjmurillo/ai-agents/pull/501"
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)


def assert_snapshot(published: Path, body: Path) -> None:
    """The host gets a private snapshot of the validated body, never the original path."""
    assert published != body.resolve()
    assert published.parent == body.resolve().parent
    assert published.name.startswith("pr-body-publish-")
    assert published.read_text(encoding="utf-8") == body.read_text(encoding="utf-8")
    assert oct(published.stat().st_mode & 0o777) == "0o600"


def run_pr(scripts, capsys, *argv):
    return invoke(scripts[3], list(argv), capsys)


def publish(scripts, capsys, body: Path, *extra: str):
    """Run ``ship_pr.py publish`` with the hand-checked paths flag and the test title."""
    return run_pr(
        scripts,
        capsys,
        "publish",
        "--paths-checked-by-hand",
        "--title",
        TITLE,
        "--body-file",
        str(body),
        *extra,
    )


def fail_push(monkeypatch, common, stderr: str) -> None:
    """Make every ``git push`` fail with ``stderr``; other git calls run for real."""
    real_git = common.git

    def failing(args, cwd=None, timeout=60, **kw):
        if args[:1] == ["push"]:
            return common.Completed(128, "", stderr)
        return real_git(args, cwd=cwd, timeout=timeout, **kw)

    monkeypatch.setattr(common, "git", failing)


def ado_created(description: str = "## Summary") -> dict:
    return {
        "stdout": json.dumps(
            {
                "pullRequestId": 88,
                "description": description,
                "repository": {"webUrl": "https://dev.azure.com/c/p/_git/r"},
            }
        )
    }


def symlink_or_skip(link: Path, target: Path) -> None:
    """Create ``link`` pointing at ``target``, or skip where the platform lacks symlinks.

    Windows without Developer Mode raises ``OSError``; a platform with no symlink
    support raises ``NotImplementedError``. On POSIX any other ``OSError`` is a
    broken fixture and fails the test instead of skipping it.
    """
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except NotImplementedError as exc:
        pytest.skip(f"cannot create symbolic links here: {exc}")
    except OSError as exc:
        if os.name != "nt":
            raise
        pytest.skip(f"cannot create symbolic links here: {exc}")


# Fake base-branch validators for the paths-in-diff check.
VALIDATOR_PASS = """\
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts.github_core  # the base closure must be importable
probe = os.environ.get("SHIP_VALIDATOR_PROBE")
if probe:
    me = Path(__file__)
    Path(probe).write_text(json.dumps({
        "argv": sys.argv[1:],
        "isolated": sys.flags.isolated,
        "file_mode": oct(me.stat().st_mode & 0o777),
        "dir_mode": oct(me.parents[2].stat().st_mode & 0o777),
        "cwd": os.getcwd(),
        "file": str(me),
    }))
print("ok")
"""

VALIDATOR_CRITICAL = """\
print("  CRITICAL: 1")
print("[CRITICAL] File mentioned but not in diff")
print("  File: old.py")
print("  Description claims this file was changed, but it is not in the PR diff.")
raise SystemExit(1)
"""

VALIDATOR_BRANCH_EDIT = """\
import os
from pathlib import Path
Path(os.environ["SHIP_BRANCH_SENTINEL"]).write_text("branch validator ran")
print("CRITICAL: branch copy")
raise SystemExit(1)
"""


def approved_ado_build(fakes, merge: str) -> None:
    """Return an approved build for the supplied merge commit."""
    fakes.rule(
        "az",
        ["repos", "pr", "policy", "list"],
        {"stdout": json.dumps([{"status": "approved", "buildId": 5}])},
    )
    fakes.rule(
        "az",
        ["pipelines", "build", "show"],
        {"stdout": json.dumps({"result": "succeeded", "sourceVersion": merge})},
    )


def pending_github_pr(fakes, head: str, number: int = 9) -> None:
    """Fake an owned open GitHub PR at ``head`` whose required checks are still running."""
    pr = {
        "number": number,
        "state": "OPEN",
        "author": {"login": "me"},
        "url": "u",
        "baseRefName": "main",
    }
    fakes.rule("gh", ["pr", "view"], {"stdout": json.dumps(pr)})
    fakes.rule("gh", ["api", "user"], {"stdout": "me\n"})
    binding = {
        "headRefName": "feat/ship-change",
        "headRefOid": head,
        "url": f"https://github.com/o/r/pull/{number}",
    }
    fakes.rule("gh", ["pr", "view", str(number)], {"stdout": json.dumps(binding)})
    fakes.rule("get_pr_checks", [], {"rc": 7, "stdout": "{}\n"})
