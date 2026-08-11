"""Shared import and helpers for the new_pr.py skill script tests.

``new_pr.py`` is a standalone script rather than a package module, so every
test module that touches it needs the same importlib dance. Extracted here
(issue #4764) so splitting the suite by responsibility does not mean copying
that dance, and its ``_completed`` helper, into each new file.

The script under test is the CANONICAL copy at
``.claude/skills/github/scripts/pr/new_pr.py``. The Copilot mirror under
``src/copilot-cli/`` is generated from it and is asserted to match by
``tests/test_push_pr_interpreter_floor.py``; tests of behavior belong on the
canonical side.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr"


def import_script(name: str) -> ModuleType:
    """Import ``<name>.py`` from the skill's script directory."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


new_pr = import_script("new_pr")

main = new_pr.main
build_parser = new_pr.build_parser
validate_conventional_commit = new_pr.validate_conventional_commit
get_repo_root = new_pr.get_repo_root
run_validations = new_pr.run_validations
write_audit_log = new_pr.write_audit_log
validate_no_escaped_newlines = new_pr.validate_no_escaped_newlines
_resolve_validation_base = new_pr._resolve_validation_base
_UNTRUSTED_REPOSITORY_VALIDATORS = new_pr._UNTRUSTED_REPOSITORY_VALIDATORS

PASS_SUMMARY = "Trusted pre-creation validations passed."
WARNING_SUMMARY = "Trusted pre-creation validations completed with warnings."


def completed(
    stdout: str = "",
    stderr: str = "",
    rc: int = 0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def subprocess_dispatcher(responses, *, default=None):
    """Return a ``subprocess.run`` fake that dispatches on the argument vector.

    ``.claude/rules/testing.md`` SHOULD 11 requires this shape. A positional
    ``side_effect`` list encodes an unstated assumption about call order, and
    when a branch skips a call every later entry is consumed by the wrong
    command while the test keeps passing. That measurably broke three lists in
    this suite when ``main()`` gained a guarded ``git branch`` call.

    ``responses`` maps a matcher callable over the argv list to the
    CompletedProcess to return. The first match wins. An unmatched command
    raises a named AssertionError rather than a StopIteration from an
    exhausted list, so the failure says which command was unstubbed.
    """

    def run(cmd, **_kwargs) -> subprocess.CompletedProcess[str]:
        argv = [str(part) for part in cmd]
        for matches, response in responses:
            if matches(argv):
                return response
        if default is not None:
            return default
        raise AssertionError(f"unstubbed subprocess call: {argv}")

    return run


def git_diff_matcher(argv: list[str]) -> bool:
    return argv[:3] == ["git", "diff", "--name-only"]


def validator_matcher(argv: list[str]) -> bool:
    return any(part.endswith("validate_pr_description.py") for part in argv)
