"""Run-completeness classification: complete, truncated, timeout (REQ-027 D1).

Split from ``scripts/metrics/gate_latency_sampler.py`` to keep that module
under the project's 300-line taste-lint warning ceiling, the same reason
``lefthook_summary.py``, ``gate_latency_io.py``, ``gate_latency_probe.py``,
``gate_latency_stats.py``, and ``gate_latency_classes.py`` are their own
modules (see each one's docstring). Pure classification: no subprocess, no
file I/O beyond reading an already-parsed lefthook config dict the caller
supplies (``build_report`` in ``gate_latency_sampler.py`` owns the actual
``_load_lefthook_config`` call, per DR4, reuse over duplication).

``build_report`` classifies every ``HookRun`` as ``"complete"``,
``"truncated"``, or ``"timeout"`` after all repetitions have been
collected, using two independent triggers (either firing is enough; see
``_classify_run_status`` for the full reasoning). The **relative** trigger
compares ``run.jobs_parsed`` against the report's own maximum, so it is
defined relative to the other repetitions in the same report, not from a
single run in isolation. **Limitation**: with exactly one repetition, that
maximum is trivially the one run's own ``jobs_parsed``, so the relative
trigger alone can never fire; a single-repetition report can still be
classified ``"truncated"`` through the **absolute** trigger below, but
never through the relative one. ``gate_latency_io.write_markdown`` states
this narrower limitation explicitly when ``repetitions == 1``.

D1 follow-up (epic #5456, measured against this repository's own real
pre-push hook): the relative trigger alone is blind to truncation that
happens identically on every repetition, which is the common case for a
``piped: true`` hook that aborts at the same failing job every run, because
the repetition that sets the max IS the truncated one. Measured with
``--hook pre-push --change-class markdown --repetitions 2``: both
repetitions aborted at job 6 of 26 and both parsed exactly 6 jobs, so the
relative check alone classified both ``"complete"`` and the report's
``__hook__`` summary read a worst-observed figure of 1.543s for a hook the
committed baseline separately measured at 126.16s. The **absolute**
trigger closes this gap: lefthook's own ``piped: true`` semantics (declared
on this repository's ``pre-push`` hook) mean a non-zero hook exit IS a
skipped remainder, because piped jobs run in sequence and a failure stops
the rest. See ``_classify_run_status`` for the trigger definition and the
deliberate conservative false positive it accepts.
"""

from __future__ import annotations

from typing import Any

from scripts.metrics.gate_latency_models import HookRun

# Recorded in place of a real exit code when the hook is killed on timeout
# (see ``gate_latency_sampler._run_repetition``, which owns the subprocess
# call and imports this constant rather than keeping a second copy).
_TIMEOUT_EXIT_CODE = -1


def _classify_run_status(run: HookRun, max_jobs_parsed: int, piped: bool | None = None) -> str:
    """Classify one repetition as ``"complete"``, ``"truncated"``, or ``"timeout"``.

    ``exit_code == _TIMEOUT_EXIT_CODE`` always reads as ``"timeout"`` and
    wins over both truncation triggers below. Otherwise, EITHER of two
    independent triggers is enough to classify ``"truncated"``:

    - **Relative** (the original D1 fix): ``run.jobs_parsed < max_jobs_parsed``,
      where ``max_jobs_parsed`` is the largest job count seen across every
      repetition in the same report (computed by the caller,
      ``build_report``, after all repetitions are collected). Catches
      truncation that VARIES between repetitions. Blind to truncation that
      happens IDENTICALLY on every repetition, because the repetition that
      sets the max is itself the truncated one; with a single repetition
      ``max_jobs_parsed`` is trivially that run's own count, so this
      trigger alone can never fire (see this module's docstring for the
      measured failure this produced against a real pre-push hook).
    - **Absolute** (D1 follow-up, epic #5456): ``piped is True and
      run.exit_code != 0``. Lefthook's own ``piped: true`` semantics mean a
      non-zero hook exit IS a skipped remainder: piped jobs run in
      sequence and a failure stops the rest. This trigger has no n=1 blind
      spot, because it needs no other repetition to compare against.
      ``piped=None`` (the default, and what the caller passes when
      ``lefthook.yml`` could not be read, the hook was missing, or the
      hook declared no ``piped`` key) disables this trigger entirely, so
      classification falls back to the relative trigger alone.

    A non-zero exit from a legitimately failed gate on a NON-piped hook (or
    a piped hook whose config could not be confirmed) is still
    ``"complete"``: the hook ran every job it was going to run, so it
    measured the hook. This is the distinction the defect brief draws
    between a run that FAILED a gate and a run that was CUT SHORT.

    Stricter than that distinction on purpose for a piped hook: a piped
    hook whose LAST job fails ran every job and did measure the whole hook,
    and the absolute trigger still classifies it ``"truncated"``. That is a
    deliberate conservative false positive. This instrument's job is to
    never report a figure that did not measure a full run; excluding one
    valid sample costs nothing but a slightly smaller n, while including
    one invalid sample reproduces D1. Erring toward exclusion is the
    correct direction here.
    """
    if run.exit_code == _TIMEOUT_EXIT_CODE:
        return "timeout"
    absolute_truncation = piped is True and run.exit_code != 0
    relative_truncation = run.jobs_parsed < max_jobs_parsed
    if absolute_truncation or relative_truncation:
        return "truncated"
    return "complete"


def _count_by_status(runs: list[HookRun]) -> dict[str, int]:
    """How many repetitions landed in each ``HookRun.status`` (auditability, D1 fix)."""
    counts: dict[str, int] = {}
    for run in runs:
        counts[run.status] = counts.get(run.status, 0) + 1
    return counts


def _resolve_piped_flag(
    config: dict[str, Any] | None, hook: str, exclusions: list[dict[str, str]]
) -> bool | None:
    """The measured hook's ``piped:`` flag, feeding the absolute truncation trigger.

    ``None`` (config unreadable, hook missing from it, or no ``piped`` key
    on the hook) is not an error: it disables the absolute trigger in
    ``_classify_run_status`` and classification falls back to the relative
    trigger alone. Either way this records why in ``exclusions`` (the same
    mechanism ``build_report`` already uses for
    ``declared_budget_seconds``), so the markdown can say which trigger
    applied to a given capture rather than silently assuming either
    direction.
    """
    if config is None or hook not in config:
        exclusions.append(
            {
                "field": "piped",
                "reason": "lefthook.yml unreadable or missing this hook at report time; "
                "the absolute truncation check is disabled and classification falls "
                "back to the relative check alone",
            }
        )
        return None
    hook_cfg = config[hook]
    raw_piped = hook_cfg.get("piped") if isinstance(hook_cfg, dict) else None
    if isinstance(raw_piped, bool):
        return raw_piped
    exclusions.append(
        {
            "field": "piped",
            "reason": "lefthook.yml declares no 'piped' key for this hook; the absolute "
            "truncation check is disabled and classification falls back to the "
            "relative check alone",
        }
    )
    return None
