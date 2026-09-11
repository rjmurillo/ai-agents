#!/usr/bin/env python3
# ruff: noqa: E402
"""Measure the repository's control-plane baseline (REQ-021, epic #5456).

Read-only CLI over seven dimensions: canonical, policy_owners,
always_loaded, generated_historical, gate_budget, activation,
accepted_tasks. An eighth, ``fanout_residue`` (worktree count on the
measuring machine), was dropped: it measured the laptop running the
script, not a property of the repository, so a rerun on a different
machine or a different day changed the number without the repository
changing at all (review F2). Never gates (DR1, measurement-only,
``.agents/specs/ontology/control-plane-subtraction-cohort-1.md`` O5): the
only nonzero exits are a dirty tree without ``--allow-dirty`` (1, ADR-035)
and a missing/non-git ``--repo`` (2). No metric value changes the exit code
(REQ-021 AC-08).

DR4 (reuse over duplication): the token estimator (``token_budget``), the
always-on glob matcher (``instruction_budget_globs``), the always-loaded base
file list (``validate_workspace_budget``), and the declared-budget config
loader and summation (``scripts.ci.lefthook_budget_model``) are imported,
not reimplemented.

AC-07: the three single-source dimensions (``gate_budget``,
``activation``, ``accepted_tasks``) return ``None`` with a logged reason
when their one data source is absent; the four multi-source dimensions
instead log one exclusion per missing subdirectory and keep counting the
rest.

Design note (2026-09-11 review): DESIGN-020 originally specified a
``dimensions/`` package of eight files with per-dimension dataclasses; both
were dropped for this one module returning plain ``dict[str, Any] | None``
per dimension (builder-ethos.md's lazy-ladder guidance against an
unrequested structural abstraction). Only ``Baseline``, the O4 aggregate
root, stays a dataclass. See DESIGN-020's Component Architecture section.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.ci.lefthook_budget_model import declared_budget, load_config
from scripts.validate_workspace_budget import WORKSPACE_FILES
from scripts.validation.instruction_budget_globs import is_language_universal, parse_applyto
from scripts.validation.token_budget import estimate_token_count

_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_HARNESS_BASE_FILES = {
    "claude_code": [f for f in WORKSPACE_FILES if f != ".github/copilot-instructions.md"],
    "copilot": [
        f for f in WORKSPACE_FILES if f in ("AGENTS.md", ".github/copilot-instructions.md")
    ],
    "codex": ["AGENTS.md"],
}
Exclusions = list[dict[str, str]]
Extractor = Callable[[str], set[str]]


class SymlinkRefusedError(Exception):
    """A caller-supplied output path resolves to a symlink (CWE-59)."""


@dataclass
class Baseline:
    """REQ-021's O4 aggregate root: the JSON/markdown pair as one unit."""

    commit_sha: str
    captured_at: str
    command: str
    dimensions: dict[str, Any]
    exclusions: list[dict[str, str]]
    release_targets: list[dict[str, str]]


def _exclude(exclusions: Exclusions, dim: str, reason: str) -> None:
    exclusions.append({"dimension": dim, "reason": reason})


def _count_glob(directory: Path, pattern: str) -> int:
    return len(list(directory.glob(pattern))) if directory.is_dir() else 0


def _count_bytes(path: Path, exclusions: Exclusions, dim: str) -> dict[str, int]:
    if not path.is_dir():
        _exclude(exclusions, dim, f"missing {path}")
        return {"count": 0, "bytes": 0}
    files = [p for p in path.rglob("*") if p.is_file()]
    return {"count": len(files), "bytes": sum(p.stat().st_size for p in files)}


def _frontmatter_paths(text: str) -> set[str]:
    """Extract the ``paths`` glob set from a Claude rule's frontmatter.

    Narrower than ``instruction_budget_globs.parse_applyto``, which resolves
    the Copilot-side ``applyTo`` key with a full comma-split, brace-aware
    parser. Claude rules use a different key, ``paths``, holding a plain
    YAML list (never comma-joined per entry), so this reads only that key.
    Patterns still feed the same ``is_language_universal`` matcher, so the
    matching logic stays shared (DR4); only extraction differs.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return set()
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return set()
    if not isinstance(data, dict):
        return set()
    raw = data.get("paths")
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {p for p in raw if isinstance(p, str)}
    return set()


def _always_on(directory: Path, pattern: str, extract: Extractor) -> list[Path] | None:
    if not directory.is_dir():
        return None
    out = []
    for path in sorted(directory.glob(pattern)):
        text = path.read_text(encoding="utf-8", errors="replace")
        if is_language_universal(extract(text), "py"):
            out.append(path)
    return out


def _always_on_rules(repo: Path, exclusions: Exclusions) -> list[Path]:
    rules = _always_on(repo / ".claude" / "rules", "*.md", _frontmatter_paths)
    if rules is None:
        _exclude(exclusions, "policy_owners.claude_rules", "missing .claude/rules")
        return []
    return rules


def _always_on_instructions(repo: Path, exclusions: Exclusions) -> list[Path]:
    files = _always_on(repo / ".github" / "instructions", "*.instructions.md", parse_applyto)
    if files is None:
        _exclude(exclusions, "policy_owners.github_instructions", "missing .github/instructions")
        return []
    return files


def _lefthook_config(repo: Path) -> dict[str, Any] | None:
    """Parse ``repo``'s ``lefthook.yml``, or ``None`` if absent or invalid.

    Delegates the read-and-parse step to the shared
    ``lefthook_budget_model.load_config`` (review F7) instead of
    reimplementing it; only the null-safety this script's AC-07 contract
    needs (a missing or malformed file degrades a dimension, it never
    raises) is new here.
    """
    path = repo / "lefthook.yml"
    try:
        return load_config(path)
    except (OSError, yaml.YAMLError, AssertionError):
        return None


def _job_names(jobs: list[Any], acc: list[str]) -> None:
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if "name" in job:
            acc.append(str(job["name"]))
        group = job.get("group")
        if isinstance(group, dict):
            _job_names(group.get("jobs", []), acc)


def _lefthook_jobs(repo: Path, exclusions: Exclusions) -> tuple[dict[str, int], int]:
    config = _lefthook_config(repo)
    if config is None:
        _exclude(exclusions, "canonical.lefthook_jobs", "missing or invalid lefthook.yml")
        return {}, 0
    by_hook: dict[str, int] = {}
    for hook_name, hook_cfg in config.items():
        if isinstance(hook_cfg, dict) and "jobs" in hook_cfg:
            names: list[str] = []
            _job_names(hook_cfg.get("jobs", []), names)
            by_hook[hook_name] = len(names)
    return by_hook, sum(by_hook.values())


def _claude_hooks(repo: Path, exclusions: Exclusions) -> tuple[dict[str, int], int]:
    settings = repo / ".claude" / "settings.json"
    by_event: dict[str, int] = {}
    if not settings.is_file():
        _exclude(exclusions, "canonical.hooks", f"missing {settings}")
    else:
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _exclude(exclusions, "canonical.hooks", f"invalid JSON: {exc}")
            data = {}
        for event, matchers in data.get("hooks", {}).items():
            by_event[event] = sum(len(m.get("hooks", [])) for m in matchers if isinstance(m, dict))
    hooks_dir = repo / ".claude" / "hooks"
    python_files = len(list(hooks_dir.rglob("*.py"))) if hooks_dir.is_dir() else 0
    return by_event, python_files


VALIDATOR_GLOBS = ("check_*.py", "checks_*.py", "validate_*.py")


def _validator_count(repo: Path) -> int:
    """Count validator scripts anywhere under ``scripts/``.

    Recursive (review F4): a depth-1 glob under ``scripts/`` missed
    validators nested under ``scripts/validation/`` and similar
    subdirectories. Excludes ``tests/`` and ``__pycache__/`` segments so a
    validator's own test fixtures or bytecode cache never count as a
    second validator.
    """
    scripts_dir = repo / "scripts"
    if not scripts_dir.is_dir():
        return 0
    count = 0
    for pattern in VALIDATOR_GLOBS:
        for path in scripts_dir.rglob(pattern):
            parts = path.relative_to(scripts_dir).parts
            if "tests" in parts or "__pycache__" in parts:
                continue
            count += 1
    return count


def _git_output(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, timeout=30, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def canonical(repo: Path, exclusions: Exclusions) -> dict[str, Any]:
    skills_dir = repo / ".claude" / "skills"
    skills = len(list(skills_dir.glob("*/SKILL.md"))) if skills_dir.is_dir() else 0
    hooks_by_event, hooks_python_files = _claude_hooks(repo, exclusions)
    lefthook_by_hook, lefthook_total = _lefthook_jobs(repo, exclusions)
    return {
        "agents": _count_glob(repo / ".claude" / "agents", "*.md"),
        "skills": skills,
        "rules": _count_glob(repo / ".claude" / "rules", "*.md"),
        "hooks_by_event": hooks_by_event,
        "hooks_python_files": hooks_python_files,
        "validators": _validator_count(repo),
        "workflows": _count_glob(repo / ".github" / "workflows", "*.yml"),
        "lefthook_jobs": lefthook_total,
        "lefthook_jobs_by_hook": lefthook_by_hook,
    }


def policy_owners(repo: Path, exclusions: Exclusions) -> dict[str, Any]:
    serena_dir = repo / ".serena" / "memories"
    serena_memories = len(list(serena_dir.rglob("*.md"))) if serena_dir.is_dir() else 0
    if not serena_dir.is_dir():
        _exclude(exclusions, "policy_owners.serena_memories", f"missing {serena_dir}")
    claude_rules = _always_on_rules(repo, exclusions)
    copilot_rules = _always_on_instructions(repo, exclusions)
    github_instr = repo / ".github" / "instructions"
    copilot_cli_instr = repo / "src" / "copilot-cli" / "instructions"
    return {
        "rule_mirrors": {
            "github_instructions": _count_glob(github_instr, "*.instructions.md"),
            "copilot_cli_instructions": _count_glob(copilot_cli_instr, "*.instructions.md"),
        },
        "adrs": _count_glob(repo / ".agents" / "architecture", "ADR-*.md"),
        "governance_docs": _count_glob(repo / ".agents" / "governance", "*.md"),
        "serena_memories": serena_memories,
        "always_on": {
            "claude_rules": sorted(str(p.relative_to(repo)) for p in claude_rules),
            "github_instructions": sorted(str(p.relative_to(repo)) for p in copilot_rules),
        },
    }


def _measure_harness_load(
    repo: Path, paths: list[Path], harness: str, exclusions: Exclusions
) -> dict[str, Any]:
    total_bytes = total_tokens = 0
    files_listed: list[str] = []
    for p in paths:
        if not p.is_file():
            _exclude(exclusions, f"always_loaded.{harness}", f"missing {p}")
            continue
        content = p.read_text(encoding="utf-8", errors="replace")
        total_bytes += len(content.encode("utf-8"))
        total_tokens += estimate_token_count(content)
        files_listed.append(str(p.relative_to(repo)))
    return {"bytes": total_bytes, "tokens": total_tokens, "files": sorted(files_listed)}


def always_loaded(repo: Path, exclusions: Exclusions) -> dict[str, dict[str, Any]]:
    extra = {
        "claude_code": _always_on_rules(repo, exclusions),
        "copilot": _always_on_instructions(repo, exclusions),
        "codex": [],
    }
    return {
        harness: _measure_harness_load(
            repo, [repo / n for n in base] + extra[harness], harness, exclusions
        )
        for harness, base in _HARNESS_BASE_FILES.items()
    }


def generated_historical(repo: Path, exclusions: Exclusions) -> dict[str, Any]:
    gh = "generated_historical"
    return {
        "episodes": _count_bytes(
            repo / ".agents" / "memory" / "episodes", exclusions, f"{gh}.episodes"
        ),
        "sessions": _count_bytes(repo / ".agents" / "sessions", exclusions, f"{gh}.sessions"),
        "serena_memories": _count_bytes(
            repo / ".serena" / "memories", exclusions, f"{gh}.serena_memories"
        ),
        "archive": _count_bytes(repo / ".agents" / "archive", exclusions, f"{gh}.archive"),
        "eval_results": _count_bytes(
            repo / ".agents" / "eval-results", exclusions, f"{gh}.eval_results"
        ),
        "generated_projections": {
            "copilot_cli_src": _count_bytes(
                repo / "src" / "copilot-cli", exclusions, f"{gh}.copilot_cli_src"
            ),
            "github_instructions": _count_bytes(
                repo / ".github" / "instructions", exclusions, f"{gh}.github_instructions"
            ),
        },
    }


def gate_budget(repo: Path, exclusions: Exclusions) -> dict[str, Any] | None:
    """Declared worst-case seconds per hook, reusing ``declared_budget``.

    ``lefthook_budget_model.load_config`` hardcodes its own module's
    ``REPO_ROOT`` and cannot measure an arbitrary ``--repo`` (needed for this
    script's test fixtures), so this function reads ``lefthook.yml`` itself;
    that two-line read is not logic DR4 protects. The summation this must
    never diverge from (``test_lefthook_declared_budget.py``'s total,
    REQ-021 AC-06) is ``declared_budget`` itself, called here unmodified.
    """
    config = _lefthook_config(repo)
    if config is None:
        _exclude(exclusions, "gate_budget", "missing or invalid lefthook.yml")
        return None
    seconds_by_hook = {
        name: declared_budget(config, name)[0]
        for name, cfg in config.items()
        if isinstance(cfg, dict) and "jobs" in cfg
    }
    return {"seconds_by_hook": seconds_by_hook}


def _skill_referenced(name: str, text: str) -> bool:
    """True when ``name`` appears as a structured reference, not a bare word.

    Bare-word matching (the prior implementation, review F3) let ordinary
    prose such as "runtime test" count the `test` skill as referenced. A
    structured reference is a backticked name (`` `name` ``) or a
    slash-prefixed occurrence (``/name``, which also matches a
    ``skills/name`` path segment as a substring, since that segment
    contains ``/name`` literally). ``(?![\\w-])`` blocks a longer name
    from matching a shorter one's prefix (``/autoplan-x`` must not count
    as a reference to ``autoplan``).
    """
    escaped = re.escape(name)
    pattern = rf"`{escaped}`|/{escaped}(?![\w-])"
    return re.search(pattern, text) is not None


def activation(repo: Path, exclusions: Exclusions) -> dict[str, Any] | None:
    skills_dir = repo / ".claude" / "skills"
    if not skills_dir.is_dir():
        _exclude(exclusions, "activation", f"missing {skills_dir}")
        return None
    skill_names = sorted(p.parent.name for p in skills_dir.glob("*/SKILL.md"))
    sources = [
        repo / "AGENTS.md",
        repo / "CLAUDE.md",
        repo / ".claude" / "skills" / "autoplan" / "SKILL.md",
    ]
    text = "".join(p.read_text(encoding="utf-8", errors="replace") for p in sources if p.is_file())
    referenced = sorted(name for name in skill_names if _skill_referenced(name, text))
    tests_dir = repo / "tests" / "skills"
    tested = (
        sorted(
            p.name for p in tests_dir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))
        )
        if tests_dir.is_dir()
        else []
    )
    return {
        "referenced_count": len(referenced),
        "referenced_names": referenced,
        "tested_count": len(tested),
        "tested_names": tested,
    }


def accepted_tasks(repo: Path, exclusions: Exclusions) -> dict[str, int] | None:
    path = repo / "scripts" / "eval" / "examples" / "harness-capability-matrix.json"
    if not path.is_file():
        _exclude(exclusions, "accepted_tasks", f"missing {path}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _exclude(exclusions, "accepted_tasks", f"invalid JSON: {exc}")
        return None
    verified = unverified = other = 0
    for harness in data.get("harnesses", []):
        for cap in harness.get("capabilities", {}).values():
            status = cap.get("status") if isinstance(cap, dict) else None
            if status == "VERIFIED":
                verified += 1
            elif status == "UNVERIFIED":
                unverified += 1
            else:
                other += 1
    return {
        "verified": verified,
        "unverified": unverified,
        "other": other,
        "total": verified + unverified + other,
    }


def _canonical_owner_total(canonical: dict[str, Any]) -> int:
    """Sum the seven owner-count fields, per the Definitions note (review F5).

    Excludes ``hooks_python_files``: a Claude hook that is both a registered
    ``settings.json`` entry and a ``.py`` source file must count once, as
    the registered entry, not twice.
    """
    return int(
        canonical["agents"]
        + canonical["skills"]
        + canonical["rules"]
        + sum(canonical["hooks_by_event"].values())
        + canonical["validators"]
        + canonical["workflows"]
        + canonical["lefthook_jobs"]
    )


def _release_targets(dims: dict[str, Any]) -> list[dict[str, str]]:
    """Build the four v0.7.0 release targets from this run's own numbers.

    Rendered by ``write_markdown`` (review F1): a rerun no longer erases a
    hand-typed Release targets section, because there is no hand-typed
    section left to erase.
    """
    owner_total = _canonical_owner_total(dims["canonical"])
    targets = [
        {
            "metric": "canonical owner total",
            "target": f"strictly below {owner_total}",
            "direction": "decrease",
        },
    ]
    for harness in sorted(dims["always_loaded"]):
        tokens = dims["always_loaded"][harness]["tokens"]
        targets.append(
            {
                "metric": f"always_loaded.{harness}.tokens",
                "target": f"strictly below {tokens}",
                "direction": "decrease",
            }
        )
    gate_budget_dim = dims["gate_budget"]
    pre_push = gate_budget_dim["seconds_by_hook"].get("pre-push") if gate_budget_dim else None
    targets.append(
        {
            "metric": "gate_budget.seconds_by_hook.pre-push",
            "target": (
                f"must not rise above {pre_push} seconds"
                if pre_push is not None
                else "N/A (gate_budget unavailable this run)"
            ),
            "direction": "hold",
        }
    )
    targets.append(
        {
            "metric": "measured push duration (once real push samples exist)",
            "target": "must not exceed ADR-104's 300 second ceiling",
            "direction": "hold",
        }
    )
    return targets


def build_baseline(repo: Path, command: str) -> Baseline:
    exclusions: Exclusions = []
    dims: dict[str, Any] = {
        "canonical": canonical(repo, exclusions),
        "policy_owners": policy_owners(repo, exclusions),
        "always_loaded": always_loaded(repo, exclusions),
        "generated_historical": generated_historical(repo, exclusions),
        "gate_budget": gate_budget(repo, exclusions),
        "activation": activation(repo, exclusions),
        "accepted_tasks": accepted_tasks(repo, exclusions),
    }
    unique = list({(e["dimension"], e["reason"]): e for e in exclusions}.values())
    unique.sort(key=lambda e: (e["dimension"], e["reason"]))
    return Baseline(
        commit_sha=_git_output(repo, ["rev-parse", "HEAD"]),
        captured_at=datetime.now(UTC).isoformat(),
        command=command,
        dimensions=dims,
        exclusions=unique,
        release_targets=_release_targets(dims),
    )


def _safe_open(path: Path) -> int:
    """Open ``path`` for writing, refusing a symlink target (CWE-59, AC-10).

    Mirrors ``.claude/skills/spec/scripts/metrics_writer.py``'s
    ``Path.is_symlink()`` pre-check plus ``os.O_NOFOLLOW``-flagged open
    (closes the CWE-367 TOCTOU window where supported). Differs from that
    module: this writer truncates and replaces the target and takes no
    advisory lock (one baseline run has no concurrent writer).
    """
    if path.is_symlink():
        raise SymlinkRefusedError(f"refusing to write to symlink target: {path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_NOFOLLOW
    return os.open(path, flags, 0o644)


def write_json(baseline: Baseline, path: Path) -> None:
    fd = _safe_open(path)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(dataclasses.asdict(baseline), fh, indent=2, sort_keys=True)
        fh.write("\n")


_PRE_COHORT_NOTE = (
    "PR #5723 merged before this capture; the baseline is taken at "
    "53ffe92c2, the last main commit before that merge, so every v0.7.0 "
    "subtraction is measured against a pre-cohort tree."
)

_METHODOLOGY_EXCLUSIONS = [
    "Gate p50/p95: no sampler exists. gate_budget is the declared worst "
    "case from lefthook.yml, not a measured distribution. ADR-104 cites "
    "two single-push measurements as provisional evidence: 142.39s "
    "against 679s recorded for a comparable push on the same container "
    "class.",
    "Fan-out: routed to the harness per #5651; worktree residue is "
    "machine-local, not a repository property, so it is not measured "
    "(the fanout_residue dimension was removed for this reason).",
    "Activation: two static proxies (referenced-name matching in "
    "AGENTS.md/CLAUDE.md/the autoplan routing table, and "
    "tests/skills/<name>/ presence), not invocation telemetry.",
    "Accepted-task outcomes: accepted_tasks counts VERIFIED/UNVERIFIED "
    "cells in the harness-capability-matrix, not task outcomes. Per "
    "issue #5423 every cell is UNVERIFIED at authoring time; paid "
    "live-harness probes are unavailable.",
]

_DEFINITIONS = [
    "canonical owner total = agents + skills + rules + registered hook "
    "entries (canonical.hooks_by_event; canonical.hooks_python_files is "
    "excluded so a hook that is both a settings.json registration and a "
    "source file counts once) + validators + workflows + lefthook jobs.",
    "validators are counted by three globs, recursive under scripts/, "
    "excluding tests/ and __pycache__/ segments: "
    + ", ".join(f"`{glob}`" for glob in VALIDATOR_GLOBS)
    + ".",
    "activation.referenced_names matches a structured reference only: a "
    "backticked name, or a /name slash-prefixed occurrence (which also "
    "matches a skills/name path segment, since that segment contains "
    "/name as a substring). A bare word in prose does not count.",
]


def _flatten(value: object, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(value, dict):
        rows: list[tuple[str, str]] = []
        for key in sorted(value):
            rows.extend(_flatten(value[key], f"{prefix}{key}."))
        return rows
    label = prefix.rstrip(".")
    rendered = ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)
    return [(label, rendered or "(none)")]


def _dimension_table(name: str, value: object) -> list[str]:
    lines = [f"## {name}", ""]
    if value is None:
        return [*lines, "null", ""]
    lines += ["| key | value |", "|---|---|"]
    lines += [f"| {key} | {rendered} |" for key, rendered in _flatten(value)]
    lines.append("")
    return lines


def write_markdown(baseline: Baseline, path: Path) -> None:
    fd = _safe_open(path)
    lines = [
        "# Control-plane baseline",
        "",
        f"- Commit: `{baseline.commit_sha}`",
        f"- Captured at: `{baseline.captured_at}`",
        "",
        "## Measurement command",
        "",
        "```",
        baseline.command,
        "```",
        "",
        "Any clean checkout of `main` at the commit recorded above "
        "produces the same dimension values; `--repo` may point at any "
        "such checkout. The script itself lives on the branch that ran "
        "it, not necessarily on `main`.",
        "",
        _PRE_COHORT_NOTE,
        "",
        "## Definitions",
        "",
    ]
    lines += [f"- {definition}" for definition in _DEFINITIONS]
    lines.append("")
    for name in sorted(baseline.dimensions):
        lines += _dimension_table(name, baseline.dimensions[name])
    lines += ["## Exclusions", ""]
    if baseline.exclusions:
        lines += ["| dimension | reason |", "|---|---|"]
        lines += [f"| {exc['dimension']} | {exc['reason']} |" for exc in baseline.exclusions]
    else:
        lines.append("No per-dimension data was missing on this run.")
    lines.append("")
    lines += [f"- {note}" for note in _METHODOLOGY_EXCLUSIONS]
    lines.append("")
    lines += ["## Release targets for v0.7.0", ""]
    lines += ["| metric | target | direction |", "|---|---|---|"]
    lines += [
        f"| {t['metric']} | {t['target']} | {t['direction']} |" for t in baseline.release_targets
    ]
    lines.append("")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Measure the repository's control-plane baseline.")
    parser.add_argument("--repo", default=".", help="Path to the git repository to measure.")
    parser.add_argument("--json", help="Write the JSON report to this path.")
    parser.add_argument("--markdown", help="Write the markdown report to this path.")
    parser.add_argument(
        "--allow-dirty", action="store_true", help="Allow measuring a dirty working tree."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    args = _build_parser().parse_args(args_list)
    repo = Path(args.repo).resolve()
    if not repo.is_dir() or not (repo / ".git").exists():
        print(f"error: not a git repository: {repo}", file=sys.stderr)
        return 2
    try:
        dirty = _git_output(repo, ["status", "--porcelain"])
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if dirty and not args.allow_dirty:
        print("error: working tree is dirty; pass --allow-dirty or commit first", file=sys.stderr)
        return 1
    command = "scripts/metrics/control_plane_baseline.py " + " ".join(args_list)
    try:
        baseline = build_baseline(repo, command)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        if args.json:
            write_json(baseline, Path(args.json))
        if args.markdown:
            write_markdown(baseline, Path(args.markdown))
    except SymlinkRefusedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
