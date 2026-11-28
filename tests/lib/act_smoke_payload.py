"""Shared act log samples for the plugin-cli-smoke.yml payload allowance tests.

Imported by ``tests/validation/test_run_workflow_local_test_smoke_payload.py``
and ``tests/validation/test_run_workflow_local_test_smoke_payload_evidence.py``.
The log lines mirror what act prints for a synthetic pull_request payload that
has no base or head SHA.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.validation import run_workflow_local_test as w

REPO_ROOT = Path(__file__).resolve().parents[2]

_FILTER_JOB = "[Plugin CLI Smoke/Smoke path filter]"
_OTHER_WORKFLOW_JOB = "[Duplicate Code Detection/Python duplication ratchet]"
_DECIDE = "Decide whether the smoke must run"
_EVENT = "pull_request"
_SCRIPTS_STEP = "Checkout trusted scripts from the base commit"
_CHECKOUT_BY_JOB = {
    "[Plugin CLI Smoke/Smoke path filter]": "Checkout the path filter from the base commit",
    "[Plugin CLI Smoke/Trusted-context gate]": _SCRIPTS_STEP,
    "[Plugin CLI Smoke/Smoke (codex, ubuntu-latest)]": _SCRIPTS_STEP,
    "[Plugin CLI Smoke/Smoke (pi, ubuntu-latest)]": _SCRIPTS_STEP,
    "[Plugin CLI Smoke/Smoke (claude hook discovery, ubuntu)]": _SCRIPTS_STEP,
    "[Plugin CLI Smoke/CLI Smoke Result]": "Checkout reporter script from the base commit",
}


_SHA = "07136aad753f7ec340165b7c212d353fd65dd42f"
_UNKNOWN_SHA_FATAL = f"fatal: remote error: upload-pack: not our ref {_SHA}"
_MISSING_REF_FATAL = "fatal: couldn't find remote ref refs/heads/no-such-branch"


def _git_annotation(job: str) -> str:
    return f"      {job}   \u2757  ::error::The process '/usr/bin/git' failed with exit code 128\n"


def _decide_error(job: str) -> str:
    return (
        f"      {job}   | cli_smoke_paths.py: error: --base and --head are required "
        "for pull_request\n"
    )


def _checkout_failure(job: str, step: str, fatal: str | None = _UNKNOWN_SHA_FATAL) -> str:
    """Lines copied from a real pre-push act log, parameterized.

    The fatal line is what git prints for the unpushed ``github.sha`` the
    checkout falls back to. ``fatal=None`` leaves it out.
    """
    fatal_line = f"      {job}   | {fatal}\n" if fatal is not None else ""
    return (
        f"{fatal_line}"
        f"{_git_annotation(job)}"
        f"      {job}   ❌  Failure - Main {step} [28.261404279s]\n"
        f"      {job} exitcode '1': failure\n"
    )


def _decide_failure(job: str = _FILTER_JOB, step: str = _DECIDE) -> str:
    return (
        f"{_decide_error(job)}"
        f"      {job}   ❌  Failure - Main {step} [130.202547ms]\n"
        f"      {job} exitcode '2': failure\n"
    )


def _hint(text: str) -> str | None:
    return w._act_limitation_hint(text, _EVENT)


def _workflow() -> dict[str, Any]:
    path = REPO_ROOT / ".github" / "workflows" / "plugin-cli-smoke.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


_FILTER_CHECKOUT = _CHECKOUT_BY_JOB[_FILTER_JOB]
_UNEXPLAINED = _checkout_failure(_FILTER_JOB, _FILTER_CHECKOUT, fatal=None)
_FILTER_FATAL = f"      {_FILTER_JOB}   | {_UNKNOWN_SHA_FATAL}\n"
_GATE_JOB = "[Plugin CLI Smoke/Trusted-context gate]"
