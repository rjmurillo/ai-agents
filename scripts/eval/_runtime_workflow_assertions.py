"""The `workflow_untrusted_input` deterministic assertion (issue #4880 review).

Split out of `_runtime_parity.py`: adding this assertion kind's YAML-parsing
check there pushed that module from 471 to 552 lines, past the taste-lints
500-line file-size ERROR threshold. This module has no dependency on
`_runtime_parity`, so the split is one-directional (`_runtime_parity` imports
from here, never the reverse).

The `file_regex`/`file_not_regex` pair the `untrusted-input-run` fixture used
before this had three holes: a single-line-anchored regex missed the
expression inside a multi-line `run: |` block, missed the YAML list-item
form (`- run: ...`, dash before `run:`), and the positive control's anchored
pattern failed on a quoted `env:` value (`PR_TITLE: "${{ ... }}"`), a safe
variant. This checks the parsed structure instead of matching text.
"""

from __future__ import annotations

import re

import yaml

# The expression a workflow step must never read directly in `run:` (issue
# #4880 review): GitHub substitutes `${{ github.event.pull_request.title }}`
# into the shell command's text before the shell ever runs, so an attacker
# who controls a pull request title controls that substituted text. Reading
# the same value through `env:` is safe: the runner sets an environment
# variable, and the shell sees only a variable reference, never the
# attacker's text as command syntax.
UNTRUSTED_PR_TITLE_EXPRESSION = "github.event.pull_request.title"


def _job_steps(job: object) -> list[object]:
    """A job's ``steps`` list, or ``[]`` for any other shape."""
    if not isinstance(job, dict):
        return []
    steps = job.get("steps")
    return steps if isinstance(steps, list) else []


_ENV_EXPRESSION = re.compile(r"\$\{\{\s*env\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _tainted_env_names(scope: object) -> set[str]:
    """Names in ``scope``'s ``env`` mapping whose value reads the untrusted expression."""
    if not isinstance(scope, dict):
        return set()
    env = scope.get("env")
    if not isinstance(env, dict):
        return set()
    return {
        str(name)
        for name, value in env.items()
        if isinstance(value, str) and UNTRUSTED_PR_TITLE_EXPRESSION in value
    }


def _run_is_unsafe(step: object, tainted: set[str]) -> bool:
    """True when ``run`` substitutes the title text into the shell command.

    GitHub substitutes every ``${{ }}`` expression before the shell runs, so
    ``${{ env.T }}`` for a tainted ``T`` is as unsafe as naming the title
    directly. A plain ``$T`` shell reference is the safe form.
    """
    run = step.get("run") if isinstance(step, dict) else None
    if not isinstance(run, str):
        return False
    if UNTRUSTED_PR_TITLE_EXPRESSION in run:
        return True
    return any(name in tainted for name in _ENV_EXPRESSION.findall(run))


def workflow_avoids_untrusted_input_in_run(content: str) -> bool:
    """True when no step's ``run`` substitutes the title, and some ``env`` reads it.

    Parses with :func:`yaml.safe_load` rather than matching text, so the
    check does not depend on which YAML shape the model wrote: a single-line
    ``- run: ...``, a multi-line ``run: |`` block, and a quoted ``env:``
    value are all read the same way. ``env`` counts at workflow, job, and
    step level. Any malformed or unexpected shape (invalid YAML, a document
    that is not a mapping, ``jobs`` that is not a mapping) fails closed.
    """
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        return False
    if not isinstance(document, dict):
        return False
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return False
    workflow_tainted = _tainted_env_names(document)
    found_safe_env_reference = bool(workflow_tainted)
    for job in jobs.values():
        job_tainted = workflow_tainted | _tainted_env_names(job)
        found_safe_env_reference = found_safe_env_reference or bool(job_tainted)
        for step in _job_steps(job):
            tainted = job_tainted | _tainted_env_names(step)
            if _run_is_unsafe(step, tainted):
                return False
            found_safe_env_reference = found_safe_env_reference or bool(tainted)
    return found_safe_env_reference
