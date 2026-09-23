#!/usr/bin/env python3
"""Gate: behavior-driving artifacts compose a capability DAG, not a policy mesh.

Skills, agents, and rules declare what they own and what they consume in a
`capability` block nested under the `metadata` frontmatter key their templates
already support:

    metadata:
      capability:
        kind: reusable-primitive
        owns: [untrusted-content-handling]
        depends-on: [project-convention-discovery]
        status: active

ADR-110 owns the contract. The short version of why the declaration lives in
the artifact rather than in a manifest: a manifest is a second source of truth
that drifts on rename, and epic #5456 lists a new registry as an abort
condition for the v0.7.0 subtraction release.

Six invariants are blocking:

  1. one canonical owner per capability name
  2. every `depends-on` name resolves to some node's `owns` entry
  3. no node depends on a capability it owns
  4. the edge set is acyclic
  5. no projection owns a capability no canonical artifact owns
  6. `status: deprecated` requires `replaced-by`

A seventh blocks the one copied-policy class that can be proven rather than
guessed: a consumer that declares a dependency and then repeats three or more
consecutive lines of the owner's text. Issue #5396 calls this the "repeated
large normative blocks" case. Smaller overlaps are left alone on purpose,
because a consumer is expected to keep a one-line statement of the invariant
inline for harnesses that never load the owning rule.

A file with no `capability` block is not a node and is not a defect. Adoption
is incremental by design, so this gate never blocks a file for staying out of
the graph.

Exit codes (ADR-035):
    0 - Success (every declaration resolves, the graph is acyclic)
    1 - Logic error (an invariant is violated, or frontmatter cannot be parsed)
    2 - Config error (invalid repository root, or a canonical tree that holds
        no artifacts, which would make a PASS vacuous)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import yaml  # noqa: E402
from instruction_budget_globs import (  # noqa: E402
    _FRONTMATTER_RE,
    UnsupportedApplyToError,
    _UniqueKeySafeLoader,
)

CANONICAL_GLOBS: tuple[tuple[str, str], ...] = (
    ("templates/skills", "*.SKILL.md.tmpl"),
    ("templates/agents", "*.md"),
    ("templates/rules", "*.md"),
)

# The per-harness agent templates render beside the shared body, so a block
# declared in one of them would be invisible to the other harness and could
# double-declare an owner. One declaration site per agent: the shared file.
AGENT_HARNESS_GLOBS: tuple[tuple[str, str], ...] = (
    ("templates/agents", "*.claude.md.tmpl"),
    ("templates/agents", "*.copilot.md.tmpl"),
)

PROJECTION_GLOBS: tuple[tuple[str, str], ...] = (
    (".claude/skills", "*/SKILL.md"),
    (".claude/agents", "*.md"),
    (".claude/rules", "*.md"),
    ("src/claude/skills", "*/SKILL.md"),
    ("src/claude/agents", "*.md"),
    ("src/claude/rules", "*.md"),
    ("src/copilot-cli/skills", "*/SKILL.md"),
    ("src/copilot-cli/agents", "*.md"),
    ("src/copilot-cli/instructions", "*.md"),
    (".github/instructions", "*.instructions.md"),
    (".github/agents", "*.agent.md"),
    ("src/vs-code-agents", "*.agent.md"),
)

PROJECTION_PREFIXES: tuple[str, ...] = tuple(f"{subdir}/" for subdir, _ in PROJECTION_GLOBS)

KINDS: tuple[str, ...] = (
    "orchestrator",
    "specialized-implementation",
    "reusable-primitive",
    "cross-cutting-rule",
)

STATUSES: tuple[str, ...] = ("active", "sunset", "deprecated", "retired")

BLOCK_KEYS: tuple[str, ...] = (
    "kind",
    "owns",
    "depends-on",
    "status",
    "replaced-by",
    "replacement-platform",
    "replacement-owner",
    "validation",
)

NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")

# Three consecutive shared lines is the smallest run that cannot be a coincidence
# of shared vocabulary and is still small enough to catch a copied paragraph.
MIN_COPIED_RUN = 3
MIN_COPIED_CHARS = 120


class TreeError(Exception):
    """A canonical tree cannot answer the question this gate asks."""


@dataclass(frozen=True)
class Node:
    """One artifact carrying a capability block."""

    path: str
    canonical: bool
    kind: str
    owns: tuple[str, ...]
    depends_on: tuple[str, ...]
    status: str
    replaced_by: str | None
    replacement_platform: str | None
    replacement_owner: str | None
    validation: str | None
    body: str = field(compare=False, default="")

    def replacement(self) -> str:
        """Return the replacement status one line of report can carry."""
        if self.replaced_by:
            return self.replaced_by
        if self.replacement_platform and self.replacement_owner:
            return f"{self.replacement_platform} ({self.replacement_owner})"
        return "none"


def _frontmatter(text: str) -> dict[str, object]:
    """Parse frontmatter, rejecting duplicate top-level keys.

    Reuses the loader `check_rule_scope_keys.py` uses, for the same reason:
    PyYAML keeps the last value when a key repeats, and nothing guarantees a
    harness resolves the duplicate the same way.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return {}
    data = yaml.load(match.group(1), Loader=_UniqueKeySafeLoader)
    return data if isinstance(data, dict) else {}


def _optional(block: dict[str, object], key: str) -> str | None:
    """Return a string field, or None when it is absent or empty."""
    value = block.get(key)
    return str(value) if value else None


def _names(value: object) -> tuple[str, ...]:
    """Return an `owns` or `depends-on` value as a sorted tuple of names.

    Only the two shapes the schema allows survive: a bare string, and a list of
    strings. Anything else returns empty AND is reported by `_field_defect`, so
    a malformed declaration is never silently indistinguishable from an absent
    one. Splitting the report from the read keeps this function total for the
    callers that only need the names.
    """
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(entry, str) for entry in value):
        return tuple(sorted(value))
    return ()


def _field_defect(rel: str, field_name: str, value: object) -> str | None:
    """Return why an `owns` or `depends-on` value has the wrong shape."""
    if value is None:
        return None
    if isinstance(value, str):
        return None
    if not isinstance(value, list):
        return (
            f"{rel}: {field_name} is {type(value).__name__}, "
            "not a capability name or a list of them"
        )
    bad = [entry for entry in value if not isinstance(entry, str)]
    if bad:
        return f"{rel}: {field_name} holds a non-string entry: {bad[0]!r}"
    return None


def _has_replacement(block: dict[str, object]) -> bool:
    """Return True when a retiring capability names where its work goes next.

    Issue #5396's lifecycle checklist wants a replaceable capability to name the
    target platform and the upstream owner. An internal successor answers that
    with one capability name; an external one needs both halves, because a
    platform with no owner names nobody to ask.
    """
    if block.get("replaced-by"):
        return True
    return bool(block.get("replacement-platform")) and bool(block.get("replacement-owner"))


def _block_defects(rel: str, block: dict[str, object]) -> list[str]:
    """Return every shape defect in one capability block."""
    defects: list[str] = []
    if not block:
        return [f"{rel}: declares an empty `capability` block; declare a kind, or remove it"]
    unknown = sorted(key for key in block if key not in BLOCK_KEYS)
    if unknown:
        keys = ", ".join(f"`{key}`" for key in unknown)
        defects.append(f"{rel}: unknown capability key(s) {keys}")
    kind = block.get("kind")
    if kind is not None and kind not in KINDS:
        defects.append(f"{rel}: kind `{kind}` is not one of {', '.join(KINDS)}")
    status = block.get("status")
    if status is not None and status not in STATUSES:
        defects.append(f"{rel}: status `{status}` is not one of {', '.join(STATUSES)}")
    if status in ("sunset", "deprecated") and not _has_replacement(block):
        defects.append(
            f"{rel}: status `{status}` requires `replaced-by`, or both "
            "`replacement-platform` and `replacement-owner`"
        )
    for field_name in ("owns", "depends-on"):
        value = block.get(field_name)
        shape = _field_defect(rel, field_name, value)
        if shape:
            defects.append(shape)
            continue
        for name in _names(value):
            if not NAME_RE.match(name):
                defects.append(f"{rel}: {field_name} name `{name}` is not [a-z0-9-]{{1,64}}")
    return defects


def _candidate_files(repo_root: Path) -> list[Path]:
    """Return every file that may carry a capability block, canonical first."""
    files: list[Path] = []
    for subdir, pattern in CANONICAL_GLOBS:
        tree = repo_root / subdir
        if not tree.is_dir():
            raise TreeError(f"{subdir} is not a directory")
        found = sorted(tree.glob(pattern))
        if not found:
            raise TreeError(f"{subdir} holds no {pattern} files")
        files.extend(found)
    for subdir, pattern in PROJECTION_GLOBS:
        tree = repo_root / subdir
        if tree.is_dir():
            files.extend(sorted(tree.glob(pattern)))
    return files


def _is_canonical(rel: str) -> bool:
    """Return True when the path is an authored source rather than a projection."""
    return not rel.startswith(PROJECTION_PREFIXES)


def _has_capability_block(text: str) -> bool:
    """Return True when the frontmatter carries a `metadata.capability` mapping."""
    try:
        front = _frontmatter(text)
    except (UnsupportedApplyToError, yaml.YAMLError):
        return False
    metadata = front.get("metadata")
    return isinstance(metadata, dict) and isinstance(metadata.get("capability"), dict)


def _retired_key_defects(rel: str, metadata: dict[str, object]) -> list[str]:
    """Refuse the vocabulary `capability.kind` replaced.

    `metadata.type` carried nine unchecked values that no validator read. The
    capability block took its job, and a file that declares no capability block
    is not a node, so without this check the retired key could return in a new
    artifact and nothing would notice.
    """
    if "type" not in metadata:
        return []
    return [
        f"{rel}: declares the retired `metadata.type`; "
        "use `metadata.capability.kind` instead"
    ]


def _harness_template_defects(repo_root: Path) -> list[str]:
    """Refuse a capability block in a per-harness agent template.

    An agent has one shared body and two per-harness templates. A block in
    either template would declare the capability for one harness only, and a
    block in both would read as two owners of one capability. The shared file
    is the single declaration site.
    """
    defects: list[str] = []
    for subdir, pattern in AGENT_HARNESS_GLOBS:
        tree = repo_root / subdir
        if not tree.is_dir():
            continue
        for path in sorted(tree.glob(pattern)):
            text = path.read_text(encoding="utf-8", errors="replace")
            if _has_capability_block(text):
                rel = path.relative_to(repo_root).as_posix()
                stem = path.name.split(".")[0]
                defects.append(
                    f"{rel}: declares a capability block; declare it once in "
                    f"templates/agents/{stem}.shared.md instead"
                )
    return defects


def collect_nodes(repo_root: Path) -> tuple[list[Node], list[str]]:
    """Return every node carrying a capability block, plus shape defects.

    A parse failure is a defect, never a silently absent node: a syntax error
    would otherwise delete a node from the graph and turn a real edge into a
    clean run.
    """
    nodes: list[Node] = []
    defects: list[str] = _harness_template_defects(repo_root)
    for path in _candidate_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            front = _frontmatter(text)
        except (UnsupportedApplyToError, yaml.YAMLError) as exc:
            defects.append(f"{rel}: frontmatter cannot be parsed: {exc}")
            continue
        metadata = front.get("metadata")
        if not isinstance(metadata, dict):
            # An absent `metadata` key is an ordinary non-node, and so is a
            # bare `metadata:` with nothing under it, which YAML parses as
            # None: neither can hide a capability block. Any other non-mapping
            # value is malformed, and skipping it silently would drop the
            # artifact from the graph with no finding.
            if metadata is not None and _is_canonical(rel):
                defects.append(
                    f"{rel}: `metadata` is {type(metadata).__name__}, not a mapping"
                )
            continue
        if _is_canonical(rel):
            defects.extend(_retired_key_defects(rel, metadata))
        block = metadata.get("capability")
        if not isinstance(block, dict):
            continue
        defects.extend(_block_defects(rel, block))
        nodes.append(
            Node(
                path=rel,
                canonical=_is_canonical(rel),
                kind=str(block.get("kind", "")),
                owns=_names(block.get("owns")),
                depends_on=_names(block.get("depends-on")),
                status=str(block.get("status", "active")),
                replaced_by=_optional(block, "replaced-by"),
                replacement_platform=_optional(block, "replacement-platform"),
                replacement_owner=_optional(block, "replacement-owner"),
                validation=_optional(block, "validation"),
                body=text,
            )
        )
    return sorted(nodes, key=lambda node: node.path), defects


def build_owner_index(nodes: list[Node]) -> tuple[dict[str, Node], list[str]]:
    """Map capability name to its canonical owner, reporting duplicates.

    A projection that repeats its canonical owner's declaration is expected,
    not a defect: ADR-109 binplaces byte-identical copies of the template trees
    into `.claude/` and `src/claude/`, so a canonical declaration arrives in a
    projection by construction. The defect this catches is a projection that
    owns a capability no canonical artifact owns, which is what a hand-edited
    mirror inventing ownership looks like.
    """
    owners: dict[str, Node] = {}
    findings: list[str] = []
    for node in nodes:
        if not node.canonical:
            continue
        for name in node.owns:
            previous = owners.get(name)
            if previous is not None:
                findings.append(
                    f"capability `{name}` has two canonical owners: {previous.path} and {node.path}"
                )
                continue
            owners[name] = node
    for node in nodes:
        if node.canonical:
            continue
        for name in node.owns:
            if name not in owners:
                findings.append(
                    f"{node.path}: claims ownership of `{name}`, which no canonical "
                    "artifact under templates/ owns"
                )
    return owners, sorted(findings)


def _find_cycle(edges: dict[str, tuple[str, ...]]) -> list[str] | None:
    """Return one cycle in declaration order, or None when the graph is acyclic.

    Iterative depth-first search with an explicit stack, so a deep graph cannot
    exhaust the interpreter stack. Nodes are visited in sorted order, which is
    what makes the reported cycle stable across runs.
    """
    white, grey, black = 0, 1, 2
    colors = {name: white for name in edges}
    for root in sorted(edges):
        if colors[root] != white:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        trail: list[str] = []
        colors[root] = grey
        trail.append(root)
        while stack:
            name, index = stack.pop()
            successors = edges.get(name, ())
            if index >= len(successors):
                colors[name] = black
                if trail and trail[-1] == name:
                    trail.pop()
                continue
            stack.append((name, index + 1))
            nxt = successors[index]
            if colors.get(nxt, black) == grey:
                return trail[trail.index(nxt) :] + [nxt]
            if colors.get(nxt, black) == white:
                colors[nxt] = grey
                trail.append(nxt)
                stack.append((nxt, 0))
    return None


def _windows(text: str) -> set[tuple[str, ...]]:
    """Return every contiguous MIN_COPIED_RUN-line window in the text.

    Adjacency is the point. An earlier version collected the owner's lines into
    a set, which discarded their order: a consumer whose lines A, B, C each
    appeared somewhere in the owner matched even when the owner never held
    A, B, C together. Windows keep both sides contiguous, so only a real copied
    block matches.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        tuple(lines[index : index + MIN_COPIED_RUN])
        for index in range(len(lines) - MIN_COPIED_RUN + 1)
    }


def _shared_run(consumer: str, owner: str) -> bool:
    """Return True when the two texts share one contiguous block of lines."""
    owner_windows = _windows(owner)
    for window in _windows(consumer):
        if window in owner_windows and sum(len(line) for line in window) >= MIN_COPIED_CHARS:
            return True
    return False


def check_graph(nodes: list[Node], owners: dict[str, Node]) -> list[str]:
    """Return one finding per violated invariant, sorted for determinism."""
    findings: list[str] = []
    edges: dict[str, tuple[str, ...]] = {}
    for node in nodes:
        for name in node.depends_on:
            if name in node.owns:
                findings.append(f"{node.path}: depends on `{name}`, which it also owns")
                continue
            owner = owners.get(name)
            if owner is None:
                findings.append(f"{node.path}: depends on `{name}`, which no artifact owns")
                continue
            if node.canonical and _shared_run(node.body, owner.body):
                findings.append(
                    f"{node.path}: repeats a block of `{name}`, owned by {owner.path}; "
                    "keep the one-line invariant and drop the copied policy"
                )
        if node.status == "deprecated" and node.replaced_by:
            if node.replaced_by not in owners:
                findings.append(
                    f"{node.path}: `replaced-by: {node.replaced_by}` names no owned capability"
                )
        for name in node.owns:
            if owners.get(name) is node:
                edges[name] = tuple(
                    dep for dep in node.depends_on if dep in owners and dep not in node.owns
                )
    cycle = _find_cycle(edges)
    if cycle:
        findings.append("capability cycle: " + " -> ".join(cycle))
    return sorted(findings)


def render(nodes: list[Node], owners: dict[str, Node], fmt: str) -> str:
    """Emit the deterministic report. Two runs on one tree are byte-identical.

    Counts describe the canonical graph. A projection repeats its canonical
    source by construction, so counting it would multiply every node by the
    number of trees it binplaces into and report a graph nobody authored. The
    projection count is reported on its own line instead.
    """
    canonical = [node for node in nodes if node.canonical]
    projections = len(nodes) - len(canonical)
    kinds = {kind: 0 for kind in KINDS}
    for node in canonical:
        if node.kind in kinds:
            kinds[node.kind] += 1
    edges = sorted((node.path, name) for node in canonical for name in node.depends_on)
    if fmt == "json":
        payload = {
            "nodes": [
                {
                    "path": node.path,
                    "canonical": node.canonical,
                    "kind": node.kind,
                    "owns": list(node.owns),
                    "depends_on": list(node.depends_on),
                    "status": node.status,
                    "replacement": node.replacement(),
                    "validation": node.validation or "",
                }
                for node in nodes
            ],
            "owners": {name: owner.path for name, owner in sorted(owners.items())},
            "counts": {
                "nodes": len(canonical),
                "edges": len(edges),
                "projections": projections,
                "by_kind": kinds,
            },
        }
        return json.dumps(payload, indent=2, sort_keys=True)
    lines = [
        f"nodes: {len(canonical)}",
        f"edges: {len(edges)}",
        f"projections: {projections}",
    ]
    lines.extend(f"kind {kind}: {count}" for kind, count in sorted(kinds.items()))
    for name, owner in sorted(owners.items()):
        lines.append(
            f"owns {name}: {owner.path} status={owner.status} "
            f"replacement={owner.replacement()} validation={owner.validation or 'none'}"
        )
    lines.extend(f"edge {consumer} -> {name}" for consumer, name in edges)
    return "\n".join(lines)


def survey(repo_root: Path) -> tuple[list[Node], dict[str, Node], list[str]]:
    """Read the trees once and return the nodes, the owners, and every finding.

    One reader for both modes. Report mode used to render from its own shorter
    path, which skipped every check and exited zero over a broken graph.
    """
    nodes, defects = collect_nodes(repo_root)
    owners, owner_findings = build_owner_index(nodes)
    return nodes, owners, sorted(defects) + owner_findings + check_graph(nodes, owners)


def _report_findings(findings: list[str]) -> None:
    """Print findings to stderr in the gate's usual shape."""
    print(f"[FAIL] {len(findings)} capability graph violation(s):", file=sys.stderr)
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    print(
        "\nFix: declare the capability under `metadata.capability` in the owning "
        "artifact under templates/, and reference it with `depends-on` instead of "
        "restating its policy. Contract: "
        ".project-toolkit/architecture/ADR-110-capability-ownership-dag.md",
        file=sys.stderr,
    )


def validate_capability_graph(repo_root: Path) -> bool:
    """Return True when every declaration resolves and the graph is acyclic.

    Entry point matching the ``validate_*(repo_root) -> bool`` contract that
    ``pre_pr_sequence.py`` expects.
    """
    _nodes, _owners, findings = survey(repo_root)
    if not findings:
        return True
    _report_findings(findings)
    return False


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo_root", nargs="?", default=None)
    parser.add_argument("--report", choices=("text", "json"), default=None)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    repo_root = (
        Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    )
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    try:
        nodes, owners, findings = survey(repo_root)
    except TreeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    if args.report:
        # The report renders either way, because a reader debugging a broken
        # graph wants to see it. The exit code still reports the findings, so a
        # caller cannot read a rendered report as a clean run.
        print(render(nodes, owners, args.report))
    if findings:
        _report_findings(findings)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
