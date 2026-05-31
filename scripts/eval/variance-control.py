#!/usr/bin/env python3
"""Variance-control harness for the security-spike eval (issue #1877).

Runs the SAME ``(fixture, agent)`` pair N times at ``temperature=0`` and reports
whether the Anthropic API is deterministic on long context. This answers the
question raised by the #1854 v2 re-run: 4 of 10 fixtures showed non-zero
pass-rate variance across N=3 runs at temperature=0, which should not happen if
the API were strictly deterministic.

This module is AC-1 of #1877: the control script and its variance metrics.

Running it against the live API (AC-2: one F002 run; AC-3: the committed report
under ``evals/security-spike/control/<RUN_ID>/``; AC-4: the ADR-058 follow-on
note) requires ``ANTHROPIC_API_KEY`` and ~N calls against an ~8K-token system
prompt. That is a separate, cost-bearing step a maintainer runs deliberately;
it is not performed by importing or unit-testing this harness.

The verdict vocabulary (``IDENTIFY | OK | ESCALATE``) and its extractor are the
same ones the eval scorer uses: this module reuses ``_scoring_engine._VERDICT_RE``
directly so the harness and the eval cannot disagree on what a verdict is.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from _eval_api_adapter import AnthropicAPIAdapter  # noqa: E402
from _scoring_engine import _VERDICT_RE  # noqa: E402

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_REPS = 20

# Mirrors OUTPUT_SHAPE_SUFFIX in eval-agent-vs-baseline.py so the model leads
# with one of the three tokens _VERDICT_RE extracts. Keep them in sync.
OUTPUT_SHAPE_SUFFIX = (
    "\n\nBegin your response with exactly one word: IDENTIFY, OK, or "
    "ESCALATE. Then briefly explain in <=80 words."
)

# CWE-22: ``--agent`` and ``--run-id`` flow into filesystem paths
# (templates/agents/<agent>.shared.md and evals/security-spike/control/<run_id>/).
# Both are constrained to a conservative charset, matching the run-id contract in
# eval-agent-vs-baseline.py, and every resolved path is re-checked under REPO_ROOT.
_NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
CONTROL_DIR_TEMPLATE = "evals/security-spike/control/{run_id}"
FIXTURES_DIR = "evals/security-spike/fixtures"


# ---------------------------------------------------------------------------
# Verdict extraction (reuses the scorer's canonical regex)
# ---------------------------------------------------------------------------


def extract_verdict(response: str) -> str | None:
    """Return the first ``IDENTIFY|OK|ESCALATE`` token (uppercased), or None.

    Uses ``_scoring_engine._VERDICT_RE`` so this harness extracts the verdict
    identically to the eval scorer (``verdict_scorer``).
    """
    if not response:
        return None
    match = _VERDICT_RE.match(response)
    return match.group(1).upper() if match else None


# ---------------------------------------------------------------------------
# Variance metrics (pure functions)
# ---------------------------------------------------------------------------


def levenshtein(a: str, b: str) -> int:
    """Edit distance between two strings (two-row dynamic programming)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


def normalized_levenshtein(a: str, b: str) -> float:
    """Edit distance divided by the longer length, in ``[0.0, 1.0]``."""
    longest = max(len(a), len(b))
    return 0.0 if longest == 0 else levenshtein(a, b) / longest


def response_text_variance(responses: list[str]) -> dict:
    """Text-level variance across responses.

    ``all_identical`` answers the issue's first branch (variance not from the
    API). ``mean/max_consecutive_distance`` quantify how far apart the texts are.

    ``all_identical`` requires at least 2 responses to claim identity; with 0 or
    1 responses we cannot demonstrate cross-rep identity.
    """
    count = len(responses)
    unique_count = len(set(responses))
    consecutive = [
        normalized_levenshtein(responses[i - 1], responses[i])
        for i in range(1, count)
    ]
    return {
        "count": count,
        "unique_count": unique_count,
        "all_identical": count >= 2 and unique_count == 1,
        "mean_consecutive_distance": statistics.fmean(consecutive) if consecutive else 0.0,
        "max_consecutive_distance": max(consecutive) if consecutive else 0.0,
    }


def verdict_distribution(verdicts: list[str | None]) -> dict:
    """Distribution of extracted verdicts. ``stable`` is the issue's third branch."""
    counts = Counter(v if v is not None else "<none>" for v in verdicts)
    modal_verdict, modal_count = counts.most_common(1)[0] if counts else ("<none>", 0)
    return {
        "distribution": dict(counts),
        "distinct_count": len(counts),
        "stable": len(counts) <= 1,
        "modal_verdict": modal_verdict,
        "modal_count": modal_count,
    }


def pass_rate_variance(verdicts: list[str | None], expected: str) -> dict:
    """Pass rate (verdict == expected) and its variance across reps.

    ``pass_variance`` requires at least 2 data points for ``statistics.pvariance``;
    with fewer samples, variance is reported as 0.0.
    """
    expected_upper = expected.upper()
    passes = [1 if (v is not None and v.upper() == expected_upper) else 0 for v in verdicts]
    rep_count = len(passes)
    return {
        "expected": expected_upper,
        "rep_count": rep_count,
        "pass_count": sum(passes),
        "pass_rate": (sum(passes) / rep_count) if rep_count else 0.0,
        "pass_variance": statistics.pvariance(passes) if rep_count >= 2 else 0.0,
        "all_pass": all(passes) if passes else False,
        "any_fail": not passes or 0 in passes,
    }


def classify_finding(
    text_var: dict,
    verdict_var: dict,
    reps_answered: int = 0,
    reps_total: int = 0,
) -> str:
    """Map the metrics onto the issue's three expected outcomes.

    Receives ``reps_answered`` and ``reps_total`` to detect high-error scenarios
    where sparse data would otherwise produce misleading findings.
    """
    if reps_answered < 2:
        return (
            "insufficient-data: fewer than 2 reps produced responses. "
            "Cannot determine variance; investigate transport or API failures."
        )
    if reps_total > 0 and reps_answered * 2 < reps_total:
        return (
            f"high-error-rate: only {reps_answered}/{reps_total} reps succeeded. "
            "Variance metrics are based on sparse data; investigate failures first."
        )
    if verdict_var["modal_verdict"] == "<none>":
        return (
            "verdicts-unparseable: no answered rep produced an extractable verdict. "
            "This is a parser or prompt-shape failure, not API verdict non-determinism; "
            "inspect the raw responses and the output-shape instruction."
        )
    if text_var["all_identical"]:
        return (
            "responses-bit-identical: the variance did not come from the API. "
            "Investigate the harness, scorer state, or fixture-text mutation."
        )
    if verdict_var["stable"] and verdict_var["modal_verdict"] != "<none>":
        return (
            "text-varies-verdict-stable: the API has output-text non-determinism "
            "but the scorer is robust. Gate AC-10 on verdict variance, not text variance."
        )
    return (
        "verdicts-vary: the API is genuinely non-deterministic on long context. "
        "Mitigate with a shorter system prompt, fixture redesign, larger N, or an "
        "eval designed around the non-determinism."
    )


def summarize_variance(records: list[RepRecord], expected: str) -> dict:
    """Aggregate one run's records into the variance report payload.

    Text/verdict metrics use only reps that produced a successful response; error
    reps are counted separately so a transport failure does not masquerade as
    variance.
    """
    answered = [r for r in records if r.outcome == "success" and r.response]
    responses = [r.response for r in answered]
    verdicts = [r.verdict for r in answered]
    text_var = response_text_variance(responses)
    verdict_var = verdict_distribution(verdicts)
    pass_var = pass_rate_variance(verdicts, expected)
    reps_total = len(records)
    reps_answered = len(answered)
    return {
        "reps_total": reps_total,
        "reps_answered": reps_answered,
        "reps_error": reps_total - reps_answered,
        "text_variance": text_var,
        "verdict_variance": verdict_var,
        "pass_rate_variance": pass_var,
        "finding": classify_finding(
            text_var, verdict_var, reps_answered=reps_answered, reps_total=reps_total
        ),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepRecord:
    """One repetition's outcome."""

    run_index: int
    outcome: str
    response: str
    verdict: str | None
    latency_ms: float
    error_category: str | None


def run_reps(
    adapter: AnthropicAPIAdapter,
    *,
    system: str,
    user: str,
    fixture_id: str,
    reps: int,
    model_id: str,
) -> list[RepRecord]:
    """Issue ``reps`` identical calls and collect one ``RepRecord`` each."""
    records: list[RepRecord] = []
    for index in range(1, reps + 1):
        result = adapter.call_model(
            prompt=user,
            model_id=model_id,
            fixture_id=fixture_id,
            variant="agent",
            run_index=index,
            system=system,
        )
        response = result.raw_response or ""
        records.append(
            RepRecord(
                run_index=index,
                outcome=result.outcome,
                response=response,
                verdict=extract_verdict(response),
                latency_ms=result.latency_ms,
                error_category=result.error_category,
            )
        )
    return records


def build_report_md(
    *,
    run_id: str,
    fixture_id: str,
    agent: str,
    model_id: str,
    summary: dict,
) -> str:
    """Render the human-readable variance report."""
    tv = summary["text_variance"]
    vv = summary["verdict_variance"]
    pv = summary["pass_rate_variance"]
    dist = ", ".join(f"{k}={v}" for k, v in sorted(vv["distribution"].items()))
    return (
        f"# Variance Control Report: {fixture_id} / {agent}\n\n"
        f"- Run ID: `{run_id}`\n"
        f"- Model: `{model_id}`\n"
        f"- Reps: {summary['reps_total']} (answered {summary['reps_answered']}, "
        f"error {summary['reps_error']})\n\n"
        "## Finding\n\n"
        f"{summary['finding']}\n\n"
        "## Verdict variance\n\n"
        f"- Distribution: {dist}\n"
        f"- Distinct verdicts: {vv['distinct_count']} (stable: {vv['stable']})\n"
        f"- Modal: {vv['modal_verdict']} x{vv['modal_count']}\n\n"
        "## Pass-rate variance\n\n"
        f"- Expected: {pv['expected']}\n"
        f"- Pass rate: {pv['pass_rate']:.3f} ({pv['pass_count']}/{pv['rep_count']})\n"
        f"- Pass variance: {pv['pass_variance']:.4f} (any fail: {pv['any_fail']})\n\n"
        "## Response-text variance\n\n"
        f"- Unique responses: {tv['unique_count']}/{tv['count']} "
        f"(all identical: {tv['all_identical']})\n"
        f"- Mean consecutive normalized edit distance: {tv['mean_consecutive_distance']:.4f}\n"
        f"- Max consecutive normalized edit distance: {tv['max_consecutive_distance']:.4f}\n"
    )


def _name_arg(value: str) -> str:
    if not _NAME_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"value must match {_NAME_RE.pattern} (got {value!r})"
        )
    return value


def _assert_under_repo_root(path: Path) -> Path:
    """Resolve ``path`` and confirm it stays under ``REPO_ROOT`` (CWE-22).

    Mirrors ``_assert_under_repo_root`` in eval-agent-vs-baseline.py: resolves
    with ``strict=False``, maps resolution failures to ``FileNotFoundError``,
    and raises ``FileNotFoundError`` (not ``ValueError``) on path escape so
    callers that catch ``FileNotFoundError`` handle containment uniformly. The
    comparison is against the resolved repo root, not the unresolved constant.
    """
    repo_root = REPO_ROOT.resolve()
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise FileNotFoundError(f"refusing to resolve path {path!s}: {exc}") from exc
    if repo_root not in (resolved, *resolved.parents):
        raise FileNotFoundError(
            f"refusing to access {resolved} (outside REPO_ROOT {repo_root})"
        )
    return resolved


def _load_fixture(fixture_id: str) -> dict:
    """Load and validate a fixture JSON file.

    Raises ``FileNotFoundError`` if the file is missing and ``ValueError`` if
    the fixture lacks required fields or has invalid structure.
    """
    path = _assert_under_repo_root(REPO_ROOT / FIXTURES_DIR / f"{fixture_id}.json")
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {path}")
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(fixture, dict):
        raise ValueError(
            f"fixture {fixture_id} must be a JSON object, "
            f"got {type(fixture).__name__}"
        )
    if "input" not in fixture:
        raise ValueError(f"fixture {fixture_id} missing required 'input' field")
    if not isinstance(fixture["input"], str):
        raise ValueError(
            f"fixture {fixture_id} field 'input' must be a string, "
            f"got {type(fixture['input']).__name__}"
        )
    assertions = fixture.get("assertions")
    if assertions is not None and not isinstance(assertions, list):
        raise ValueError(
            f"fixture {fixture_id} has invalid 'assertions' field (expected list or null)"
        )
    return fixture


def _expected_verdict(fixture: dict) -> str:
    assertions = fixture.get("assertions") or []
    for assertion in assertions:
        if not isinstance(assertion, dict):
            continue
        if assertion.get("kind") == "verdict" and assertion.get("expected_value"):
            return str(assertion["expected_value"])
    raise ValueError("fixture has no verdict assertion with expected_value")


def _read_agent_prompt(agent: str) -> str:
    path = _assert_under_repo_root(
        REPO_ROOT / "templates" / "agents" / f"{agent}.shared.md"
    )
    if not path.exists():
        raise FileNotFoundError(f"agent prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Quantify Anthropic API determinism at temperature=0 (issue #1877).",
    )
    parser.add_argument(
        "--fixture", default="F002", type=_name_arg, help="fixture id (default: F002)",
    )
    parser.add_argument(
        "--agent", default="security", type=_name_arg, help="agent name (default: security)",
    )
    parser.add_argument(
        "--reps", type=int, default=DEFAULT_REPS,
        help=f"repetitions (default: {DEFAULT_REPS})",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--run-id", type=_name_arg, default=None, help="run id (default: generated)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="validate inputs and print the plan; issue no API calls",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.reps < 2:
        print("Error: --reps must be at least 2 to measure variance.", file=sys.stderr)
        return 2

    try:
        fixture = _load_fixture(args.fixture)
        expected = _expected_verdict(fixture)
        agent_prompt = _read_agent_prompt(args.agent)
    except (FileNotFoundError, ValueError, OSError, UnicodeDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    system = agent_prompt
    user = str(fixture["input"]) + OUTPUT_SHAPE_SUFFIX
    run_id = args.run_id or _generate_run_id()

    # Resolve the output directory inside a guarded block: a path-containment
    # failure must exit 2 with a single-line error, not crash with a traceback
    # (the resolution happens outside the input-validation try/except above).
    try:
        out_dir = _assert_under_repo_root(
            REPO_ROOT / CONTROL_DIR_TEMPLATE.format(run_id=run_id)
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if not args.dry_run:
        existing_artifacts = [
            out_dir / name for name in ("raw.jsonl", "summary.json", "REPORT.md")
            if (out_dir / name).exists()
        ]
        if existing_artifacts:
            print(
                f"Error: run directory {out_dir.relative_to(REPO_ROOT)}/ already contains "
                f"control artifacts: {', '.join(p.name for p in existing_artifacts)}. "
                "Use a different --run-id to avoid overwriting prior results.",
                file=sys.stderr,
            )
            return 2
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"Error creating output directory: {exc}", file=sys.stderr)
            return 2

    if args.dry_run:
        print(
            f"PLAN: {args.reps} reps of fixture={args.fixture} agent={args.agent} "
            f"model={args.model} expected={expected} run_id={run_id} (no API calls)"
        )
        return 0

    adapter = AnthropicAPIAdapter()
    records = run_reps(
        adapter,
        system=system,
        user=user,
        fixture_id=args.fixture,
        reps=args.reps,
        model_id=args.model,
    )
    # Honor the AGENTS.md eval exit-code contract (3=external, 4=auth) so
    # automation does not read a control run with no successful reps as
    # success. Auth failures are terminal: exit before writing artifacts.
    if any(r.error_category == "auth" for r in records):
        print(
            "Error: authentication failed (missing or invalid ANTHROPIC_API_KEY).",
            file=sys.stderr,
        )
        return 4
    summary = summarize_variance(records, expected)
    report = build_report_md(
        run_id=run_id, fixture_id=args.fixture, agent=args.agent,
        model_id=args.model, summary=summary,
    )
    # Write to temp files first, then rename atomically to avoid partial artifacts
    # if a write fails partway through (Bug #2: mixed artifacts on failure).
    temp_suffix = ".tmp"
    output_files = [
        ("raw.jsonl", "".join(json.dumps(r.__dict__) + "\n" for r in records)),
        ("summary.json", json.dumps(summary, indent=2) + "\n"),
        ("REPORT.md", report),
    ]
    temp_paths: list[Path] = []
    final_paths: list[Path] = []
    try:
        for name, content in output_files:
            temp_path = out_dir / f"{name}{temp_suffix}"
            temp_path.write_text(content, encoding="utf-8")
            temp_paths.append(temp_path)
        for temp_path in temp_paths:
            final_path = temp_path.with_suffix("")
            temp_path.rename(final_path)
            final_paths.append(final_path)
    except OSError as exc:
        for temp_path in temp_paths:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        for final_path in final_paths:
            try:
                final_path.unlink(missing_ok=True)
            except OSError:
                pass
        print(f"Error writing output: {exc}", file=sys.stderr)
        return 2
    print(report)
    print(f"Wrote {out_dir.relative_to(REPO_ROOT)}/")
    # Every rep errored: artifacts are written as evidence, but the run did not
    # measure anything. Signal an external failure rather than success.
    if summary["reps_answered"] == 0:
        print(
            "Error: all reps failed; no successful API responses (external failure).",
            file=sys.stderr,
        )
        return 3
    return 0


def _generate_run_id() -> str:
    """ISO8601-UTC + short token. Local import keeps the pure-function surface
    free of the non-deterministic ``datetime``/``uuid`` calls that tests avoid.
    """
    import datetime
    import uuid

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


if __name__ == "__main__":
    raise SystemExit(main())
