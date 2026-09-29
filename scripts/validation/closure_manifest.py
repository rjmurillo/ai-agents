#!/usr/bin/env python3
"""Emit the typed dependency closure of every pinned required context (ADR-101).

ADR-101, "What stays outside the loop", says the enforcement-bearing set must be
computed, not enumerated, "over every entrypoint named by a required context,
with one resolver per edge kind", emitted as a manifest and compared on every
run, with an unresolvable edge failing closed. Its Phase 0 exit condition adds
that CODEOWNERS must cover the manifest's file set exactly, "with any deliberate
exclusion named in the manifest". This tool is that computation.

Entrypoints are the jobs whose check-run name is a pinned context (the same
mapping the required-context lint uses), plus every job they depend on through
`needs:`. From each entrypoint five resolvers run (edge kinds in `closure_model`):

  1. module imports              via the completion gate's own static closure
                                 (`_expand_import_closure`), including the
                                 dynamic loads it resolves or halts on
  2. configuration-named paths   executable files a reached YAML, JSON or TOML
                                 file names in a string value
  3. action inputs               `with:` values that name a repository file
  4. workflow references         `run:` text, `uses:` local actions and reusable
                                 workflows, and pinned external actions
  5. runtime configuration       recorded values of `on`, `permissions`, `env`,
                                 `runs-on`, `defaults`, conditions and the rest

Files carry a content hash. Recorded values carry the value. Anything a resolver
cannot resolve is an `unresolved` entry and the tool exits 1: an omitted edge and a
verified one would otherwise look the same. What a P1 run cannot observe at all,
`core.hooksPath` and live ruleset state, is named under `unobservable`.

The import resolver is loaded from this tool's own tree, never from the tree being
measured, so pointing `--root` at a pull request's head reads that head as data. The
one command run inside the measured root is `git ls-files`, under a configuration with
no hook and no filesystem monitor; a tree with no `.git` directory, such as one
`verify_dispatch_closure.py` wrote, is walked instead and runs no git at all.

Scope, stated so a clean run is not read as more than it is. Resolution reads
tracked files only, so an untracked file is out of scope by the same decision the
completion gate records. A `run:` block that builds a path at run time
(`python "$SCRIPT"`) names no file this tool can see and adds no edge. This tool
is P0 code in the tree it measures, so its output is advisory until it runs from
the base ref; the `Dispatch closure` and scheduled workflows are that path.

EXIT CODES (ADR-035):
  0 - manifest emitted with no unresolved edge, or --advisory
  1 - unresolved edges, or a requested check failed (--against with --fail-on-change,
      --check-codeowners with uncovered files)
  2 - configuration: the workflows do not parse, git is unavailable, or a file
      given on the command line cannot be read
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import codeowners_coverage  # noqa: E402
from check_required_context_conditions import (  # noqa: E402
    WorkflowLoadError,
    load_workflows,
    producing_jobs,
)
from closure_model import (  # noqa: E402
    EDGE_IMPORT,
    EDGE_RUNTIME_CONFIG,
    EDGE_WORKFLOW_REF,
    Edge,
    Manifest,
    Unresolved,
    diff,
)
from closure_resolvers import (  # noqa: E402
    RepoTree,
    load_config,
    resolve_action_inputs,
    resolve_config_commands,
    resolve_tokens,
    resolve_uses,
)
from required_context_types import mapping  # noqa: E402

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS  # noqa: E402

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 2

_GATE = ".claude/skills/github/scripts/pr/run_completion_gate.py"
_SITE = re.compile(r"^(.*?):(\d+): (.*)$")

# Paths deliberately left without a CODEOWNERS entry, each with the reason. Empty
# on purpose: ADR-101 requires an exclusion to be named, so an unnamed gap fails.
CODEOWNERS_EXCLUSIONS: dict[str, str] = {}

# Repository-visible baselines of P2 state. They are hashed, not resolved.
_P2_ANCHORS = (
    ".github/CODEOWNERS",
    "scripts/validation/ruleset_params_baseline.json",
    "scripts/ci/ruleset_required_contexts.py",
)
_JOB_FIELDS = (
    "runs-on",
    "permissions",
    "env",
    "defaults",
    "timeout-minutes",
    "continue-on-error",
    "container",
    "services",
    "strategy",
    "environment",
    "concurrency",
    "if",
    "needs",
)
_STEP_FIELDS = ("if", "env", "shell", "working-directory", "continue-on-error", "timeout-minutes")
_WORKFLOW_FIELDS = ("on", "permissions", "env", "defaults", "concurrency")


_MAX_RECORDED_NODES = 2_000


def _plain(line: str) -> str:
    """ASCII with every control character escaped, so a name cannot start a log line."""
    ascii_line = line.encode("ascii", "backslashreplace").decode("ascii")
    return re.sub(r"[\x00-\x1f\x7f]", lambda m: f"\\x{ord(m.group()):02x}", ascii_line)


def _bounded(value: object) -> object:
    """A copy of ``value`` with at most `_MAX_RECORDED_NODES` nodes, else a marker.

    `yaml.safe_load` shares an aliased node instead of copying it, so serialising the
    result can expand a few kilobytes of YAML into gigabytes. Copy under a budget.
    """
    budget = [_MAX_RECORDED_NODES]

    def copy(node: object, depth: int) -> object:
        budget[0] -= 1
        if budget[0] < 0 or depth > 32:
            return "<truncated>"
        if isinstance(node, Mapping):
            return {str(k): copy(v, depth + 1) for k, v in node.items()}
        if isinstance(node, list):
            return [copy(v, depth + 1) for v in node]
        return node

    return copy(value, 0)


def _record(manifest: Manifest, key: str, value: object) -> None:
    manifest.recorded[key] = json.dumps(_bounded(value), sort_keys=True, default=str)[:4000]


def _job_chain(job_id: str, jobs: Mapping[str, Any]) -> list[str]:
    """``job_id`` and every job it depends on through `needs:`, in the same workflow."""
    order: list[str] = []
    pending = [job_id]
    while pending:
        current = pending.pop()
        body = jobs.get(current)
        if current in order or not isinstance(body, Mapping):
            continue
        order.append(current)
        needs = body.get("needs", [])
        pending.extend([needs] if isinstance(needs, str) else [str(n) for n in needs or []])
    return order


class _Walker:
    """Collects edges, recorded values and files while walking one closure."""

    def __init__(self, tree: RepoTree, manifest: Manifest) -> None:
        self.tree = tree
        self.manifest = manifest
        self.queue: list[str] = []
        # Entrypoint workflows, walked job by job along `needs:`. Re-reading the
        # whole file would pull in every unrelated job it also holds.
        self.walked: set[str] = set()

    def add_file(self, path: str) -> None:
        if path not in self.manifest.files:
            self.manifest.files[path] = self.tree.digest(path)
            self.queue.append(path)

    def add(self, edges: Sequence[Edge], unresolved: Sequence[Unresolved]) -> None:
        self.manifest.edges.update(edges)
        self.manifest.unresolved.update(unresolved)
        for edge in edges:
            self.add_file(edge.target)

    def walk_steps(self, steps: object, source: str) -> None:
        if not isinstance(steps, list):
            return
        for index, step in enumerate(steps):
            if isinstance(step, Mapping):
                self._walk_step(step, f"{source}:step[{index}]")

    def _walk_step(self, step: Mapping[str, Any], source: str) -> None:
        for field in _STEP_FIELDS:
            if field in step:
                _record(self.manifest, f"{source}:{field}", step[field])
        run = step.get("run")
        if isinstance(run, str):
            self.add(*resolve_tokens(run, source, EDGE_WORKFLOW_REF, self.tree))
        with_inputs = step.get("with")
        if isinstance(with_inputs, Mapping):
            self.add(*resolve_action_inputs(with_inputs, source, self.tree))
        uses = step.get("uses")
        if isinstance(uses, str):
            edges, pins, unresolved, follow = resolve_uses(uses, source, self.tree)
            self.manifest.recorded.update(pins)
            self.add(edges, unresolved)
            if follow is not None:
                self.add_file(follow)


def _walk_workflow_document(
    walker: _Walker, name: str, document: Mapping[str, Any], jobs: list[str]
) -> None:
    raw: Mapping[Any, Any] = document
    for field in _WORKFLOW_FIELDS:
        # YAML 1.1 reads a bare `on` key as the boolean True, so `on:` is filed
        # under True by `safe_load` and a lookup by name alone would miss the
        # trigger block, the one field that decides whether the workflow runs.
        key: Any = True if field == "on" and field not in raw and True in raw else field
        if key in raw:
            _record(walker.manifest, f"{name}:{field}", raw[key])
    job_map = mapping(document, "jobs")
    for job_id in jobs:
        body = job_map[job_id]
        for field in _JOB_FIELDS:
            if field in body:
                _record(walker.manifest, f"{name}:{job_id}:{field}", body[field])
        walker.walk_steps(body.get("steps"), f"{name}:{job_id}")
        uses = body.get("uses")
        if isinstance(uses, str):
            edges, pins, unresolved, follow = resolve_uses(uses, f"{name}:{job_id}", walker.tree)
            walker.manifest.recorded.update(pins)
            walker.add(edges, unresolved)
            if follow is not None:
                walker.add_file(follow)


def _process_queue(walker: _Walker, root: Path) -> list[str]:
    """Drain the file queue; return the Python files reached, for the import pass."""
    python_files: list[str] = []
    while walker.queue:
        path = walker.queue.pop()
        suffix = Path(path).suffix.lower()
        if suffix == ".py":
            python_files.append(path)
        elif suffix in {".sh", ".ps1"}:
            text = (root / path).read_text(encoding="utf-8", errors="replace")
            base_dir = str(Path(path).parent) if Path(path).parent != Path() else ""
            walker.add(*resolve_tokens(text, path, EDGE_WORKFLOW_REF, walker.tree, base_dir))
        elif suffix in {".yml", ".yaml", ".json", ".toml"}:
            _process_config(walker, root, path)
    return python_files


def _process_config(walker: _Walker, root: Path, path: str) -> None:
    """Read one reached YAML, JSON or TOML file as an action, a workflow or a config.

    An action or a workflow is walked for its steps, not scanned as configuration:
    its `run:` text names scripts by workflow reference (kind 4), and calling that
    a configuration-named path (kind 2) would misfile every script it runs.
    """
    if path in walker.walked:
        return
    document = load_config(root / path)
    if not isinstance(document, Mapping):
        if document is not None:
            walker.add(*resolve_config_commands(document, path, walker.tree))
        return
    runs = document.get("runs")
    jobs = document.get("jobs")
    if isinstance(runs, Mapping):
        walker.walk_steps(runs.get("steps"), path)
    elif isinstance(jobs, Mapping):
        _walk_workflow_document(walker, path, document, list(jobs))
    else:
        walker.add(*resolve_config_commands(document, path, walker.tree))


def _load_gate(gate_root: Path) -> ModuleType | None:
    """Load the import resolver from ``gate_root``, which must be the tool's own tree.

    Never the tree being measured: measuring a pull request's head would then
    execute the head's copy of the resolver, and a rewritten resolver could report
    any closure it liked. The measured tree is read as data only.
    """
    path = gate_root / _GATE
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("closure_manifest_gate", path)
    if (
        spec is None or spec.loader is None
    ):  # pragma: no cover - a fixed .py name always has a loader
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


def _resolve_imports(walker: _Walker, root: Path, python_files: list[str], gate_root: Path) -> None:
    if not python_files:
        return
    gate = _load_gate(gate_root)
    if gate is None:
        walker.manifest.unresolved.add(
            Unresolved(EDGE_IMPORT, "closure", f"import resolver {_GATE} is unavailable")
        )
        return
    seeds = sorted(python_files)
    closure = gate._expand_import_closure(seeds, root)
    for member in closure:
        if member not in seeds and walker.tree.has(member):
            walker.manifest.edges.add(Edge(EDGE_IMPORT, "closure", member))
            walker.add_file(member)
    for site in gate._unresolvable_dynamic_sites(closure, root):
        matched = _SITE.match(site)
        path, line, detail = matched.groups() if matched else (site, "?", "unresolvable load")
        walker.manifest.unresolved.add(Unresolved(EDGE_IMPORT, path, f"line {line}: {detail}"))


def build_manifest(root: Path, gate_root: Path | None = None) -> Manifest:
    """Compute the closure of every pinned required context under ``root``.

    ``gate_root`` is where the import resolver is loaded from and defaults to the
    tree this module lives in, so measuring a checkout never runs that checkout's
    code.
    """
    tree = RepoTree.from_root(root)
    manifest = Manifest()
    walker = _Walker(tree, manifest)
    documents = load_workflows(root / ".github" / "workflows")
    producers = producing_jobs(documents, REQUIRED_CONTEXTS)
    for context in sorted(set(REQUIRED_CONTEXTS) - {p.context for p in producers}):
        manifest.unresolved.add(
            Unresolved(EDGE_WORKFLOW_REF, context, "no job produces this pinned context")
        )
    for producer in producers:
        name = f".github/workflows/{producer.workflow}"
        manifest.entrypoints.add(f"{name}:{producer.job_id}")
        walker.add_file(name)
        walker.walked.add(name)
        document = documents[producer.workflow]
        jobs = document["jobs"]
        _walk_workflow_document(walker, name, document, _job_chain(producer.job_id, jobs))
    for anchor in _P2_ANCHORS:
        if tree.has(anchor):
            manifest.edges.add(Edge(EDGE_RUNTIME_CONFIG, "p2-anchor", anchor))
            walker.add_file(anchor)
    python_files = _process_queue(walker, root)
    _resolve_imports(walker, root, python_files, gate_root or _REPO_ROOT)
    _process_queue(walker, root)
    return manifest


def _load_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkflowLoadError(f"cannot read {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise WorkflowLoadError(f"{path} is not a manifest document")
    return loaded


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--root", type=Path, default=_REPO_ROOT, help="Checkout to measure.")
    parser.add_argument(
        "--gate-root",
        type=Path,
        default=None,
        help="Tree to load the import resolver from (default: this tool's own tree).",
    )
    parser.add_argument("--output", type=Path, help="Write the manifest JSON here.")
    parser.add_argument("--against", type=Path, help="A previous manifest JSON to compare with.")
    parser.add_argument(
        "--fail-on-change", action="store_true", help="Exit 1 when --against differs."
    )
    parser.add_argument(
        "--check-codeowners", action="store_true", help="Report files no CODEOWNERS entry owns."
    )
    parser.add_argument(
        "--advisory", action="store_true", help="Report, but exit 0 unless a config error."
    )
    return parser


def _report(manifest: Manifest, args: argparse.Namespace) -> int:
    failed = bool(manifest.unresolved)
    print(
        f"closure-manifest: {len(manifest.entrypoints)} entrypoints, {len(manifest.files)} files, "
        f"{len(manifest.edges)} edges, {len(manifest.recorded)} recorded values, "
        f"{len(manifest.unresolved)} unresolved"
    )
    for item in sorted(manifest.unresolved):
        print(_plain(f"closure-manifest: UNRESOLVED [{item.kind}] {item.source}: {item.detail}"))
    if args.against:
        changes = diff(_load_json(args.against), manifest.to_json())
        moved = {k: v for k, v in changes.items() if v}
        for key, values in moved.items():
            print(f"closure-manifest: {key}: {len(values)}")
        failed = failed or (args.fail_on_change and bool(moved))
    if args.check_codeowners:
        rules = codeowners_coverage.load(args.root / ".github" / "CODEOWNERS")
        uncovered, excluded = codeowners_coverage.coverage(
            manifest.files, rules, CODEOWNERS_EXCLUSIONS
        )
        print(
            f"closure-manifest: {len(uncovered)} of {len(manifest.files)} files have no "
            f"CODEOWNERS entry ({len(excluded)} deliberately excluded)"
        )
        for path in uncovered:
            print(_plain(f"closure-manifest: UNCOVERED {path}"))
        failed = failed or bool(uncovered)
    return EXIT_FAILED if failed and not args.advisory else EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = build_manifest(args.root, args.gate_root)
        if args.output:
            args.output.write_text(
                json.dumps(manifest.to_json(), indent=2) + "\n", encoding="utf-8"
            )
        return _report(manifest, args)
    except (
        WorkflowLoadError,
        RuntimeError,
        codeowners_coverage.UnsupportedPatternError,
        OSError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
