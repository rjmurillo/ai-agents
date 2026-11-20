#!/usr/bin/env python3
"""Deterministic lint for skill frontmatter, size limits, and routing declarations.

Every rule here is a static check with a stable id. Nothing in the checked
skill runs, no model is called, and the standard library is the only import,
so the verdict is the same on every machine.

Usage:
    lint_skill_frontmatter.py SKILL_DIR [SKILL_DIR ...] [--root DIR] [--strict]
                              [--format text|json]
    lint_skill_frontmatter.py --list [--format text|json]

Rules:
    fm.subset-parse              MUST    frontmatter parses under the stdlib subset
    fm.size.bytes                MUST    SKILL.md is at most 24576 bytes (or size-exception)
    fm.size.headroom             SHOULD  SKILL.md leaves 256 bytes for generated mirrors
    fm.artifacts.shape           MUST    metadata.inputs/outputs keyed by artifact name
    fm.capability.shape          MUST    metadata.capability uses the closed key set
    fm.routing.intents-role      MUST    intents only on a front-door skill
    fm.routing.phrases-routable  SHOULD  quoted trigger phrases match the skill's intents
    fm.handoff.shape             MUST    a "Writes:" Handoff line holds the one-line shape
    fm.description.redirect      SHOULD  the description names what not to use it for

Statuses: PASS, FAIL (MUST failed), WARN (SHOULD failed), NOT_APPLICABLE,
NOT_EVALUATED (a rule could not decide, such as unparsable frontmatter).

Exit codes:
    0  no FAIL, and no NOT_EVALUATED on a MUST rule
    1  a FAIL or a MUST rule NOT_EVALUATED; with --strict, also any WARN
    2  usage error: bad flag, or a path that is missing or outside --root
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _conformance_parse as subset
from _lint_frontmatter_checks import (
    ARTIFACT_RE,
    CAPABILITY_KEYS,
    CAPABILITY_KINDS,
    HANDOFF_RE,
    INPUT_KEYS,
    OUTPUT_KEYS,
    PATH_RE,
    SKILL_BYTE_HEADROOM,
    SKILL_BYTE_LIMIT,
    SOURCES,
    NotApplicableError,
    NotEvaluatedError,
    artifacts_shape,
    capability_shape,
    description_redirect,
    handoff_shape,
    intents_role,
    phrases_routable,
    size_bytes,
    size_headroom,
    subset_parse,
    trigger_phrases,
)

# Re-exported so callers and the mirror test read one module.
__all__ = [
    "ARTIFACT_RE",
    "CAPABILITY_KEYS",
    "CAPABILITY_KINDS",
    "HANDOFF_RE",
    "INPUT_KEYS",
    "OUTPUT_KEYS",
    "PATH_RE",
    "RULES",
    "SKILL_BYTE_HEADROOM",
    "SKILL_BYTE_LIMIT",
    "SOURCES",
    "added_failures",
    "lint_text",
    "main",
    "new_failures",
    "trigger_phrases",
]
from _path_guard import contained_realpath, resolve_root


@dataclass(frozen=True)
class Rule:
    id: str
    level: str
    summary: str
    check: Callable[[subset.SkillDoc], list[str]]


@dataclass(frozen=True)
class Result:
    rule: Rule
    status: str
    messages: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.rule.id,
            "level": self.rule.level,
            "status": self.status,
            "messages": list(self.messages),
        }


RULES: tuple[Rule, ...] = (
    Rule("fm.subset-parse", "MUST", "Frontmatter parses under the stdlib subset.", subset_parse),
    Rule("fm.size.bytes", "MUST", f"SKILL.md is at most {SKILL_BYTE_LIMIT} bytes.", size_bytes),
    Rule(
        "fm.size.headroom",
        "SHOULD",
        f"SKILL.md leaves {SKILL_BYTE_HEADROOM} bytes for generated mirrors.",
        size_headroom,
    ),
    Rule(
        "fm.artifacts.shape",
        "MUST",
        "metadata.inputs and metadata.outputs are keyed by artifact name.",
        artifacts_shape,
    ),
    Rule(
        "fm.capability.shape",
        "MUST",
        "metadata.capability uses the closed key set and kind list.",
        capability_shape,
    ),
    Rule(
        "fm.routing.intents-role",
        "MUST",
        "routing.intents appear only on a front-door skill.",
        intents_role,
    ),
    Rule(
        "fm.routing.phrases-routable",
        "SHOULD",
        "Quoted trigger phrases match one of the skill's own intents.",
        phrases_routable,
    ),
    Rule("fm.handoff.shape", "MUST", "A Handoff section holds the one-line shape.", handoff_shape),
    Rule(
        "fm.description.redirect",
        "SHOULD",
        "A user-facing description names what not to use the skill for.",
        description_redirect,
    ),
)


def evaluate(doc: subset.SkillDoc) -> list[Result]:
    results: list[Result] = []
    for rule in RULES:
        try:
            problems = rule.check(doc)
        except NotApplicableError as exc:
            results.append(Result(rule, "NOT_APPLICABLE", (str(exc),)))
            continue
        except NotEvaluatedError as exc:
            results.append(Result(rule, "NOT_EVALUATED", (str(exc),)))
            continue
        if not problems:
            results.append(Result(rule, "PASS", ()))
        else:
            results.append(
                Result(rule, "FAIL" if rule.level == "MUST" else "WARN", tuple(problems))
            )
    return results


def lint_text(text: str) -> list[Result]:
    """Lint SKILL.md text that is not on disk, such as a skillopt candidate.

    Parses the same way `load_skill` does, without the directory checks.
    """
    doc = subset.SkillDoc(directory=Path("."), skill_md=Path("SKILL.md"), text=text)
    subset.parse_doc_text(doc)
    return evaluate(doc)


# Rules whose FAIL message embeds a measurement (a byte count). Compare the
# measurement, never the message text: shrinking an oversized skill is not a
# new failure, and growing it further is.
MEASURED_RULES = frozenset({"fm.size.bytes"})
_MEASUREMENT = re.compile(r"(\d+) bytes")


_LINE_NUMBER = re.compile(r"\bline \d+\b")


def _unplaced(message: str) -> str:
    """Drop a parser line number, so moving an inherited error is not a new one."""
    return _LINE_NUMBER.sub("line N", message)


def _measurement(result: Result) -> int:
    for message in result.messages:
        match = _MEASUREMENT.search(message)
        if match:
            return int(match.group(1))
    return 0


def _grew(result: Result, before: list[Result]) -> bool:
    """Return whether a measured FAIL is new, or larger than the incumbent's."""
    prior = [r for r in before if r.rule.id == result.rule.id and r.status == "FAIL"]
    return not prior or _measurement(result) > _measurement(prior[0])


def added_failures(before: list[Result], after: list[Result]) -> list[Result]:
    """Return MUST failures in `after` that `before` does not have.

    A FAIL counts when it carries a message the incumbent's FAIL of the same
    rule did not, so an inherited failure cannot hide a new violation of that
    rule. Only the new messages are returned. A MUST rule that is NOT_EVALUATED
    counts when the incumbent PASSed it, because the standalone linter treats
    that state as failing (`failed`). An incumbent that was itself
    NOT_EVALUATED already carried the problem.
    """
    failing_before = {r.rule.id: set(r.messages) for r in before if r.status == "FAIL"}
    passing_before = {r.rule.id for r in before if r.status == "PASS"}
    added = []
    for result in after:
        if result.status == "FAIL" and result.rule.id in MEASURED_RULES:
            if _grew(result, before):
                added.append(result)
        elif result.status == "FAIL":
            inherited = {_unplaced(m) for m in failing_before.get(result.rule.id, set())}
            new_messages = tuple(m for m in result.messages if _unplaced(m) not in inherited)
            if new_messages:
                added.append(Result(result.rule, result.status, new_messages))
        elif (
            result.status == "NOT_EVALUATED"
            and result.rule.level == "MUST"
            and result.rule.id in passing_before
        ):
            added.append(result)
    return added


def new_failures(incumbent: str, candidate: str) -> list[Result]:
    """Return MUST failures the candidate has and the incumbent does not.

    An optimizer may keep a failure it inherited; it may not add one.
    """
    return added_failures(lint_text(incumbent), lint_text(candidate))


def failed(results: list[Result], strict: bool) -> bool:
    for result in results:
        if result.status == "FAIL":
            return True
        if result.status == "NOT_EVALUATED" and (result.rule.level == "MUST" or strict):
            return True
        if strict and result.status == "WARN":
            return True
    return False


def render_text(reports: list[tuple[str, list[Result]]]) -> str:
    lines: list[str] = []
    for path, results in reports:
        lines.append(f"skill frontmatter lint: {path}")
        shown = [r for r in results if r.status not in ("PASS", "NOT_APPLICABLE")]
        for result in shown:
            lines.append(f"  {result.status:<13} {result.rule.level:<6} {result.rule.id}")
            lines.extend(f"      {message}" for message in result.messages)
        counts: dict[str, int] = {}
        for result in results:
            counts[result.status] = counts.get(result.status, 0) + 1
        summary = ", ".join(f"{count} {status.lower()}" for status, count in sorted(counts.items()))
        lines.append(f"  {len(results)} rules: {summary}")
    return "\n".join(lines) + "\n"


def render_catalog(fmt: str) -> str:
    if fmt == "json":
        rows = [{"id": r.id, "level": r.level, "summary": r.summary} for r in RULES]
        return json.dumps({"rules": rows}, indent=2) + "\n"
    width = max(len(rule.id) for rule in RULES)
    return "\n".join(f"{r.id:<{width}}  {r.level:<6}  {r.summary}" for r in RULES) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit codes:" + __doc__.split("Exit codes:", 1)[1],
    )
    parser.add_argument("skills", nargs="*", metavar="SKILL_DIR")
    parser.add_argument("--root", help="every SKILL_DIR must resolve inside DIR (default: cwd)")
    parser.add_argument("--strict", action="store_true", help="also fail on WARN")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--list", action="store_true", help="print the rule catalog and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list:
        sys.stdout.write(render_catalog(args.format))
        return 0
    if not args.skills:
        parser.error("give at least one SKILL_DIR, or --list")
    if args.root is not None and not Path(args.root).is_dir():
        parser.error(f"--root is not a directory: {args.root}")
    root = resolve_root(args.root)
    reports: list[tuple[str, list[Result]]] = []
    for raw in args.skills:
        if not Path(raw).is_dir():
            parser.error(f"not a directory: {raw}")
        real = contained_realpath(Path(raw), root)
        if real is None:
            parser.error(f"{raw} resolves outside the root {root}; pass --root")
        doc = subset.load_skill(Path(real), Path(root))
        reports.append((raw, evaluate(doc)))
    exit_code = 1 if any(failed(results, args.strict) for _, results in reports) else 0
    if args.format == "json":
        payload = {
            "strict": args.strict,
            "exit_code": exit_code,
            "skills": [
                {"path": path, "results": [r.to_json() for r in results]}
                for path, results in reports
            ],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(render_text(reports))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
