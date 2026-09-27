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


def _step_untrusted_input_signals(step: object) -> tuple[bool, bool]:
    """``(run_is_unsafe, env_is_safe)`` for one workflow step.

    ``run_is_unsafe`` is true when the step's ``run`` string names the
    untrusted expression directly. ``env_is_safe`` is true when the step's
    ``env`` mapping has a value naming it instead (the safe indirection).
    A non-mapping ``step`` (a malformed list entry) reports both false.
    """
    if not isinstance(step, dict):
        return False, False
    run = step.get("run")
    run_is_unsafe = isinstance(run, str) and UNTRUSTED_PR_TITLE_EXPRESSION in run
    env = step.get("env")
    env_is_safe = isinstance(env, dict) and any(
        isinstance(value, str) and UNTRUSTED_PR_TITLE_EXPRESSION in value for value in env.values()
    )
    return run_is_unsafe, env_is_safe


def workflow_avoids_untrusted_input_in_run(content: str) -> bool:
    """True when no step's ``run`` names the untrusted expression, and one does in ``env``.

    Parses with :func:`yaml.safe_load` rather than matching text, so the
    check does not depend on which YAML shape the model wrote: a single-line
    ``- run: ...`` (no separate ``name:``), a multi-line ``run: |`` block
    with the expression on a continuation line, and a quoted ``env:`` value
    are all read the same way parsing does. Any malformed or unexpected
    shape (invalid YAML, a document that is not a mapping, ``jobs`` that is
    not a mapping) fails closed: ``False``, never treated as "no steps to
    check." Per-step classification lives in
    :func:`_step_untrusted_input_signals`, keeping this function's own
    branching to the walk over jobs and steps.
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
    found_safe_env_reference = False
    for job in jobs.values():
        for step in _job_steps(job):
            run_is_unsafe, env_is_safe = _step_untrusted_input_signals(step)
            if run_is_unsafe:
                return False
            found_safe_env_reference = found_safe_env_reference or env_is_safe
    return found_safe_env_reference
