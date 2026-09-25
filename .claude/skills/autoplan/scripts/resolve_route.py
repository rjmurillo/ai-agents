#!/usr/bin/env python3
"""Deterministic long-tail route resolver for the autoplan skill (DESIGN-037).

The `autoplan` high-traffic table is prose a model reads; this script is the
fallback for a single-domain request that misses every table row. It never
repeats the table. The model reads the table first and runs this resolver
only on a miss (REQ-039 criterion 2).

    resolve_route.py --request TEXT [--skills-root PATH[=NAMESPACE] ...]

With no ``--skills-root``, the resolver reads the skills directory that holds
this script's own ``autoplan`` skill (two directories up from this file:
``scripts/`` -> ``autoplan/`` -> the skills root). Its namespace is the
nearest ancestor ``.claude-plugin/plugin.json`` ``name`` field above that
root, or ``local`` when no manifest exists. In this repository's own
development checkout that walk finds no manifest above ``.claude/skills``, so
the in-repo namespace is ``local``; the packaged plugin copy under
``src/claude/skills`` sits under ``src/claude/.claude-plugin/plugin.json``
(name ``project-toolkit``), which is why DESIGN-037's Identity table names
``project-toolkit:autoplan`` as the packaged-plugin identity and ``autoplan``
(no namespace, i.e. this repository's own ``local`` namespace) as the
in-repo one. Verified 2026-09-25 by reading
``src/claude/.claude-plugin/plugin.json`` (``"name": "project-toolkit"``) and
confirming no ``.claude-plugin/plugin.json`` exists above ``.claude/skills``
in this checkout.

Self-identification rule (this is the one implementation decision DESIGN-037
leaves to the resolver: it says only "the resolver identifies itself by
path, not by name"). This resolver reads the *first* root in its effective
root list -- the sole default root, or the first ``--skills-root`` argument
when the caller overrides the default -- as its home root. A skill named
``autoplan`` found in the home root's namespace is always the router itself,
regardless of what namespace label that root carries. An ``autoplan`` found
in any other, later root is a foreign skill like any other and is never
treated as self; it is reachable only by its own qualified name. This makes
self-detection a property of root order, not of a hard-coded namespace
string or the absolute path this file happens to run from, so a test can
construct the identical mixed-catalog fixture DESIGN-037 describes (a
``project-toolkit`` root passed first, a foreign ``gstack`` root passed
second) without needing to place anything at this script's own real
on-disk path.

Matching:

1. Lowercase the request, split into word tokens, drop stop words. Fold a
   trailing single ``s`` off both request tokens and intent tokens before
   comparing, so ``packages`` matches an intent word ``package`` but
   ``libraries`` does not match ``library`` -- verified against exactly the
   two examples DESIGN-037 gives (its "Matching" section, point 1): stripping
   a two-character ``es`` suffix instead would break the ``packages`` ->
   ``package`` match (removing the ``e`` that belongs to the stem), so this
   resolver strips only the final ``s`` character. That is a narrower, less
   linguistically complete rule than a real stemmer (it does not fold
   ``boxes`` to ``box``); it is deliberately narrow because REQ-039 asks for
   a deterministic, testable heuristic, not a stemmer, and Q6 defers scored
   recall improvements to the eval in issue #5389.
2. An intent matches when every one of its folded tokens appears in the
   folded request token set.
3. A skill's score is its count of matching intents. The tie-break is the
   total token count of those matching intents.

Order: explicit name/namespace reference (dropping a self-reference and
continuing) -> multi-domain marker -> highest-scoring eligible front-door
skill with `intents` -> `none`.

Output keys are sorted (`json.dumps(..., sort_keys=True)`) so two runs over
the same request and catalog produce byte-identical JSON (REQ-039 criterion
3). `kind` is one of `explicit`, `orchestrator`, `specialist`, `ambiguous`,
or `none`.

Failure modes (REQ-039 "Failure modes"):

- PyYAML absent: exit 2, naming the missing module.
- A `--skills-root` (or the default root) does not exist: exit 2.
- Bad arguments: argparse's own exit 2.

Exit codes: 0 for any resolution including `none`; 2 for a config or usage
error. This script opens no network connection, runs no subprocess, and
never executes skill content (REQ-039 "Security"): it only reads local
`SKILL.md` frontmatter and writes JSON to stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

__all__ = ["main", "resolve", "Root", "Skill"]

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_WORD_RE = re.compile(r"[a-z0-9]+")

# A short list of English function words dropped before token matching, so
# they never contribute to an intent match or a false positive.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "being", "but",
        "by", "can", "could", "do", "does", "did", "for", "from", "how",
        "i", "in", "is", "it", "its", "my", "of", "on", "or", "our",
        "please", "should", "that", "the", "their", "this", "to", "was",
        "we", "were", "what", "which", "who", "will", "with", "would",
        "you", "your",
    }
)

# Phrases that mean the request needs several agents or spans several
# domains at once (DESIGN-037 "Order", step 2). Checked as substrings of the
# lowercased request, not tokens, so hyphenated forms match as written.
_MULTI_DOMAIN_MARKERS: tuple[str, ...] = (
    "in parallel",
    "across services",
    "across teams",
    "across repositories",
    "across repos",
    "multi-agent",
    "multi agent",
    "multiple agents",
    "several agents",
    "cross-cutting",
    "cross cutting",
    "multi-domain",
    "multi domain",
)

# `/name`, `/namespace:name`, or "use the NAME skill" (DESIGN-037 "Order",
# step 1). The `(?<![\w/])` guard before a leading slash keeps a path
# fragment such as "src/foo" from being misread as an explicit reference:
# a real reference is preceded by whitespace or starts the string.
_EXPLICIT_RE = re.compile(
    r"(?<![\w/])/(?P<slash_ns>[A-Za-z][\w-]*):(?P<slash_ns_name>[A-Za-z][\w-]*)\b"
    r"|(?<![\w/])/(?P<slash_name>[A-Za-z][\w-]*)\b"
    r"|\buse the (?:(?P<use_ns>[A-Za-z][\w-]*):)?(?P<use_name>[A-Za-z][\w-]*) skill\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Root:
    """One catalog root: a directory of skill directories plus its namespace."""

    path: Path
    namespace: str


@dataclass(frozen=True)
class Skill:
    """One skill read from a root's `SKILL.md` frontmatter."""

    qualified_name: str
    name: str
    namespace: str
    role: str | None
    intents: tuple[str, ...]


def _fold(token: str) -> str:
    """Strip one trailing ``s`` from a token longer than three characters.

    See the module docstring's "Matching" section for why this strips only
    a single character rather than a two-character ``es`` suffix.
    """
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _tokenize(text: str) -> tuple[str, ...]:
    """Lowercase, split into words, drop stop words, and fold each token."""
    words = _WORD_RE.findall(text.lower())
    return tuple(_fold(word) for word in words if word not in _STOPWORDS)


def _default_namespace(root: Path) -> str:
    """Return the nearest ancestor plugin manifest's `name`, or `local`."""
    resolved = root.resolve()
    for candidate in (resolved, *resolved.parents):
        manifest = candidate / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "local"
        name = data.get("name") if isinstance(data, dict) else None
        return name.strip() if isinstance(name, str) and name.strip() else "local"
    return "local"


def _read_frontmatter(path: Path) -> dict[str, object]:
    """Best-effort YAML frontmatter parse. Returns `{}` on any defect.

    The resolver is not a validator: `check_skill_routing_roles.py` already
    refuses a malformed routing block before this script ever runs against a
    real catalog. A skill this resolver cannot parse simply contributes no
    role or intents, the same as a skill with an absent routing block.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        # Foreign plugin roots never pass the routing-role gate, so say which
        # skill dropped out instead of skipping it silently.
        reason = exc.__class__.__name__
        print(f"warning: skipped {path}: unparseable frontmatter ({reason})", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def _load_catalog(roots: list[Root]) -> list[Skill]:
    """Read every skill's name, role, and intents from each root in order."""
    catalog: list[Skill] = []
    for root in roots:
        if not root.path.is_dir():
            continue
        for skill_dir in sorted(p for p in root.path.iterdir() if p.is_dir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            front = _read_frontmatter(skill_md)
            raw_name = front.get("name")
            name = raw_name if isinstance(raw_name, str) and raw_name.strip() else skill_dir.name
            metadata = front.get("metadata")
            routing = metadata.get("routing") if isinstance(metadata, dict) else None
            routing = routing if isinstance(routing, dict) else {}
            role = routing.get("role")
            role = role if isinstance(role, str) else None
            raw_intents = routing.get("intents")
            intents = (
                tuple(item for item in raw_intents if isinstance(item, str) and item.strip())
                if isinstance(raw_intents, list)
                else ()
            )
            catalog.append(
                Skill(
                    qualified_name=f"{root.namespace}:{name}",
                    name=name,
                    namespace=root.namespace,
                    role=role,
                    intents=intents,
                )
            )
    return catalog


def _explicit_candidates(catalog: list[Skill], namespace: str | None, name: str) -> list[Skill]:
    """Return every catalog skill matching a parsed explicit reference."""
    name = name.lower()
    if namespace is not None:
        namespace = namespace.lower()
        return [s for s in catalog if s.namespace == namespace and s.name.lower() == name]
    return [s for s in catalog if s.name.lower() == name]


def _resolve_one_reference(
    namespace: str | None,
    name: str,
    catalog: list[Skill],
    home_namespace: str,
    home_qualified: str,
    notes: list[str],
) -> dict[str, object] | None:
    """Resolve one parsed `/name` or `/namespace:name` reference.

    Returns a finished result dict, or `None` when the reference was
    dropped (unknown, or the router naming itself) and scanning should
    continue on the rest of the request.
    """
    candidates = _explicit_candidates(catalog, namespace, name)
    if not candidates:
        label = f"{namespace}:{name}" if namespace else name
        notes.append(f"ignored unknown skill reference `{label}`")
        return None
    chosen: Skill | None = None
    if len(candidates) == 1:
        chosen = candidates[0]
    else:
        home_matches = [c for c in candidates if c.namespace == home_namespace]
        if len(home_matches) == 1:
            chosen = home_matches[0]
        else:
            names = sorted(c.qualified_name for c in candidates)
            return {
                "kind": "ambiguous",
                "route": None,
                "candidates": names,
                "rationale": f"ambiguous skill name `{name}`: found in {', '.join(names)}",
            }
    if chosen.qualified_name == home_qualified:
        notes.append(f"dropped self-reference `{chosen.qualified_name}`")
        return None
    return {
        "kind": "explicit",
        "route": chosen.qualified_name,
        "candidates": [chosen.qualified_name],
        "rationale": f"explicit skill reference: {chosen.qualified_name}",
    }


def _resolve_explicit(
    request: str,
    catalog: list[Skill],
    home_namespace: str,
    home_qualified: str,
    notes: list[str],
) -> dict[str, object] | None:
    """Scan every explicit reference in order; return the first decisive one."""
    for match in _EXPLICIT_RE.finditer(request):
        if match.group("slash_ns"):
            namespace, name = match.group("slash_ns"), match.group("slash_ns_name")
        elif match.group("slash_name"):
            namespace, name = None, match.group("slash_name")
        else:
            namespace, name = match.group("use_ns"), match.group("use_name")
        result = _resolve_one_reference(namespace, name, catalog, home_namespace, home_qualified, notes)
        if result is not None:
            return result
    return None


def _find_multi_domain_marker(request: str) -> str | None:
    """Return the first multi-domain marker phrase found, or `None`."""
    lowered = request.lower()
    for marker in _MULTI_DOMAIN_MARKERS:
        if marker in lowered:
            return marker
    return None


def _resolve_specialist(request: str, catalog: list[Skill], home_qualified: str) -> dict[str, object]:
    """Score every eligible front-door skill and return the winner, a tie, or none."""
    request_tokens = frozenset(_tokenize(request))
    scored: list[tuple[int, int, Skill, list[str]]] = []
    for skill in catalog:
        if skill.role != "front-door" or not skill.intents or skill.qualified_name == home_qualified:
            continue
        matched = [
            intent
            for intent in skill.intents
            if (tokens := _tokenize(intent)) and all(t in request_tokens for t in tokens)
        ]
        if matched:
            tiebreak = sum(len(_tokenize(intent)) for intent in matched)
            scored.append((len(matched), tiebreak, skill, matched))
    if not scored:
        return {
            "kind": "none",
            "route": None,
            "candidates": [],
            "rationale": "no explicit reference, multi-domain marker, or intent match",
        }
    top = max((score, tiebreak) for score, tiebreak, _skill, _matched in scored)
    winners = [entry for entry in scored if (entry[0], entry[1]) == top]
    if len(winners) > 1:
        names = sorted(entry[2].qualified_name for entry in winners)
        return {
            "kind": "ambiguous",
            "route": None,
            "candidates": names,
            "rationale": f"ambiguous: tied specialists {', '.join(names)}",
        }
    _score, _tiebreak, skill, matched = winners[0]
    return {
        "kind": "specialist",
        "route": skill.qualified_name,
        "candidates": [skill.qualified_name],
        "rationale": f"matched intents: {', '.join(matched)}",
    }


def resolve(request: str, roots: list[Root]) -> dict[str, object]:
    """Resolve one request against a catalog built from `roots`, in order.

    `roots[0]` is the home root: the resolver's own identity is
    `<roots[0].namespace>:autoplan`, and that qualified name is dropped from
    every stage rather than ever returned (REQ-039 criterion 9).
    """
    catalog = _load_catalog(roots)
    home_namespace = roots[0].namespace
    home_qualified = f"{home_namespace}:autoplan"
    notes: list[str] = []

    result = _resolve_explicit(request, catalog, home_namespace, home_qualified, notes)
    if result is None:
        marker = _find_multi_domain_marker(request)
        if marker is not None:
            result = {
                "kind": "orchestrator",
                "route": "orchestrator",
                "candidates": ["orchestrator"],
                "rationale": f"multi-domain marker: {marker}",
            }
        else:
            result = _resolve_specialist(request, catalog, home_qualified)

    if notes:
        result = dict(result)
        result["rationale"] = "; ".join([*notes, str(result["rationale"])])
    return result


def _parse_skills_root(raw: str) -> tuple[Path, str | None]:
    """Split a `PATH[=NAMESPACE]` argument into its path and optional namespace."""
    if "=" in raw:
        path_str, namespace = raw.split("=", 1)
        return Path(path_str), namespace
    return Path(raw), None


def _build_roots(raw_roots: list[str] | None) -> list[Root] | None:
    """Build the effective root list, or `None` when one does not exist."""
    if raw_roots:
        roots: list[Root] = []
        for raw in raw_roots:
            path, namespace = _parse_skills_root(raw)
            if not path.is_dir():
                print(f"error: skills root does not exist: {path}", file=sys.stderr)
                return None
            resolved = path.resolve()
            roots.append(Root(path=resolved, namespace=namespace or _default_namespace(resolved)))
        return roots
    default_root = Path(__file__).resolve().parents[2]
    if not default_root.is_dir():
        print(f"error: skills root does not exist: {default_root}", file=sys.stderr)
        return None
    return [Root(path=default_root, namespace=_default_namespace(default_root))]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on any resolution, 2 on a config error."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--request", required=True)
    parser.add_argument(
        "--skills-root",
        action="append",
        default=None,
        metavar="PATH[=NAMESPACE]",
        help="repeatable; first occurrence is the resolver's home root",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if yaml is None:
        print(
            "error: missing required module: yaml (PyYAML). "
            "Read skill descriptions directly instead of running this resolver.",
            file=sys.stderr,
        )
        return 2

    roots = _build_roots(args.skills_root)
    if roots is None:
        return 2

    result = resolve(args.request, roots)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
