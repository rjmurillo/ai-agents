"""Step and job condition scanning for the required-context lint.

Given one producing job, reports the conditions that read an outside source:
directly in a step `if:`, relocated one level through `steps.<id>.outputs` or an
environment value, or at job level through another job's output. The source
patterns live in required_context_sources.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from required_context_sources import (
    JOB_SOURCES,
    SOURCES,
    STEP_OUTPUT,
    condition_sources,
    env_sources,
    sources_in,
    step_body_text,
    text,
)
from required_context_types import (
    KIND_JOB,
    KIND_RELOCATED,
    KIND_STEP,
    Finding,
    ProducingJob,
    mapping,
)


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


def _tainted_env(producer: ProducingJob) -> dict[str, list[str]]:
    """Map each workflow-level or job-level env name to the sources its value reads.

    A step that reads `env.NAME` inherits those sources: the outside value
    reached it through the environment instead of through the step's own text.
    A job-level definition wins over a workflow-level one, as it does at run time.
    """
    tainted: dict[str, list[str]] = {}
    for scope in (producer.workflow_env, mapping(producer.body, "env")):
        for name, value in scope.items():
            value_text = text(value)
            sources = sources_in(value_text, SOURCES)
            for source in env_sources(value_text, tainted):
                if source not in sources:
                    sources.append(source)
            if sources:
                tainted[str(name).lower()] = sources
            else:
                tainted.pop(str(name).lower(), None)
    return tainted


def _step_source_map(
    steps: Sequence[tuple[int, Mapping[str, Any]]], tainted_env: Mapping[str, list[str]]
) -> dict[str, list[str]]:
    """Map each step id to the outside sources its own body reads."""
    found: dict[str, list[str]] = {}
    for _, step in steps:
        ident = step.get("id")
        if not isinstance(ident, str) or not ident:
            continue
        ident = ident.lower()
        body = step_body_text(step)
        sources = sources_in(body, SOURCES)
        # A step's own `env:` replaces a workflow or job value of the same name
        # for that step's body. If the override itself reads a source, the body
        # text above already carries it, so only the untainted overrides need
        # to hide the inherited taint.
        overridden = {str(name).lower() for name in mapping(step, "env")}
        inherited = {n: v for n, v in tainted_env.items() if n not in overridden}
        for source in env_sources(body, inherited):
            if source not in sources:
                sources.append(source)
        if sources:
            found[ident] = sources
    return found


def step_findings(producer: ProducingJob) -> list[Finding]:
    steps = _steps(producer)
    tainted_env = _tainted_env(producer)
    tainted = _step_source_map(steps, tainted_env)
    findings: list[Finding] = []
    for index, step in steps:
        if "if" not in step:
            continue
        label = _step_label(index, step)
        direct = condition_sources(step["if"], SOURCES)
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
        findings.extend(
            _relocated_findings(producer, label, step["if"], tainted, tainted_env)
        )
    return findings


def _relocated_findings(
    producer: ProducingJob,
    label: str,
    condition: object,
    tainted: Mapping[str, list[str]],
    tainted_env: Mapping[str, list[str]],
) -> list[Finding]:
    condition_text = text(condition)
    findings: list[Finding] = []
    seen: set[str] = set()
    for match in STEP_OUTPUT.finditer(condition_text):
        ident = (match.group(1) or match.group(2)).lower()
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
    env_found = env_sources(condition_text, tainted_env)
    if env_found:
        findings.append(
            Finding(
                KIND_RELOCATED,
                producer.context,
                producer.workflow,
                producer.job_id,
                f"step `if:` reads an env value that is set from {', '.join(env_found)}",
                label,
            )
        )
    return findings


def job_findings(producer: ProducingJob) -> list[Finding]:
    if "if" not in producer.body:
        return []
    refs = condition_sources(producer.body["if"], JOB_SOURCES)
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
