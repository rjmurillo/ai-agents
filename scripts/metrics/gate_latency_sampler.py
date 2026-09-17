"""The measurement core: run one hook N times and fold the runs into a report.

Split from ``scripts/metrics/gate_latency.py`` so each module holds one
concern. That file is now the command-line surface (argument parsing, input
validation, exit codes); this one is the measurement (subprocess execution,
sample collection, report assembly) and knows nothing about argv.

The split answers a cohesion finding from this repository's own
``code-qualities-assessment`` axis, which scored the combined module 3.7
against a floor of 7: it was parsing arguments, running subprocesses, and
assembling a report in one place.

Per ci-scripts.md MUST-16, the hook runs whole: this module never invokes
lefthook with ``--job`` to time a job in isolation, because a standalone run
does not predict that job's cost inside a real hook.

Run-completeness classification (REQ-027 D1 fix and D1 follow-up, epic
#5456) lives in ``gate_latency_classify.py``, split out to keep this module
under the taste-lint warning ceiling once the D1 follow-up (the absolute,
piped-based truncation trigger) was added. ``build_report`` below calls
``_classify_run_status`` after every repetition is collected and
``_resolve_piped_flag`` on the already-loaded lefthook config; read that
module's docstring for the full reasoning behind both triggers.
"""

from __future__ import annotations

import dataclasses
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.ci.lefthook_budget_model import declared_budget
from scripts.metrics.gate_latency_classify import (
    _TIMEOUT_EXIT_CODE,
    _classify_run_status,
    _count_by_status,
    _resolve_piped_flag,
)
from scripts.metrics.gate_latency_models import GateLatencyReport, HookRun
from scripts.metrics.gate_latency_probe import (
    _git_rev_parse_head,
    _host_profile,
    _load_lefthook_config,
    _one_minute_load,
    _tree_digest,
)
from scripts.metrics.gate_latency_stats import (
    _build_summaries,
    _percentile_note,
    _smallest_scope_n,
)
from scripts.metrics.lefthook_summary import parse_summary

# A hung hook would otherwise hang the sampler with no diagnostic. Generous on
# purpose: it has to exceed the slowest legitimate hook, and lefthook's own
# per-job timeout: values already bound the individual jobs. A timeout is
# recorded as a failed repetition, never raised past the caller (AC-06).
_HOOK_TIMEOUT_SECONDS = 3600.0


_URL_USERINFO_RE = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<userinfo>[^/@\s]+)@")


def _redact_url_userinfo(text: str) -> str:
    """Strip credentials out of any ``scheme://user:pass@host`` in ``text``.

    A pre-push measurement needs ``--hook-arg <remote> <url>``, and these
    values are written verbatim into a committed artifact. A remote URL can
    carry a token (``https://x-access-token:TOKEN@github.com/...``), which is a
    discouraged but real pattern for service accounts, and a secret written
    into a committed artifact is in git history permanently. Redacting here
    costs nothing when the URL is credential-free, which is the normal case.
    """
    return _URL_USERINFO_RE.sub(r"\g<scheme><redacted>@", text)


def _as_text(raw: str | bytes) -> str:
    """TimeoutExpired.stdout is bytes even when the call asked for text."""
    return raw if isinstance(raw, str) else raw.decode("utf-8", "replace")


def _run_repetition(
    repo: Path,
    lefthook_cmd: list[str],
    hook: str,
    files: tuple[str, ...],
    repetition_index: int,
    stdin_ref_line: str | None = None,
    hook_args: tuple[str, ...] = (),
    force: bool = False,
) -> HookRun:
    """Run one whole-hook lefthook invocation and parse its summary (AC-01 to AC-03).

    A hook that fails (non-zero exit) is data, not a sampler error: the
    exit code is recorded and the caller runs the remaining repetitions
    regardless (AC-06).

    ``stdin_ref_line`` is the text git feeds a real pre-push hook on stdin
    (``<local ref> <local sha> <remote ref> <remote sha>``). Several
    pre-push jobs in this repository declare ``use_stdin: true``, and with
    empty stdin those jobs can take an early exit, which would understate
    their cost in exactly the figure this script exists to report. The
    caller supplies the line or it is absent; this module never synthesises
    one, because a fabricated ref line would measure a push that did not
    happen. It reaches the subprocess through ``input=``, never through the
    argument list, so it is not an injection surface on a call that already
    runs with ``shell=False``.
    """
    file_args: list[str] = []
    for rel in files:
        file_args += ["--file", rel]
    cmd = [
        *lefthook_cmd,
        "run",
        hook,
        *hook_args,
        "--no-tty",
        "--colors",
        "off",
        "--no-stage-fixed",
        *file_args,
    ]
    if force:
        cmd.append("--force")
    digest_before = _tree_digest(repo)
    load_before = _one_minute_load()
    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            input="" if stdin_ref_line is None else stdin_ref_line.rstrip("\n") + "\n",
            timeout=_HOOK_TIMEOUT_SECONDS,
        )
        stdout, exit_code = result.stdout, result.returncode
    except subprocess.TimeoutExpired as expired:
        stdout = "" if expired.stdout is None else _as_text(expired.stdout)
        exit_code = _TIMEOUT_EXIT_CODE
    load_after = _one_minute_load()
    wall_clock_seconds = time.perf_counter() - start
    digest_after = _tree_digest(repo)
    samples, reported_seconds = parse_summary(stdout)
    unknown_status_count = sum(1 for sample in samples if sample.status == "unknown")
    return HookRun(
        repetition_index=repetition_index,
        exit_code=exit_code,
        wall_clock_seconds=wall_clock_seconds,
        lefthook_reported_seconds=reported_seconds,
        jobs_parsed=len(samples),
        tree_mutated=digest_before != digest_after,
        unknown_status_count=unknown_status_count,
        samples=samples,
        load_before=load_before,
        load_after=load_after,
    )


def build_report(
    repo: Path,
    command: str,
    hook: str,
    change_class: str,
    files: tuple[str, ...],
    repetitions: int,
    lefthook_cmd: list[str],
    stdin_ref_line: str | None = None,
    hook_args: tuple[str, ...] = (),
    force: bool = False,
    include_incomplete: bool = False,
) -> GateLatencyReport:
    """Run every repetition and fold the results into one report.

    ``include_incomplete`` (wired to ``--include-incomplete``) restores the
    pre-D1-fix behavior of folding every repetition into the summaries
    regardless of its classified ``status``; see
    ``gate_latency_stats._build_summaries`` for what that changes.
    """
    runs = [
        _run_repetition(repo, lefthook_cmd, hook, files, index, stdin_ref_line, hook_args, force)
        for index in range(repetitions)
    ]
    exclusions: list[dict[str, str]] = []
    config = _load_lefthook_config(repo)
    piped = _resolve_piped_flag(config, hook, exclusions)
    # Classification happens here, after every repetition is in hand, because
    # the relative trigger is defined relative to the other repetitions in
    # this same report, and the absolute trigger needs the hook's piped
    # flag resolved above (see this module's docstring and
    # _classify_run_status).
    max_jobs_parsed = max((run.jobs_parsed for run in runs), default=0)
    runs = [
        dataclasses.replace(run, status=_classify_run_status(run, max_jobs_parsed, piped))
        for run in runs
    ]
    summaries = _build_summaries(runs, include_incomplete=include_incomplete)
    run_status_counts = _count_by_status(runs)
    declared_seconds: float | None = None
    if config is not None and hook in config:
        declared_seconds, _rows = declared_budget(config, hook)
    else:
        exclusions.append(
            {
                "field": "declared_budget_seconds",
                "reason": "lefthook.yml unreadable or missing this hook at report time",
            }
        )
    return GateLatencyReport(
        commit_sha=_git_rev_parse_head(repo),
        captured_at=datetime.now(UTC).isoformat(),
        command=_redact_url_userinfo(command),
        hook=hook,
        change_class=change_class,
        files=list(files),
        repetitions=repetitions,
        host=_host_profile(),
        runs=runs,
        summaries=summaries,
        declared_budget_seconds=declared_seconds,
        percentile_note=_percentile_note(_smallest_scope_n(summaries, repetitions)),
        stdin_ref_line_supplied=stdin_ref_line is not None,
        hook_args=[_redact_url_userinfo(arg) for arg in hook_args],
        forced=force,
        exclusions=exclusions,
        run_status_counts=run_status_counts,
        include_incomplete=include_incomplete,
        piped=piped,
    )
