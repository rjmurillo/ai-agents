#!/usr/bin/env python3
"""Decide whether a change needs a developer-experience review (``/test`` Gate 5).

``/test`` Gate 5 composes the ``dx-review`` skill instead of carrying its own
DX checklist. A full DX audit on every change is noise, so this script decides
from verified changed paths and diff effects whether the change can alter a
developer-facing workflow. It is a pure function of its arguments, so the same
change always gets the same decision and the routing is testable.

Path classification reuses the ``/review`` risk-axis classifier from issue
#4981 (``classify_paths`` in the sibling ``review`` skill's
``scripts/select_axes.py``). Its risk categories are mapped onto developer
journeys here; this script adds only the journeys that classifier has no
category for (CLI entry points, install and onboarding files, contributor
tooling, plugin manifests). It never defines a second risk taxonomy.

Journeys (any match activates ``dx-review``):

- ``public-cli``: CLI commands, flags, output, errors, or help.
- ``public-api``: public APIs, types, or SDK entry points.
- ``install-onboarding``: install, setup, dependency, or first-run flow.
- ``harness-interface``: skills, agents, hooks, prompts, commands, plugin manifests.
- ``user-docs``: externally consumed documentation.
- ``contributor-workflow``: contributor guides and local developer tooling.

A skip is allowed only when every changed path is provably internal: tests or
fixtures, internal planning records, CI pipeline files, repository metadata,
or files under an internal-only root. A path that is neither a journey nor
provably internal fails closed and activates the review. So does an empty
path list and an unknown effect.

EXIT CODES (ADR-035):
    0 - A decision was emitted on stdout as JSON.
    2 - Config error: the review-axis classifier could not be loaded.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType

JOURNEYS = (
    "public-cli",
    "public-api",
    "install-onboarding",
    "harness-interface",
    "user-docs",
    "contributor-workflow",
)

# Diff effects the caller verified in the diff body. Each one activates the
# named journey even when no path shows it. public-api and agent-behavior
# reuse the /review effect names so a caller verifies each effect once.
EFFECTS: dict[str, str] = {
    "cli-surface": "public-cli",
    "public-api": "public-api",
    "onboarding-flow": "install-onboarding",
    "agent-behavior": "harness-interface",
    "user-task-docs": "user-docs",
    "contributor-workflow": "contributor-workflow",
}

# /review risk category -> developer journey it implies.
_CATEGORY_JOURNEYS: dict[str, str] = {
    "types-or-public-api": "public-api",
    "dependencies": "install-onboarding",
    "agent-artifacts": "harness-interface",
}

# /review risk categories that are internal for DX when no journey matched.
# decision-records is absent on purpose: it also covers any architecture/
# directory, and an architecture overview is read by outside developers. Only
# an ADR file or a decisions/ directory counts (see _is_decision_record).
_INTERNAL_CATEGORIES: dict[str, str] = {
    "roadmap-or-spec-docs": "internal planning record",
    "ci-deploy-artifacts": "CI or deploy pipeline file",
}

# Hidden top-level roots whose content never reaches a developer using the
# product, stored without the leading dot. These match segments of a
# caller-supplied changed path and resolve nothing on disk; spelling them with
# the dot reads to the vendor-portability ratchet as an upstream path (#2050).
_INTERNAL_ROOT_NAMES = frozenset({"agents", "project-toolkit", "serena"})
_METADATA_NAMES = frozenset({"codeowners", ".gitattributes", ".gitignore", ".mailmap"})

_CLI_DIRECTORIES = frozenset({"cli", "bin"})
_CLI_NAMES = frozenset({"__main__.py"})
_ONBOARDING_STEMS = frozenset(
    {
        "readme",
        "install",
        "installation",
        "setup",
        "quickstart",
        "getting-started",
        "getting_started",
        "onboarding",
    }
)
_ONBOARDING_DIRECTORIES = frozenset({".devcontainer", "getting-started"})
_CONTRIBUTOR_STEMS = frozenset(
    {
        "contributing",
        "pull_request_template",
        "lefthook",
        "makefile",
        "justfile",
        ".pre-commit-config",
        ".editorconfig",
    }
)
_CONTRIBUTOR_DIRECTORIES = frozenset({"issue_template"})
# A composite action's manifest is an interface other workflows call.
_CONTRIBUTOR_NAMES = frozenset({"action.yml", "action.yaml"})
_TEST_DIRECTORIES = frozenset({"tests", "fixtures"})
_HARNESS_NAMES = frozenset(
    {"plugin.json", "marketplace.json", "hooks.json", ".mcp.json", "mcp.json"}
)
_HARNESS_DIRECTORIES = frozenset({".claude-plugin"})

_CLASSIFIER_RELATIVE = Path("review") / "scripts" / "select_axes.py"


def _segments(path: str) -> list[str]:
    return [segment for segment in path.replace("\\", "/").strip().lower().split("/") if segment]


def _stem(name: str) -> str:
    """Name up to its first dot, keeping a leading dot: ``.pre-commit-config``."""
    if name.startswith("."):
        return "." + name[1:].split(".", 1)[0]
    return name.split(".", 1)[0]


def _is_cli(segments: list[str]) -> bool:
    name = segments[-1]
    if name in _CLI_NAMES or _CLI_DIRECTORIES & set(segments[:-1]):
        return True
    return "cli" in _stem(name).replace("_", "-").split("-")


def _is_onboarding(segments: list[str]) -> bool:
    return _stem(segments[-1]) in _ONBOARDING_STEMS or bool(
        _ONBOARDING_DIRECTORIES & set(segments[:-1])
    )


def _is_contributor(segments: list[str]) -> bool:
    if segments[-1] in _CONTRIBUTOR_NAMES or _stem(segments[-1]) in _CONTRIBUTOR_STEMS:
        return True
    return bool(_CONTRIBUTOR_DIRECTORIES & set(segments[:-1]))


def _is_harness(segments: list[str]) -> bool:
    return segments[-1] in _HARNESS_NAMES or bool(_HARNESS_DIRECTORIES & set(segments[:-1]))


_PATH_JOURNEYS: tuple[tuple[str, Callable[[list[str]], bool]], ...] = (
    ("public-cli", _is_cli),
    ("install-onboarding", _is_onboarding),
    ("contributor-workflow", _is_contributor),
    ("harness-interface", _is_harness),
)


def load_classifier(path: Path | None = None) -> ModuleType:
    """Load the sibling ``review`` skill's ``select_axes`` module.

    Both skills ship in the same ``skills/`` directory of every plugin root,
    so the sibling path resolves in the source tree and in a vendored install.
    """
    target = path or Path(__file__).resolve().parents[2] / _CLASSIFIER_RELATIVE
    if not target.is_file():
        raise FileNotFoundError(f"review-axis classifier not found: {target}")
    spec = importlib.util.spec_from_file_location("dx_trigger_select_axes", target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load review-axis classifier: {target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_decision_record(segments: list[str]) -> bool:
    return segments[-1].startswith("adr-") or "decisions" in segments[:-1]


def _is_test_only(segments: list[str], categories: Sequence[str]) -> bool:
    """A test or fixture file, not merely a name the test predicate matches.

    The review classifier also matches a ``test.`` filename prefix, which
    catches ``templates/skills/test.SKILL.md.tmpl``, the edit source of the
    ``/test`` skill itself. Require a tests or fixtures directory, or an
    executable test module, before calling a path test-only.
    """
    if "tests-or-fixtures" not in categories:
        return False
    return bool(_TEST_DIRECTORIES & set(segments[:-1])) or "executable-code" in categories


def _name_journeys(segments: list[str]) -> set[str]:
    return {journey for journey, predicate in _PATH_JOURNEYS if predicate(segments)}


def _journeys_for(segments: list[str], categories: Sequence[str]) -> list[str]:
    found = {_CATEGORY_JOURNEYS[c] for c in categories if c in _CATEGORY_JOURNEYS}
    found.update(_name_journeys(segments))
    planning = "roadmap-or-spec-docs" in categories or _is_decision_record(segments)
    if "docs-and-instructions" in categories and not planning:
        found.add("user-docs")
    return sorted(found, key=JOURNEYS.index)


def _internal_reason(segments: list[str], categories: Sequence[str]) -> str | None:
    if _is_decision_record(segments):
        return "internal planning record"
    for category in categories:
        if category in _INTERNAL_CATEGORIES:
            return _INTERNAL_CATEGORIES[category]
    if segments[-1] in _METADATA_NAMES:
        return "repository metadata"
    return None


def _is_internal_root_record(segments: list[str], categories: Sequence[str]) -> bool:
    """A non-code record under a hidden internal root.

    Code under such a root can be developer tooling in a host repository, and a
    README or contributor guide there is read by developers, so neither is
    provably internal.
    """
    root = segments[0]
    if not (root.startswith(".") and root[1:] in _INTERNAL_ROOT_NAMES):
        return False
    return "executable-code" not in categories and not _name_journeys(segments)


def classify_path(path: str, classifier: ModuleType) -> tuple[list[str], str | None]:
    """Return ``(journeys, internal_reason)`` for one changed path.

    Tests and internal-root records are checked first: a test under a
    ``skills/`` directory cannot change a developer workflow even though the
    review classifier also calls it an agent artifact.
    """
    segments = _segments(path)
    categories, _unclassified = classifier.classify_paths([path])
    if _is_test_only(segments, categories):
        return [], "test or fixture only"
    if _is_internal_root_record(segments, categories):
        return [], f"internal-only root {segments[0]}/"
    journeys = _journeys_for(segments, categories)
    if journeys:
        return journeys, None
    return [], _internal_reason(segments, categories)


def _decision_reason(
    journeys: list[str],
    internal_paths: dict[str, str],
    unclassified: list[str],
    unknown: list[str],
    any_path: bool,
) -> str:
    if unknown:
        return "activate - fail-closed: unknown effect " + ", ".join(unknown)
    if not any_path:
        return "activate - fail-closed: no changed paths supplied"
    if unclassified:
        return "activate - fail-closed: not provably internal: " + ", ".join(unclassified)
    if journeys:
        return "activate - developer journeys: " + ", ".join(journeys)
    return "skip - every changed path is provably internal: " + "; ".join(
        f"{path} ({why})" for path, why in internal_paths.items()
    )


def decide(
    changed_paths: Sequence[str], effects: Sequence[str], classifier: ModuleType
) -> dict[str, object]:
    """Return the Gate 5 activation decision for one change."""
    path_journeys: dict[str, list[str]] = {}
    internal_paths: dict[str, str] = {}
    unclassified: list[str] = []
    for raw in changed_paths:
        if not _segments(raw):
            continue
        journeys, internal = classify_path(raw, classifier)
        if journeys:
            path_journeys[raw] = journeys
        elif internal:
            internal_paths[raw] = internal
        else:
            unclassified.append(raw)

    active = {journey for journeys in path_journeys.values() for journey in journeys}
    unknown = [effect for effect in effects if effect.strip().lower() not in EFFECTS]
    active.update(EFFECTS[e.strip().lower()] for e in effects if e.strip().lower() in EFFECTS)
    any_path = bool(path_journeys or internal_paths or unclassified)
    fail_closed = bool(unknown or unclassified) or not any_path
    activate = fail_closed or bool(active)
    ordered = sorted(active, key=JOURNEYS.index)
    return {
        "journeys": ordered,
        "path_journeys": path_journeys,
        "internal_paths": internal_paths,
        "unclassified_paths": unclassified,
        "unknown_effects": unknown,
        "fail_closed": fail_closed,
        "activate": activate,
        "decision": "activate" if activate else "skip",
        "reason": _decision_reason(ordered, internal_paths, unclassified, unknown, any_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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
        + ", ".join(sorted(EFFECTS))
        + ". An unknown value fails closed.",
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
    try:
        classifier = load_classifier(args.classifier)
    except (OSError, ImportError) as exc:
        print(f"dx_trigger: {exc}", file=sys.stderr)
        return 2
    result = decide(args.changed_path, args.effect, classifier)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
