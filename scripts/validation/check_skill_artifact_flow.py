#!/usr/bin/env python3
"""Gate: skills declare the artifacts they read and write, and the data connects.

ADR-123 owns the contract. Each skill template may declare typed lists under
the `metadata` key it already supports:

    metadata:
      inputs:
        requirements-spec:
          required: false
      outputs:
        execution-plan:
          path: plans/active/

Six invariants are blocking:

  0. skillforge's stdlib frontmatter parser can read the template
  1. every entry has the declared shape (keys, types, name and path grammar)
  2. one producing skill per artifact name
  3. every `source: skill` input names a produced artifact, and a shipped
     consumer names a shipped producer
  4. the six lifecycle skills connect in `LIFECYCLE_ORDER` through data,
     with helper outputs credited along the `routing.invoker` chain
  5. each lifecycle skill carries a `## Handoff` line that agrees with (4)

A skill with no `inputs` or `outputs` is not a defect, except that item 4
needs the lifecycle skills to declare enough data to connect.

The gate reads `templates/skills/*.SKILL.md.tmpl`, the canonical source. It
never opens, creates, or writes a declared `path`.

Exit codes (ADR-035):
    0 - Success (every declaration is well-formed and the lifecycle connects)
    1 - Logic error (a declaration is malformed, unresolved, or disconnected)
    2 - Config error (invalid repository root, a template that cannot be read,
        or `templates/skills` is absent or holds no skill templates, which
        would make a PASS vacuous). An invalid argument combination also exits 2.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import yaml  # noqa: E402
from instruction_budget_globs import _FRONTMATTER_RE, _UniqueKeySafeLoader  # noqa: E402
from skill_artifact_schema import (  # noqa: E402
    ARTIFACT_RE,
    INPUT_KEYS,
    OUTPUT_KEYS,
    PATH_RE,
    SOURCES,
    Input,
    Output,
    SubsetParserUnavailableError,
    parse_inputs,
    parse_outputs,
    subset_defect,
)
from skill_routing_model import LIFECYCLE_ORDER, RESERVED_INVOKERS  # noqa: E402

__all__ = [
    "ARTIFACT_RE",
    "INPUT_KEYS",
    "OUTPUT_KEYS",
    "PATH_RE",
    "SOURCES",
    "Input",
    "Output",
    "main",
    "survey",
    "validate_skill_artifact_flow",
]

TEMPLATE_DIR = "templates/skills"
TEMPLATE_SUFFIX = ".SKILL.md.tmpl"

# A walk that reaches the router, a reserved invoker, an agent, or an unknown
# name credits nobody: none of them is a lifecycle skill.
TERMINAL_INVOKERS: frozenset[str] = frozenset({"autoplan", *RESERVED_INVOKERS})

HANDOFF_HEADING = "## Handoff"
HANDOFF_RE = re.compile(
    r"Writes: (?P<writes>none|`[^`]+`(?:, `[^`]+`)*)\. Next: (?P<next>none|`/[a-z][a-z0-9-]*`)\."
)


class TreeError(Exception):
    """The template tree cannot answer the question this gate asks."""


@dataclass(frozen=True)
class SkillFlow:
    """One skill template's declarations and the facts the checks need."""

    name: str
    rel: str
    shipped: bool
    invoker: str | None
    inputs: tuple[Input, ...]
    outputs: tuple[Output, ...]
    body: str


@dataclass(frozen=True)
class Survey:
    """Everything one read of the tree produces."""

    skills: dict[str, SkillFlow]
    credit: dict[str, str | None]
    findings: list[str]


def _split(text: str) -> tuple[dict[str, object], str]:
    """Return (frontmatter, body), rejecting duplicate keys.

    Raises yaml.YAMLError on malformed frontmatter, and ValueError
    (`UnsupportedApplyToError`) on a duplicate key.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}, text
    data = yaml.load(match.group(1), Loader=_UniqueKeySafeLoader)
    return (data if isinstance(data, dict) else {}), text[match.end() :]


def _read_skill(path: Path, rel: str) -> tuple[SkillFlow | None, list[str]]:
    """Read one template, returning its flow or the defects that prevented it."""
    name = path.name.removesuffix(TEMPLATE_SUFFIX)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TreeError(f"{rel}: unreadable: {exc}") from exc
    try:
        subset = subset_defect(rel, text)
    except SubsetParserUnavailableError as exc:
        raise TreeError(str(exc)) from exc
    try:
        front, body = _split(text)
    except (yaml.YAMLError, ValueError) as exc:
        defects = [f"{rel}: frontmatter does not parse: {exc}".splitlines()[0]]
        return None, defects + ([subset] if subset else [])
    metadata = front.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    routing = metadata.get("routing")
    invoker = routing.get("invoker") if isinstance(routing, dict) else None
    inputs, input_defects = parse_inputs(rel, metadata.get("inputs"))
    outputs, output_defects = parse_outputs(rel, metadata.get("outputs"))
    flow = SkillFlow(
        name=name,
        rel=rel,
        shipped=metadata.get("distribution") != "repo-local",
        invoker=invoker if isinstance(invoker, str) else None,
        inputs=inputs,
        outputs=outputs,
        body=body,
    )
    return flow, ([subset] if subset else []) + input_defects + output_defects


def collect(repo_root: Path) -> tuple[dict[str, SkillFlow], list[str]]:
    """Read every skill template. Raises TreeError when the tree is unusable."""
    template_dir = repo_root / TEMPLATE_DIR
    if not template_dir.is_dir():
        raise TreeError(f"{TEMPLATE_DIR} does not exist under {repo_root}")
    paths = sorted(template_dir.glob(f"*{TEMPLATE_SUFFIX}"))
    if not paths:
        raise TreeError(f"{TEMPLATE_DIR} holds no *{TEMPLATE_SUFFIX} files")
    skills: dict[str, SkillFlow] = {}
    defects: list[str] = []
    for path in paths:
        rel = path.relative_to(repo_root).as_posix()
        flow, found = _read_skill(path, rel)
        defects.extend(found)
        if flow is not None:
            skills[flow.name] = flow
    return skills, defects


def producers(skills: dict[str, SkillFlow]) -> dict[str, list[str]]:
    """Return every declared output artifact mapped to the skills producing it."""
    index: dict[str, list[str]] = {}
    for flow in skills.values():
        for output in flow.outputs:
            index.setdefault(output.artifact, []).append(flow.name)
    return index


def _producer_defects(index: dict[str, list[str]]) -> list[str]:
    """Item 2: one producer per artifact name."""
    return [
        f"artifact `{artifact}` has {len(names)} producers ({', '.join(sorted(names))}); "
        "ADR-123 allows one"
        for artifact, names in sorted(index.items())
        if len(names) > 1
    ]


def _input_defects(skills: dict[str, SkillFlow], index: dict[str, list[str]]) -> list[str]:
    """Item 3: every skill-sourced input resolves, shipped to shipped."""
    defects: list[str] = []
    for flow in skills.values():
        for item in flow.inputs:
            if item.source != "skill":
                continue
            names = index.get(item.artifact)
            if not names:
                defects.append(
                    f"{flow.rel}: input `{item.artifact}` has no producing skill; "
                    "declare its producer or set `source: user` or `source: repo`"
                )
                continue
            if flow.shipped and not any(skills[name].shipped for name in names):
                defects.append(
                    f"{flow.rel}: shipped skill reads `{item.artifact}`, which only a "
                    "repo-local skill produces"
                )
    return defects


def _walk(name: str, skills: dict[str, SkillFlow]) -> tuple[str | None, tuple[str, ...]]:
    """Return (credited lifecycle skill or None, cycle segment or ()).

    The walk starts at `name` and follows `routing.invoker` one step at a time.
    It stops at the first lifecycle skill. A shipped skill's walk ends at its
    first repo-local invoker, and a repo-local skill never credits a shipped
    lifecycle skill.
    """
    start = skills[name]
    if name in LIFECYCLE_ORDER:
        return name, ()
    seen = [name]
    current = start
    while True:
        invoker = current.invoker
        if invoker is None or invoker in TERMINAL_INVOKERS or invoker not in skills:
            return None, ()
        target = skills[invoker]
        if start.shipped and not target.shipped:
            return None, ()
        if invoker in seen:
            return None, tuple(seen[seen.index(invoker) :])
        if invoker in LIFECYCLE_ORDER:
            return (invoker if start.shipped or not target.shipped else None), ()
        seen.append(invoker)
        current = target


def credit_outputs(skills: dict[str, SkillFlow]) -> tuple[dict[str, str | None], list[str]]:
    """Item 4 walk: credit each output-declaring skill to a lifecycle skill."""
    credit: dict[str, str | None] = {}
    defects: list[str] = []
    reported: set[frozenset[str]] = set()
    for name in sorted(skills):
        if not skills[name].outputs:
            continue
        owner, cycle = _walk(name, skills)
        credit[name] = owner
        key = frozenset(cycle)
        if cycle and key not in reported and any(skills[n].outputs for n in cycle):
            reported.add(key)
            loop = " -> ".join([*cycle, cycle[0]])
            defects.append(f"invoker cycle {loop} contains a skill that declares outputs")
    return credit, defects


def credited_artifacts(
    skills: dict[str, SkillFlow], credit: dict[str, str | None]
) -> dict[str, str]:
    """Return each output artifact mapped to the lifecycle skill it is credited to."""
    owners: dict[str, str] = {}
    for name, lifecycle in credit.items():
        if lifecycle is None:
            continue
        for output in skills[name].outputs:
            owners[output.artifact] = lifecycle
    return owners


def _lifecycle_defects(skills: dict[str, SkillFlow], owners: dict[str, str]) -> list[str]:
    """Item 4 order: each later step reads earlier data, never required later data."""
    defects: list[str] = []
    position = {name: index for index, name in enumerate(LIFECYCLE_ORDER)}
    for index, name in enumerate(LIFECYCLE_ORDER):
        flow = skills.get(name)
        if flow is None:
            defects.append(f"lifecycle skill `{name}` has no template under {TEMPLATE_DIR}")
            continue
        sourced = [item for item in flow.inputs if item.source == "skill"]
        if index > 0 and not any(
            position.get(owners.get(item.artifact, ""), index) < index for item in sourced
        ):
            earlier = ", ".join(LIFECYCLE_ORDER[:index])
            defects.append(
                f"{flow.rel}: lifecycle skill `{name}` declares no input credited to an "
                f"earlier lifecycle skill ({earlier})"
            )
        for item in sourced:
            later = owners.get(item.artifact)
            if item.required and later is not None and position[later] > index:
                defects.append(
                    f"{flow.rel}: `{name}` requires `{item.artifact}`, credited to the later "
                    f"lifecycle skill `{later}`"
                )
    return defects


def _handoff_line(body: str) -> str | None:
    """Return the first non-blank line after the `## Handoff` heading, or None."""
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == HANDOFF_HEADING:
            for candidate in lines[index + 1 :]:
                if candidate.strip():
                    return candidate.strip()
            return ""
    return None


def _handoff_defects(skills: dict[str, SkillFlow], owners: dict[str, str]) -> list[str]:
    """Item 5: the Handoff line names own outputs, only credited ones, and the next step."""
    defects: list[str] = []
    for index, name in enumerate(LIFECYCLE_ORDER):
        flow = skills.get(name)
        if flow is None:
            continue
        line = _handoff_line(flow.body)
        if line is None:
            defects.append(f"{flow.rel}: lifecycle skill has no `{HANDOFF_HEADING}` section")
            continue
        match = HANDOFF_RE.fullmatch(line)
        if match is None:
            defects.append(
                f"{flow.rel}: Handoff line {line!r} must read "
                '"Writes: `a`, `b`. Next: `/skill`." (or `none` in either slot)'
            )
            continue
        writes = match.group("writes")
        named = set() if writes == "none" else set(re.findall(r"`([^`]+)`", writes))
        own = {output.artifact for output in flow.outputs}
        credited = {artifact for artifact, owner in owners.items() if owner == name}
        for artifact in sorted(own - named):
            defects.append(f"{flow.rel}: Handoff line omits its own output `{artifact}`")
        for artifact in sorted(named - credited):
            defects.append(
                f"{flow.rel}: Handoff line names `{artifact}`, which is not credited to `{name}`"
            )
        expected = (
            f"`/{LIFECYCLE_ORDER[index + 1]}`" if index + 1 < len(LIFECYCLE_ORDER) else "none"
        )
        if match.group("next") != expected:
            defects.append(f"{flow.rel}: Handoff `Next:` must be {expected}")
    return defects


def survey(repo_root: Path) -> Survey:
    """Read the tree once and return the skills, the credit map, and every finding."""
    skills, defects = collect(repo_root)
    index = producers(skills)
    credit, cycle_defects = credit_outputs(skills)
    owners = credited_artifacts(skills, credit)
    findings = (
        sorted(defects)
        + _producer_defects(index)
        + sorted(_input_defects(skills, index))
        + cycle_defects
        + _lifecycle_defects(skills, owners)
        + _handoff_defects(skills, owners)
    )
    return Survey(skills=skills, credit=credit, findings=findings)


def _counts(skills: dict[str, SkillFlow]) -> tuple[int, int, int]:
    """Return (declaring skills, inputs, outputs)."""
    declaring = sum(1 for flow in skills.values() if flow.inputs or flow.outputs)
    inputs = sum(len(flow.inputs) for flow in skills.values())
    outputs = sum(len(flow.outputs) for flow in skills.values())
    return declaring, inputs, outputs


def graph(result: Survey) -> dict[str, object]:
    """Return the artifact graph as plain data for JSON output."""
    skills = result.skills
    producers_of: dict[str, list[dict[str, object]]] = {}
    consumers_of: dict[str, list[dict[str, object]]] = {}
    for flow in skills.values():
        for output in flow.outputs:
            producers_of.setdefault(output.artifact, []).append(
                {
                    "skill": flow.name,
                    "path": output.path,
                    "credited_to": result.credit.get(flow.name),
                }
            )
        for item in flow.inputs:
            consumers_of.setdefault(item.artifact, []).append(
                {"skill": flow.name, "source": item.source, "required": item.required}
            )
    names = sorted(set(producers_of) | set(consumers_of))
    artifacts = {
        name: {"producers": producers_of.get(name, []), "consumers": consumers_of.get(name, [])}
        for name in names
    }
    return {"lifecycle_order": list(LIFECYCLE_ORDER), "artifacts": artifacts}


def render_report(result: Survey) -> str:
    """Return the text report: counts plus artifacts nobody consumes."""
    declaring, inputs, outputs = _counts(result.skills)
    produced = {output.artifact for flow in result.skills.values() for output in flow.outputs}
    consumed = {item.artifact for flow in result.skills.values() for item in flow.inputs}
    artifacts = produced | consumed
    unconsumed = sorted(produced - consumed)
    lines = [
        f"skills: {len(result.skills)}",
        f"declaring skills: {declaring}",
        f"inputs: {inputs}",
        f"outputs: {outputs}",
        f"artifacts: {len(artifacts)}",
        f"no consumer: {len(unconsumed)}",
        *(f"no consumer {name}" for name in unconsumed),
    ]
    return "\n".join(lines)


def _report_findings(findings: list[str]) -> None:
    """Print findings to stderr in the gate's usual shape."""
    print(f"[FAIL] {len(findings)} skill artifact flow violation(s):", file=sys.stderr)
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    print(
        "\nFix: declare typed `metadata.inputs` and `metadata.outputs` in the skill "
        "template under templates/skills/. Contract: "
        ".project-toolkit/architecture/ADR-123-skill-artifact-flow-declarations.md",
        file=sys.stderr,
    )


def _summary(result: Survey) -> str:
    declaring, inputs, outputs = _counts(result.skills)
    return (
        f"examined {len(result.skills)} skill templates: {declaring} declare data, "
        f"{inputs} inputs, {outputs} outputs; {len(result.findings)} violation(s)"
    )


def validate_skill_artifact_flow(repo_root: Path) -> bool:
    """Return True when every declaration is valid and the lifecycle connects.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract that
    ``pre_pr_sequence.py`` expects. Raises TreeError on an unusable tree.
    """
    result = survey(repo_root)
    print(_summary(result))
    if not result.findings:
        return True
    _report_findings(result.findings)
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", default=None)
    parser.add_argument(
        "--report", action="store_true", help="print counts and unconsumed artifacts"
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if args.report and args.format == "json":
        # JSON output has no report section; accepting both would drop --report silently.
        parser.error("--report cannot be combined with --format json")
    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    )
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    try:
        result = survey(repo_root)
    except TreeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(graph(result), indent=2, sort_keys=True))
    elif args.report:
        print(render_report(result))
    print(_summary(result), file=sys.stderr if args.format == "json" else sys.stdout)
    if result.findings:
        _report_findings(result.findings)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
