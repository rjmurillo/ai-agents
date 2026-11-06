#!/usr/bin/env python3
"""Decide whether a change needs a documentation-accuracy check (``/test`` Gate 5).

``/test`` Gate 5 composes the ``doc-accuracy`` skill instead of carrying its own
documentation checklist (issue #5398). A full audit on every change is noise,
and an extension test misses both directions: a code change can make prose
stale, and a Markdown edit can change what an agent does. This script decides
from verified changed paths and diff effects whether the change could
invalidate a durable claim or alter executable prose. It is a pure function of
its arguments, so the same change always gets the same decision.

Path classification reuses the ``/review`` risk-axis classifier from issue
#4981 (the sibling ``review`` skill's ``select_axes.py``), including its model
of which files ``doc_accuracy.py`` can read. This script defines no second
risk taxonomy.

Path kinds, in the order they are tested:

- ``test``: a test or fixture. Never a durable claim. Skips.
- ``historical``: dated evidence such as a retrospective or a changelog. Not an
  evergreen contract. Skips, and is reported as info when a scan covers it.
- ``unreadable``: a document the scanner cannot read. Activates, and is named
  so the caller reports it unverified instead of passing it.
- ``document``: Markdown the scanner reads. Activates.
- ``agent-artifact``: a skill, agent, hook, prompt, or command file that is not
  Markdown. Activates, because prose generated or read from it steers agents.
- ``api``: a type or public API surface. Activates.
- ``code``: any other classified path. Activates only through an effect.
- ``unclassified``: a path the classifier cannot place. Fails closed.

An empty path list, an unknown effect, and an unclassified path also activate.

``/build`` runs this script once and saves the JSON as its documentation-impact
record. ``/test`` Gate 5 passes that file back through ``--build-record``. The
record's effects join the verified effects, and a record that activated keeps
the decision at activate, so a signal raised at build time cannot be dropped
before the principal gate runs.

EXIT CODES (ADR-035):
    0 - A decision was emitted on stdout as JSON.
    2 - Config error: the review-axis classifier could not be loaded, the
        diff base is blank, or the build record cannot be read.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

# Diff effects the caller verified in the diff body. Each one is a way a change
# can invalidate a documented claim when no changed path shows it.
EFFECTS = (
    "public-api",
    "cli-surface",
    "config-or-defaults",
    "quantitative-claim",
    "behavioral-claim",
    "support-or-limit",
    "example-change",
    "generated-input",
    "agent-behavior",
)

# Effects whose claims the deterministic scan cannot verify: a count, a default,
# a flag, or a limit is a value, and only a read of the code settles it.
REQUIRED_ESCALATION = frozenset(
    {
        "public-api",
        "cli-surface",
        "config-or-defaults",
        "quantitative-claim",
        "behavioral-claim",
        "support-or-limit",
    }
)

ESCALATION_REQUIRED = "required"
ESCALATION_ON_FINDINGS = "on-findings"
ESCALATION_NONE = "none"

_HISTORICAL_DIRECTORIES = frozenset(
    {"retrospective", "retrospectives", "archive", "archives", "session-logs", "sessions"}
)
_HISTORICAL_NAMES = frozenset({"changelog.md", "history.md"})
_DATED_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}")
_TEST_DIRECTORIES = frozenset({"tests", "fixtures"})

_DECISIONS = ("activate", "skip")

_CLASSIFIER_RELATIVE = Path("review") / "scripts" / "select_axes.py"

_INTERNAL_WHY = {
    "test": "test or fixture only",
    "historical": "historical evidence, not an evergreen contract",
    "code": "code or configuration with no verified documentation-impact effect",
}


def _segments(path: str) -> list[str]:
    return [segment for segment in path.replace("\\", "/").strip().lower().split("/") if segment]


def load_classifier(path: Path | None = None) -> ModuleType:
    """Load the sibling ``review`` skill's ``select_axes`` module.

    Both skills ship in the same ``skills/`` directory of every plugin root, so
    the sibling path resolves in the source tree and in a vendored install.
    """
    target = path or Path(__file__).resolve().parents[2] / _CLASSIFIER_RELATIVE
    if not target.is_file():
        raise FileNotFoundError(f"review-axis classifier not found: {target}")
    spec = importlib.util.spec_from_file_location("doc_accuracy_trigger_select_axes", target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load review-axis classifier: {target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_build_record(path: Path) -> dict[str, Any]:
    """Read the documentation-impact record ``/build`` saved from this script.

    The record is this script's own JSON output, so only the two fields the
    merge reads are required. Anything else raises ``ValueError``, because a
    record that cannot be read must never look like a record that said skip.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read build record {path}: {exc}") from exc
    effects = data.get("effects") if isinstance(data, dict) else None
    decision = data.get("decision") if isinstance(data, dict) else None
    if decision not in _DECISIONS or not isinstance(effects, list):
        raise ValueError(f"build record {path} needs a decision and an effects list")
    if not all(isinstance(effect, str) for effect in effects):
        raise ValueError(f"build record {path} holds a non-string effect")
    return {"decision": decision, "effects": effects}


def _is_test_only(segments: list[str], categories: Sequence[str]) -> bool:
    """A test or fixture file, not merely a name the test predicate matches.

    The review classifier also matches a ``test.`` filename prefix, which catches
    ``templates/skills/test.SKILL.md.tmpl``, the edit source of the ``/test``
    skill itself. Require a tests or fixtures directory.
    """
    return "tests-or-fixtures" in categories and bool(_TEST_DIRECTORIES & set(segments[:-1]))


def _is_historical(segments: list[str]) -> bool:
    name = segments[-1]
    if name in _HISTORICAL_NAMES or _DATED_NAME.match(name):
        return True
    return bool(_HISTORICAL_DIRECTORIES & set(segments[:-1]))


def _document_kind(path: str, segments: list[str], classifier: ModuleType) -> str:
    if _is_historical(segments):
        return "historical"
    if classifier.unreviewable_paths([path]):
        return "unreadable"
    return "document"


def classify_path(path: str, classifier: ModuleType) -> str:
    """Return the path kind documented in the module docstring."""
    segments = _segments(path)
    categories, unclassified = classifier.classify_paths([path])
    if unclassified:
        return "unclassified"
    if _is_test_only(segments, categories):
        return "test"
    if "docs-and-instructions" in categories:
        return _document_kind(path, segments, classifier)
    if "agent-artifacts" in categories:
        return "agent-artifact"
    if "types-or-public-api" in categories:
        return "api"
    return "code"


def _classify_all(changed_paths: Sequence[str], classifier: ModuleType) -> dict[str, list[str]]:
    by_kind: dict[str, list[str]] = {}
    for raw in changed_paths:
        if _segments(raw):
            by_kind.setdefault(classify_path(raw, classifier), []).append(raw)
    return by_kind


def _causes(
    by_kind: dict[str, list[str]],
    effects: list[str],
    unknown: list[str],
    build_activated: bool = False,
) -> list[str]:
    causes: list[str] = []
    if build_activated:
        causes.append("build record: /build recorded documentation impact")
    if unknown:
        causes.append("fail-closed: unknown effect " + ", ".join(unknown))
    if not by_kind:
        causes.append("fail-closed: no changed paths supplied")
    if by_kind.get("unclassified"):
        unplaced = ", ".join(by_kind["unclassified"])
        causes.append("fail-closed: not provably claim-neutral: " + unplaced)
    for kind, label in (
        ("document", "changed document"),
        ("unreadable", "document the scanner cannot read"),
        ("agent-artifact", "agent artifact"),
        ("api", "public API surface"),
    ):
        if by_kind.get(kind):
            causes.append(f"{label}: " + ", ".join(by_kind[kind]))
    causes.extend(f"effect: {effect}" for effect in effects)
    return causes


def _needs_coupled_lookup(
    by_kind: dict[str, list[str]], effects: list[str], unknown: list[str]
) -> bool:
    """True when a cause other than a scannable changed document is present.

    A changed document is scanned directly. Any other cause (a verified effect,
    an unknown effect, an unreadable or unclassified path, an agent artifact, a
    public API, or no paths) can leave a document stale that the diff never
    touched, so the coupled-document lookup must run beside the changed ones.
    """
    if effects or unknown or not by_kind:
        return True
    return any(
        by_kind.get(kind) for kind in ("unclassified", "unreadable", "agent-artifact", "api")
    )


def _escalation(activate: bool, by_kind: dict[str, list[str]], effects: list[str]) -> str:
    if not activate:
        return ESCALATION_NONE
    if by_kind.get("api") or REQUIRED_ESCALATION & set(effects):
        return ESCALATION_REQUIRED
    return ESCALATION_ON_FINDINGS


def _skip_reason(by_kind: dict[str, list[str]]) -> str:
    parts = [f"{path} ({_INTERNAL_WHY[kind]})" for kind, paths in by_kind.items() for path in paths]
    return "skip - no change can invalidate a durable claim: " + "; ".join(parts)


def decide(
    changed_paths: Sequence[str],
    effects: Sequence[str],
    diff_base: str,
    classifier: ModuleType,
    build_record: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Return the Gate 5 documentation-accuracy decision for one change."""
    by_kind = _classify_all(changed_paths, classifier)
    recorded: list[str] = list(build_record["effects"]) if build_record else []
    normalized = [effect.strip().lower() for effect in [*effects, *recorded]]
    known = [effect for effect in dict.fromkeys(normalized) if effect in EFFECTS]
    unknown = [effect for effect in dict.fromkeys(normalized) if effect not in EFFECTS]
    build_activated = build_record is not None and build_record["decision"] == "activate"
    causes = _causes(by_kind, known, unknown, build_activated)
    activate = bool(causes)
    documents = by_kind.get("document", [])
    return {
        "decision": "activate" if activate else "skip",
        "activate": activate,
        "reason": "activate - " + "; ".join(causes) if activate else _skip_reason(by_kind),
        "activation_causes": causes,
        "diff_base": diff_base,
        "effects": known,
        "build_record": (
            {"decision": build_record["decision"], "effects": recorded} if build_record else None
        ),
        "scope": f"incremental: {diff_base}...HEAD",
        "changed_documents": documents,
        "unreadable_documents": by_kind.get("unreadable", []),
        "historical_paths": by_kind.get("historical", []),
        "unknown_effects": unknown,
        "coupled_documents_needed": _needs_coupled_lookup(by_kind, known, unknown),
        "behavioral_escalation": _escalation(activate, by_kind, known),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--diff-base",
        required=True,
        metavar="REF",
        help="Base ref the scan is scoped to, for example origin/main. Blank is a config error.",
    )
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        metavar="PATH",
        help="A path from the verified three-dot diff. Repeatable.",
    )
    parser.add_argument(
        "--effect",
        action="append",
        default=[],
        metavar="NAME",
        help="A diff effect verified in the diff body. Known values: "
        + ", ".join(EFFECTS)
        + ". An unknown value fails closed.",
    )
    parser.add_argument(
        "--build-record",
        type=Path,
        default=None,
        metavar="PATH",
        help="The JSON this script printed for /build. Its effects join --effect values.",
    )
    parser.add_argument(
        "--classifier",
        type=Path,
        default=None,
        help="Path to the review skill's select_axes.py. Defaults to the sibling skill.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.diff_base.strip():
        print("doc_accuracy_trigger: --diff-base is blank", file=sys.stderr)
        return 2
    try:
        classifier = load_classifier(args.classifier)
    except (OSError, ImportError) as exc:
        print(f"doc_accuracy_trigger: {exc}", file=sys.stderr)
        return 2
    try:
        record = load_build_record(args.build_record) if args.build_record else None
    except ValueError as exc:
        print(f"doc_accuracy_trigger: {exc}", file=sys.stderr)
        return 2
    result = decide(args.changed_path, args.effect, args.diff_base.strip(), classifier, record)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
