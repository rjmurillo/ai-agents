#!/usr/bin/env python3
"""Advisory lint over the workflows that produce a pinned required context.

ADR-101 requirement 1 (`.project-toolkit/architecture/ADR-101-enforcement-planes.md`)
states the property: a job producing a required context reaches its verdict from
its own execution, and no condition sourced outside that chain's own logic may
let it report success without running the verification its name claims. The
syntactic form of that rule ("no `if:` or path filter on a required job") is
satisfiable by moving the condition into a step, so the ADR asks for a lint on
the relocated form and says exactly what it is worth:

    "a lint that fails when a step inside a required-context job carries an
    `if:` referencing `needs.*.outputs`, `github.event_name`, or
    `github.actor`. It narrows the window and does not close it."

It is P0 code, so it is advisory by the ADR's own rule 1: the pull request it
gates can edit it. What closes the window is the base-ref publisher in
requirement 2, which this module does not provide and must not be cited as.

Findings, by kind:

  step-condition        A step in a producing job carries an `if:` that
                        references `needs.<job>.outputs`, `github.event_name` or
                        `github.actor`. This is the ADR's stated lint.
  relocated-condition   A step `if:` reads `steps.<id>.outputs`, and step `<id>`
                        of the same job reads one of those three sources in its
                        `env`, `with`, `run` or `if`. This is the relocation the
                        ADR says defeats the syntactic rule, followed one level.
                        Environment spellings count: `GITHUB_EVENT_NAME` and
                        `GITHUB_ACTOR`.
  job-condition         A producing job carries a job-level `if:` that references
                        `needs.<job>.outputs`. That is a path gate: another job's
                        output decides whether this one runs. `needs.<job>.result`
                        is not flagged; the ADR names the control plane's own
                        result as the one permitted external input.
  producer-count        A pinned context has no producing job, or more than one. A
                        second job publishing the same context is a pass-through
                        (ADR-101 Implementation Notes, Phase 1: "exactly one
                        producing job per pinned context with no same-name
                        pass-through").

What this lint does not see, so a clean run is not read as more than it is:

  - A condition relocated two or more levels: a step reading `steps.b.outputs`
    where `b` itself only read `steps.a.outputs`.
  - A script the job runs that decides scope, such as which tests a partition
    selects, or a checked-in Python module that reads the event itself.
  - A condition in a job the producing job depends on. Only the producing job's
    own steps and job `if:` are read.

Job identity mirrors `scripts/github_core/workflow_event_subscriptions.py`,
`declared_required_contexts`, whose docstring states the contract:

    "Matching is exact against WorkflowSubscriptions.job_names and by prefix
    against WorkflowSubscriptions.job_name_prefixes. Prefix matching is confined
    to the expression-bearing names on purpose: applying it to literal names
    would let a job called `Validate PR` claim `Validate PR title`"

A job is named by its `name:` when it declares one and by its job id otherwise,
which is the string branch protection matches. Different from that module: it
reads whole-file subscriptions, this one keeps the job-to-context pairing so a
finding can name the job.

EXIT CODES (ADR-035):
  0 - no findings, or findings under --advisory
  1 - findings
  2 - configuration: the workflow directory is missing or a workflow does not parse

`validate_required_context_conditions` is the pre-PR gate. It is advisory: it
prints findings and always returns True, for the reason this module gives above.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS  # noqa: E402

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_CONFIG = 2

KIND_STEP = "step-condition"
KIND_RELOCATED = "relocated-condition"
KIND_JOB = "job-condition"
KIND_PRODUCERS = "producer-count"

_EXPRESSION_MARKER = "${{"

# Bracket forms (`needs['job'].outputs`) are equivalent to dotted access in the
# expression language, so both spellings are matched. `GITHUB_EVENT_NAME` and
# `GITHUB_ACTOR` are the environment spellings of the same two values; a step
# body reads them without an expression, which is how the relocation happens.
_NEEDS_OUTPUTS = re.compile(
    r"\bneeds(?:\.[A-Za-z0-9_-]+|\[\s*['\"][^'\"]+['\"]\s*\])\.outputs\b"
)
_EVENT_NAME = re.compile(
    r"\bgithub(?:\.event_name|\[\s*['\"]event_name['\"]\s*\])|\bGITHUB_EVENT_NAME\b"
)
_ACTOR = re.compile(r"\bgithub(?:\.actor|\[\s*['\"]actor['\"]\s*\])|\bGITHUB_ACTOR\b")
_STEP_OUTPUT = re.compile(r"\bsteps\.([A-Za-z0-9_-]+)\.outputs\b")

_SOURCES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("needs.*.outputs", _NEEDS_OUTPUTS),
    ("github.event_name", _EVENT_NAME),
    ("github.actor", _ACTOR),
)
_JOB_SOURCES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("needs.*.outputs", _NEEDS_OUTPUTS),
)
_STEP_BODY_KEYS = ("env", "with", "run", "if")


class WorkflowLoadError(Exception):
    """A workflow file could not be read or parsed."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One place a required-context chain departs from the property."""

    kind: str
    context: str
    workflow: str
    job: str
    detail: str
    step: str = ""

    def render(self) -> str:
        where = f"{self.workflow}:{self.job}"
        if self.step:
            where = f"{where}:{self.step}"
        return f"[{self.kind}] {self.context}: {where}: {self.detail}"


@dataclass(frozen=True, slots=True)
class ProducingJob:
    """A job whose check-run name is a pinned required context."""

    workflow: str
    job_id: str
    context: str
    body: Mapping[str, Any]


def load_workflows(workflow_dir: Path) -> dict[str, Mapping[str, Any]]:
    """Parse every workflow file under ``workflow_dir``, failing closed.

    A file that does not parse is an error, never an empty workflow: a lint that
    skipped it would report a chain it could not read as clean.
    """
    if not workflow_dir.is_dir():
        raise WorkflowLoadError(f"workflow directory not found: {workflow_dir}")
    documents: dict[str, Mapping[str, Any]] = {}
    for path in sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")]):
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise WorkflowLoadError(f"cannot parse {path.name}: {exc}") from exc
        if not isinstance(loaded, Mapping):
            raise WorkflowLoadError(f"cannot parse {path.name}: top level is not a mapping")
        documents[path.name] = loaded
    return documents


def _check_run_label(job_id: str, body: Mapping[str, Any]) -> str:
    declared = body.get("name")
    if isinstance(declared, str) and declared:
        return declared
    return str(job_id)


def _contexts_for_label(label: str, contexts: Iterable[str]) -> list[str]:
    marker = label.find(_EXPRESSION_MARKER)
    if marker == -1:
        return [context for context in contexts if context == label]
    prefix = label[:marker]
    return [context for context in contexts if context.startswith(prefix)]


def producing_jobs(
    documents: Mapping[str, Mapping[str, Any]], contexts: Iterable[str]
) -> list[ProducingJob]:
    """Every job whose check-run name is one of ``contexts``."""
    pinned = sorted(contexts)
    found: list[ProducingJob] = []
    for workflow, document in documents.items():
        jobs = document.get("jobs")
        if not isinstance(jobs, Mapping):
            continue
        for job_id, body in jobs.items():
            if not isinstance(body, Mapping):
                continue
            label = _check_run_label(str(job_id), body)
            for context in _contexts_for_label(label, pinned):
                found.append(ProducingJob(workflow, str(job_id), context, body))
    return found


def _sources_in(text: str, sources: Sequence[tuple[str, re.Pattern[str]]]) -> list[str]:
    return [name for name, pattern in sources if pattern.search(text)]


def _condition_sources(
    condition: object, sources: Sequence[tuple[str, re.Pattern[str]]]
) -> list[str]:
    # A bare boolean or number is a valid `if:` value in YAML. It references
    # nothing, so it is coerced to text rather than skipped as a type error.
    return _sources_in(str(condition), sources)


def _step_label(index: int, step: Mapping[str, Any]) -> str:
    name = step.get("name")
    if isinstance(name, str) and name:
        return name
    ident = step.get("id")
    if isinstance(ident, str) and ident:
        return ident
    return f"step[{index}]"


def _steps(producer: ProducingJob) -> list[tuple[int, Mapping[str, Any]]]:
    steps = producer.body.get("steps")
    if not isinstance(steps, list):
        return []
    return [(i, s) for i, s in enumerate(steps) if isinstance(s, Mapping)]


def _step_body_text(step: Mapping[str, Any]) -> str:
    parts = [str(step[key]) for key in _STEP_BODY_KEYS if key in step]
    return "\n".join(parts)


def _step_source_map(steps: Sequence[tuple[int, Mapping[str, Any]]]) -> dict[str, list[str]]:
    """Map each step id to the outside sources its own body reads."""
    found: dict[str, list[str]] = {}
    for _, step in steps:
        ident = step.get("id")
        if not isinstance(ident, str) or not ident:
            continue
        sources = _sources_in(_step_body_text(step), _SOURCES)
        if sources:
            found[ident] = sources
    return found


def _step_findings(producer: ProducingJob) -> list[Finding]:
    steps = _steps(producer)
    tainted = _step_source_map(steps)
    findings: list[Finding] = []
    for index, step in steps:
        if "if" not in step:
            continue
        label = _step_label(index, step)
        direct = _condition_sources(step["if"], _SOURCES)
        if direct:
            findings.append(
                Finding(
                    KIND_STEP,
                    producer.context,
                    producer.workflow,
                    producer.job_id,
                    f"step `if:` references {', '.join(direct)}",
                    label,
                )
            )
        findings.extend(_relocated_findings(producer, label, step["if"], tainted))
    return findings


def _relocated_findings(
    producer: ProducingJob,
    label: str,
    condition: object,
    tainted: Mapping[str, list[str]],
) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[str] = set()
    for match in _STEP_OUTPUT.finditer(str(condition)):
        ident = match.group(1)
        if ident in seen or ident not in tainted:
            continue
        seen.add(ident)
        findings.append(
            Finding(
                KIND_RELOCATED,
                producer.context,
                producer.workflow,
                producer.job_id,
                f"step `if:` reads steps.{ident}.outputs, and step `{ident}` reads "
                f"{', '.join(tainted[ident])}",
                label,
            )
        )
    return findings


def _job_findings(producer: ProducingJob) -> list[Finding]:
    if "if" not in producer.body:
        return []
    refs = _condition_sources(producer.body["if"], _JOB_SOURCES)
    if not refs:
        return []
    return [
        Finding(
            KIND_JOB,
            producer.context,
            producer.workflow,
            producer.job_id,
            f"job `if:` references {', '.join(refs)}, so another job's output decides "
            "whether this one runs",
        )
    ]


def _producer_count_findings(
    producers: Sequence[ProducingJob], contexts: Iterable[str]
) -> list[Finding]:
    by_context: dict[str, list[ProducingJob]] = {}
    for producer in producers:
        by_context.setdefault(producer.context, []).append(producer)
    findings: list[Finding] = []
    for context in sorted(contexts):
        owners = by_context.get(context, [])
        if len(owners) == 1:
            continue
        if not owners:
            findings.append(
                Finding(KIND_PRODUCERS, context, "-", "-", "no job produces this context")
            )
            continue
        listing = ", ".join(f"{o.workflow}:{o.job_id}" for o in owners)
        findings.append(
            Finding(
                KIND_PRODUCERS,
                context,
                owners[0].workflow,
                owners[0].job_id,
                f"{len(owners)} jobs produce this context ({listing})",
            )
        )
    return findings


def lint(
    documents: Mapping[str, Mapping[str, Any]], contexts: Iterable[str]
) -> tuple[list[Finding], list[ProducingJob]]:
    """Return every finding plus the producing jobs that were examined."""
    pinned = list(contexts)
    producers = producing_jobs(documents, pinned)
    findings: list[Finding] = []
    for producer in producers:
        findings.extend(_job_findings(producer))
        findings.extend(_step_findings(producer))
    findings.extend(_producer_count_findings(producers, pinned))
    return findings, producers


def grouped_lines(findings: Sequence[Finding]) -> list[str]:
    """One line per (kind, context, job, detail), counting the steps behind it.

    A single relocated `should-run` step fans out to a dozen sibling steps that
    all read it. Listing each buries the one fact the reader needs: which job
    carries the condition and what it reads. `--verbose` prints every step.
    """
    order: list[tuple[str, str, str, str, str]] = []
    counts: dict[tuple[str, str, str, str, str], int] = {}
    for finding in findings:
        key = (finding.kind, finding.context, finding.workflow, finding.job, finding.detail)
        if key not in counts:
            order.append(key)
            counts[key] = 0
        counts[key] += 1 if finding.step else 0
    lines: list[str] = []
    for key in order:
        kind, context, workflow, job, detail = key
        steps = counts[key]
        suffix = f" ({steps} step{'s' if steps != 1 else ''})" if steps else ""
        lines.append(f"[{kind}] {context}: {workflow}:{job}: {detail}{suffix}")
    return lines


def _summary(workflows: int, contexts: int, producers: int, findings: int) -> str:
    return (
        f"required-context-conditions: {findings} findings; examined {workflows} "
        f"workflows, {contexts} pinned contexts, {producers} producing jobs"
    )


def run(workflow_dir: Path) -> tuple[list[Finding], str]:
    """Lint ``workflow_dir`` against the pinned contexts and return a summary line."""
    documents = load_workflows(workflow_dir)
    findings, producers = lint(documents, REQUIRED_CONTEXTS)
    summary = _summary(len(documents), len(REQUIRED_CONTEXTS), len(producers), len(findings))
    return findings, summary


def validate_required_context_conditions(repo_root: Path) -> bool:
    """Advisory pre-PR gate. Prints findings and always returns True.

    Advisory by ADR-101 rule 1, not by taste: this is P0 code the gated pull
    request can edit, so its verdict cannot bind. It also cannot block honestly
    today, because the live corpus carries findings this change does not own.
    A workflow that does not parse is reported, not silently passed.
    """
    try:
        findings, summary = run(repo_root / ".github" / "workflows")
    except WorkflowLoadError as exc:
        print(f"required-context-conditions: {exc}", file=sys.stderr)
        return True
    for line in grouped_lines(findings):
        print(f"required-context-conditions: {line}")
    print(summary)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=_REPO_ROOT / ".github" / "workflows",
        help="Directory holding the workflow files (default: this checkout's).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="List every step instead of one line per job.",
    )
    parser.add_argument(
        "--advisory",
        action="store_true",
        help="Report findings but exit 0. A workflow that cannot be parsed still exits 2.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        findings, summary = run(args.workflows_dir)
    except WorkflowLoadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    lines = [f.render() for f in findings] if args.verbose else grouped_lines(findings)
    for line in lines:
        print(line)
    print(summary)
    if findings and not args.advisory:
        return EXIT_FINDINGS
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
