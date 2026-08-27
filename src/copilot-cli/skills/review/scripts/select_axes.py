#!/usr/bin/env python3
"""Select Stage-2 review axes from verified changed paths and diff effects.

``/review`` runs a Stage-1 ``spec-compliance`` gate, then a set of Stage-2
axes.  Running all of them on every change costs review latency and adds
low-signal findings, so this script decides which axes a change actually
needs.  It is a pure function of its arguments: the same paths and effects
always produce the same selection, so the routing is testable instead of
being re-derived by a model on each run.

Two axis families exist and this script keeps them in separate output
fields, because they are loaded differently and conflating them misloads a
caller-pinned local axis:

* **Canonical axes** are discovered from ``references/*.md`` and dispatched
  with ``Task(subagent_type="{stem}")`` using ``references/{stem}.md`` as
  the system prompt.
* **Local-only skill axes** (``code-qualities-assessment``, ``doc-accuracy``,
  ``golden-principles``, ``taste-lints``) are sibling skills invoked with
  ``Skill(skill="{name}")``.  They have no ``references/{name}.md`` file, so
  a local axis that lands in the canonical list resolves to a prompt path
  that does not exist.

``spec-compliance`` is the Stage-1 gate.  It always runs and this script
never reports on it; it is excluded from the canonical candidate set.

Selection is additive: one change can match several risk categories and
every matched category contributes its axes.

Fail-closed rule: when a changed path matches no known risk category, when a
declared diff effect is not in the known vocabulary, or when a demanded axis
has no ``references/{stem}.md`` prompt to load, every candidate axis is
selected.  An unclassified change gets the full review, never an empty one,
and an incomplete prompt set widens the review instead of narrowing it.  A
demanded axis with no prompt is reported in ``unresolved_axes`` so it never
vanishes from both ``canonical_selected`` and ``skipped``.

EXIT CODES (ADR-035):
    0 - A selection was emitted on stdout as JSON.
    2 - Config error: an unknown pinned axis name, or the references
        directory could not be resolved.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

# The Stage-1 gate. Runs unconditionally; never a Stage-2 candidate.
STAGE1_AXIS = "spec-compliance"

# One general review always runs (issue #4981 acceptance criterion 2).
ALWAYS_ON_CANONICAL = ("analyst",)

# Sibling skills invoked with Skill(skill=...), not references/{stem}.md.
LOCAL_AXES = ("code-qualities-assessment", "doc-accuracy", "golden-principles", "taste-lints")

_CODE_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".cs", ".ps1", ".psm1", ".sh", ".go", ".rs", ".rb", ".java"}
)

_DEPENDENCY_MANIFESTS = frozenset(
    {
        "pyproject.toml", "uv.lock", "poetry.lock", "package.json", "package-lock.json",
        "pnpm-lock.yaml", "yarn.lock", "go.mod", "go.sum", "cargo.toml", "cargo.lock",
        "gemfile", "gemfile.lock", "directory.packages.props", "packages.lock.json",
    }
)

# Security words are matched against whole path words, never as bare
# substrings: "auth" inside "docs/authors.md" and "token" inside
# "src/tokenizer.py" both selected the security axis under substring matching,
# which is exactly the low-signal noise risk selection exists to remove.
_SECURITY_WORDS = frozenset(
    {
        "auth", "authn", "authz", "oauth", "secret", "secrets", "credential", "credentials",
        "password", "passwords", "token", "tokens", "permission", "permissions",
    }
)

# Genuinely prefix-shaped: every real spelling starts with these ("sanitize",
# "sanitizer", "sanitization"; "cryptography", "cryptographic").
_SECURITY_WORD_PREFIXES = ("sanitiz", "crypto")

# Directory-shaped and filename-shaped CI markers. The bare token "release"
# used to match "docs/release-notes.md"; a deploy or release surface is a
# directory or a workflow filename, so match those shapes instead.
_CI_PATH_TOKENS = (".github/workflows/", ".github/actions/")
_CI_DIRECTORIES = frozenset({"deploy", "release"})
_CI_FILENAMES = frozenset(
    {
        "dockerfile", "lefthook.yml", "lefthook.yaml", "release.yml", "release.yaml",
        "deploy.yml", "deploy.yaml",
    }
)
_CI_FILENAME_PREFIXES = ("dockerfile.", "docker-compose", "deploy.")
_CI_FILENAME_SUFFIXES = (".tf", ".tfvars")

# Word boundary inside one path segment: any run of non-alphanumeric bytes.
_WORD_SPLIT = re.compile(r"[^a-z0-9]+")

_TYPE_API_TOKENS = (
    ".d.ts", "types.py", "types.ts", "models.py", "schema.py", "schemas/",
    ".proto", "interfaces/", "protocols.py", "api.py", "api.ts",
)

_AGENT_ARTIFACT_TOKENS = ("skill.md", "/skills/", "/agents/", "/hooks/", "/prompts/", "/commands/")

_TOOLKIT_TOKENS = _AGENT_ARTIFACT_TOKENS + (".github/workflows/", ".github/actions/", "/rules/")


def _norm(path: str) -> str:
    """Normalize a changed path for matching: posix separators, lowercase."""
    return path.replace("\\", "/").strip().lower()


def _segments(path: str) -> list[str]:
    """Return the non-empty path segments of a normalized path."""
    return [segment for segment in path.split("/") if segment]


def _words(path: str) -> set[str]:
    """Split a normalized path into alphanumeric words.

    ``src/auth/session.py`` yields ``{src, auth, session, py}``; the word set
    is what security matching tests, so ``docs/authors.md`` (``authors``) and
    ``src/tokenizer.py`` (``tokenizer``) no longer match ``auth``/``token``.
    """
    return {word for segment in _segments(path) for word in _WORD_SPLIT.split(segment) if word}


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if "/tests/" in path or path.startswith("tests/") or "/fixtures/" in path:
        return True
    if name.startswith("test_") or name.startswith("test."):
        return True
    return name.endswith(("_test.py", ".tests.ps1", ".test.ts", ".spec.ts", ".test.js"))


def _is_security_path(path: str) -> bool:
    if path.rsplit("/", 1)[-1].startswith(".env") or ".env." in path:
        return True
    words = _words(path)
    if words & _SECURITY_WORDS:
        return True
    return any(word.startswith(_SECURITY_WORD_PREFIXES) for word in words)


def _is_dependency_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    if name in _DEPENDENCY_MANIFESTS or name.endswith(".csproj"):
        return True
    return name.startswith("requirements") and name.endswith(".txt")


def _is_ci_deploy_path(path: str) -> bool:
    if any(token in path for token in _CI_PATH_TOKENS):
        return True
    name = path.rsplit("/", 1)[-1]
    if name in _CI_FILENAMES or name.startswith(_CI_FILENAME_PREFIXES):
        return True
    if name.endswith(_CI_FILENAME_SUFFIXES):
        return True
    return bool(_CI_DIRECTORIES & set(_segments(path)[:-1]))


def _is_type_or_api_path(path: str) -> bool:
    return any(token in path for token in _TYPE_API_TOKENS)


def _is_agent_artifact_path(path: str) -> bool:
    return any(token in path for token in _AGENT_ARTIFACT_TOKENS)


def _is_toolkit_artifact_path(path: str) -> bool:
    return any(token in path for token in _TOOLKIT_TOKENS)


def _is_decision_doc_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name.startswith("adr-") or "/architecture/" in path or "/decisions/" in path


def _is_roadmap_doc_path(path: str) -> bool:
    return "/roadmap/" in path or "/planning/" in path or "/specs/" in path


def _is_docs_path(path: str) -> bool:
    return path.endswith((".md", ".mdx", ".rst", ".txt"))


def _is_code_path(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in _CODE_SUFFIXES)


# Ordered risk table. Each row is (category, predicate, canonical axes, local
# axes). Every row whose predicate matches contributes its axes, so a single
# path can select several axes and several paths accumulate.
_RISK_TABLE: tuple[tuple[str, Callable[[str], bool], tuple[str, ...], tuple[str, ...]], ...] = (
    ("tests-or-fixtures", _is_test_path, ("qa",), ()),
    ("auth-secrets-execution", _is_security_path, ("security",), ()),
    ("dependencies", _is_dependency_path, ("security", "devops"), ()),
    ("ci-deploy-artifacts", _is_ci_deploy_path, ("devops", "security"), ()),
    ("types-or-public-api", _is_type_or_api_path, ("architect",), ()),
    ("agent-artifacts", _is_agent_artifact_path, ("agent-safety",), ()),
    ("decision-records", _is_decision_doc_path, ("decision-rigor",), ()),
    ("roadmap-or-spec-docs", _is_roadmap_doc_path, ("roadmap",), ()),
    ("docs-and-instructions", _is_docs_path, (), ("doc-accuracy",)),
    (
        "executable-code",
        _is_code_path,
        ("code-quality",),
        ("code-qualities-assessment", "taste-lints"),
    ),
    ("toolkit-governance", _is_toolkit_artifact_path, (), ("golden-principles",)),
)

# Diff effects the caller verified in the diff body, which no path glob can
# see. An effect outside this vocabulary fails closed.
_EFFECT_TABLE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "error-handling": (("reliability", "qa"), ()),
    "type-change": (("architect",), ()),
    "public-api": (("architect",), ()),
    "integration-point": (("reliability",), ()),
    "new-code-path": (("observability",), ()),
    "dependency-change": (("security", "devops"), ()),
    "agent-behavior": (("agent-safety",), ()),
    "decision-record": (("decision-rigor",), ()),
    "comments-or-docstrings": (("code-quality",), ()),
}

_SKIP_REASON = "skipped - no changed path or diff effect matched this axis"
_FAIL_CLOSED_REASON = "selected - fail-closed: change could not be classified"
_UNRESOLVED_REASON = "selected - fail-closed: a demanded axis has no prompt to load"
_DEEP_REASON = "selected - deep review requested"
_ALWAYS_ON_REASON = "selected - always-on"
_PINNED_REASON = "selected - caller-pinned always-on"


def _blanket_reason(
    deep: bool,
    unclassified: Sequence[str],
    unknown_effects: Sequence[str],
    changed_paths: Sequence[str],
) -> str:
    """Return the reason recorded on every axis when the whole set runs."""
    if deep:
        return _DEEP_REASON
    if unclassified or unknown_effects or not changed_paths:
        return _FAIL_CLOSED_REASON
    return _UNRESOLVED_REASON


def discover_canonical_axes(references_dir: Path) -> list[str]:
    """Return the Stage-2 canonical axis stems found in *references_dir*.

    The directory is the source of truth: adding ``references/{stem}.md``
    enrolls an axis with no edit here. ``spec-compliance`` is the Stage-1
    gate and is excluded.
    """
    stems = sorted(p.stem for p in references_dir.glob("*.md"))
    return [stem for stem in stems if stem != STAGE1_AXIS]


def classify_paths(paths: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split *paths* into matched risk categories and unclassified paths."""
    categories: list[str] = []
    unclassified: list[str] = []
    for raw in paths:
        normalized = _norm(raw)
        if not normalized:
            continue
        matched = False
        for category, predicate, _canonical, _local in _RISK_TABLE:
            if predicate(normalized):
                matched = True
                if category not in categories:
                    categories.append(category)
        if not matched:
            unclassified.append(raw)
    return categories, unclassified


def _contributions(
    categories: Iterable[str], effects: Sequence[str]
) -> tuple[dict[str, list[str]], dict[str, list[str]], list[str]]:
    """Map each axis to the categories and effects that selected it."""
    canonical: dict[str, list[str]] = {}
    local: dict[str, list[str]] = {}
    unknown: list[str] = []

    def record(bucket: dict[str, list[str]], axes: Iterable[str], source: str) -> None:
        for axis in axes:
            bucket.setdefault(axis, []).append(source)

    wanted = set(categories)
    for category, _predicate, canonical_axes, local_axes in _RISK_TABLE:
        if category in wanted:
            record(canonical, canonical_axes, category)
            record(local, local_axes, category)

    for effect in effects:
        entry = _EFFECT_TABLE.get(_norm(effect))
        if entry is None:
            unknown.append(effect)
            continue
        record(canonical, entry[0], f"effect:{_norm(effect)}")
        record(local, entry[1], f"effect:{_norm(effect)}")

    return canonical, local, unknown


def select_axes(
    changed_paths: Sequence[str],
    canonical_candidates: Sequence[str],
    effects: Sequence[str] = (),
    pinned: Sequence[str] = (),
    deep: bool = False,
) -> dict[str, object]:
    """Return the axis selection for one change.

    ``canonical_candidates`` is the discovered Stage-2 set. ``pinned`` may
    name either a canonical or a local axis; each is routed to its own
    family so a pinned local axis is never loaded as a canonical prompt.
    """
    categories, unclassified = classify_paths(changed_paths)
    canonical_sources, local_sources, unknown_effects = _contributions(categories, effects)

    # A demanded canonical axis with no references/{stem}.md prompt cannot be
    # dispatched. Report it rather than dropping it from both output lists,
    # and widen the review instead of silently narrowing it.
    demanded = set(canonical_sources) | set(ALWAYS_ON_CANONICAL)
    unresolved_axes = sorted(demanded - set(canonical_candidates))

    fail_closed = (
        bool(unclassified)
        or bool(unknown_effects)
        or bool(unresolved_axes)
        or not changed_paths
    )
    reasons: dict[str, str] = {}

    if deep or fail_closed:
        blanket = _blanket_reason(deep, unclassified, unknown_effects, changed_paths)
        canonical_selected = set(canonical_candidates)
        local_selected = set(LOCAL_AXES)
        for axis in canonical_selected | local_selected:
            reasons[axis] = blanket
    else:
        # unresolved_axes is empty on this branch (a demanded axis with no
        # prompt fails closed above), so every demanded axis is a candidate.
        canonical_selected = set(canonical_sources)
        local_selected = set(local_sources) & set(LOCAL_AXES)
        for axis in canonical_selected:
            reasons[axis] = "selected - " + ", ".join(canonical_sources[axis])
        for axis in local_selected:
            reasons[axis] = "selected - " + ", ".join(local_sources[axis])
        for axis in ALWAYS_ON_CANONICAL:
            canonical_selected.add(axis)
            reasons[axis] = _ALWAYS_ON_REASON

    for axis in pinned:
        if axis in LOCAL_AXES:
            local_selected.add(axis)
        else:
            canonical_selected.add(axis)
        reasons[axis] = _PINNED_REASON

    skipped = {
        axis: _SKIP_REASON
        for axis in list(canonical_candidates) + list(LOCAL_AXES)
        if axis not in canonical_selected and axis not in local_selected
    }

    return {
        "mode": "deep" if deep else "risk",
        "stage1_axis": STAGE1_AXIS,
        "fail_closed": fail_closed and not deep,
        "matched_categories": categories,
        "unclassified_paths": unclassified,
        "unknown_effects": unknown_effects,
        "unresolved_axes": unresolved_axes,
        "canonical_selected": sorted(canonical_selected),
        "local_selected": sorted(local_selected),
        "selection_reasons": dict(sorted(reasons.items())),
        "skipped": dict(sorted(skipped.items())),
    }


def _default_references_dir() -> Path:
    """Resolve ``references/`` next to this script, in either layout.

    The script ships inside the skill directory, so its own location anchors
    the lookup in both the source project and a vendored plugin install.
    """
    return Path(__file__).resolve().parent.parent / "references"


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
        help=(
            "A diff effect verified in the diff body. Known values: "
            + ", ".join(sorted(_EFFECT_TABLE))
            + ". An unknown value fails closed."
        ),
    )
    parser.add_argument(
        "--pin",
        action="append",
        default=[],
        metavar="AXIS",
        help="A caller-pinned always-on axis, canonical or local. Repeatable.",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Deep review: select every candidate axis regardless of risk.",
    )
    parser.add_argument(
        "--references-dir",
        type=Path,
        default=None,
        help="Directory holding the canonical axis prompts (references/*.md).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    references_dir = args.references_dir or _default_references_dir()
    if not references_dir.is_dir():
        print(
            f"select_axes: references directory not found: {references_dir}",
            file=sys.stderr,
        )
        return 2

    candidates = discover_canonical_axes(references_dir)
    if not candidates:
        print(
            f"select_axes: no canonical axis prompts in {references_dir}",
            file=sys.stderr,
        )
        return 2

    known = set(candidates) | set(LOCAL_AXES)
    unknown_pins = [axis for axis in args.pin if axis not in known]
    if unknown_pins:
        print(
            "select_axes: unknown pinned axis: " + ", ".join(sorted(unknown_pins)),
            file=sys.stderr,
        )
        return 2

    result = select_axes(
        changed_paths=args.changed_path,
        canonical_candidates=candidates,
        effects=args.effect,
        pinned=args.pin,
        deep=args.deep,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
