#!/usr/bin/env python3
"""Ratchet: natural-language artifacts are source code, so structural debt may not grow.

Rules, skills, and agents are executable artifacts written in English (issue
#5397). Two defects that code review already names in source code are measured
here for authored artifacts only:

  1. duplicate normative blocks: five or more consecutive normalized,
     non-trivial lines that two authored files share. This is duplicate code.
  2. derived cardinality claims: "the three filters" followed by four filters.
     This is duplicated mutable state.

The scan set is an allowlist of authored sources: every file the instruction byte
corpus classifies as authored (`instruction_bytes_corpus.canonical_paths`: templates,
per-harness agent templates, partials, governance, root AGENTS.md and CLAUDE.md),
hand-kept `.github/prompts/` files, skill references, and untemplated skills.
Generated projections are not in the allowlist, so one authored source with N
generated copies is the good shape and is never counted. The one projection that
shares a root with authored text, `.github/prompts/pr-quality-gate-*.md`, is
skipped by name.

The check is a ratchet over a committed baseline. Existing debt is allowed; a
new pair, a bigger overlap, or a new stale count fails. Shrinking debt also
fails until the baseline is updated, so a burn-down is locked in. The fix text
prefers deleting or consolidating a representation over syncing the copies.

Reused by reference, not reimplemented: the always-on byte ratchet
(`instruction_bytes.py --ci`) and the activation coverage ratchet
(`check_rule_activation_coverage.py`). Change amplification per owner uses the
capability graph survey from `check_capability_graph.py`.

Exit codes (ADR-035):
    0 - Success (debt is at or below the baseline, or the baseline was updated)
    1 - Logic error (debt grew, a baseline entry is stale, or growth was refused)
    2 - Config error (invalid root, an empty scan, or a missing/invalid baseline)
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
for _path in (_SCRIPT_DIR, _SCRIPT_DIR.parents[1]):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from check_capability_graph import TreeError, survey  # noqa: E402
from nl_cardinality import Fence, derived_count_claims, fence_step, simplify  # noqa: E402

BASELINE_PATH = "scripts/validation/nl_structural_debt_baseline.json"
MIN_BLOCK_LINES = 5
MIN_BLOCK_CHARS = 200
MIN_LINE_CHARS = 20
SKILL_ROOT = ".claude/skills"
# Authored text the byte corpus does not classify: hand-kept prompts. Everything else
# authored comes from `instruction_bytes_corpus.canonical_paths`, the one source of truth.
EXTRA_AUTHORED_GLOBS: tuple[tuple[str, str], ...] = ((".github/prompts", "*.md"),)
NL_SUFFIXES = (".md", ".tmpl", ".mustache")
# `.github/prompts/pr-quality-gate-*.md` is generated from the review skill's
# references (templates/platforms/binplace.yaml), so it is a projection.
GENERATED_PROMPT_PREFIX = "pr-quality-gate-"
_RULE_RE = re.compile(r"^[\s|:\-=*_#>]*$")


class ScanError(Exception):
    """The scan cannot answer the question, so a clean result would be vacuous."""


def _canonical_paths(repo_root: Path) -> list[str]:
    """Return the byte corpus's authored paths.

    Imported by name at call time: a static import pulls `instruction_budget_globs` under
    two module names (package and sibling form), which mypy rejects.
    """
    corpus = importlib.import_module("scripts.validation.instruction_bytes_corpus")
    paths: list[str] = corpus.canonical_paths(repo_root)
    return paths


class GraphViolationError(Exception):
    """The capability graph is invalid, so fan-out derived from it would mislead."""


def authored_files(repo_root: Path) -> list[Path]:
    """Return authored sources: the byte corpus set, hand-kept prompts, skill references."""
    files = [
        repo_root / rel
        for rel in _canonical_paths(repo_root)
        if rel.endswith(NL_SUFFIXES) and not Path(rel).name.startswith(GENERATED_PROMPT_PREFIX)
    ]
    for subdir, pattern in EXTRA_AUTHORED_GLOBS:
        files.extend(
            p
            for p in sorted((repo_root / subdir).glob(pattern))
            if not p.name.startswith(GENERATED_PROMPT_PREFIX)
        )
    skills = repo_root / SKILL_ROOT
    templated = {
        p.name.removesuffix(".SKILL.md.tmpl")
        for p in (repo_root / "templates/skills").glob("*.SKILL.md.tmpl")
    }
    if skills.is_dir():
        for skill in sorted(p for p in skills.iterdir() if p.is_dir()):
            files.extend(sorted((skill / "references").glob("*.md")))
            if skill.name not in templated and (skill / "SKILL.md").is_file():
                files.append(skill / "SKILL.md")
    return files


def _body_lines(text: str) -> list[str]:
    """Return normalized non-trivial lines outside frontmatter and code fences."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
        lines = lines[end + 1 :]
    kept: list[str] = []
    fence: Fence | None = None
    for line in lines:
        fence, is_fence_line = fence_step(line, fence)
        if is_fence_line:
            continue
        norm = " ".join(line.split()).lower()
        if (
            fence is not None
            or len(norm) < MIN_LINE_CHARS
            or _RULE_RE.match(norm)
            or norm.startswith("#")
        ):
            continue
        kept.append(norm)
    return kept


def duplicate_blocks(files: dict[str, str]) -> dict[str, int]:
    """Map `a|b` file pairs to the count of shared normative windows."""
    seen: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for rel, text in files.items():
        lines = _body_lines(text)
        for i in range(len(lines) - MIN_BLOCK_LINES + 1):
            window = tuple(lines[i : i + MIN_BLOCK_LINES])
            if sum(map(len, window)) >= MIN_BLOCK_CHARS:
                seen[window].add(rel)
    pairs: dict[str, int] = defaultdict(int)
    for owners in seen.values():
        ordered = sorted(owners)
        for i, first in enumerate(ordered):
            for second in ordered[i + 1 :]:
                pairs[f"{first}|{second}"] += 1
    return dict(sorted(pairs.items()))


def stale_counts(files: dict[str, str]) -> dict[str, str]:
    """Map `path::claim` keys to a simplification of each contradicted count."""
    found: dict[str, str] = {}
    for rel, text in files.items():
        for claim in derived_count_claims(text):
            found[f"{rel}::{claim.text}"] = simplify(claim.text)
    return dict(sorted(found.items()))


def measure(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Return the current debt: duplicate pairs and stale cardinality claims."""
    paths = authored_files(repo_root)
    if not paths:
        raise ScanError("no authored artifacts found; an empty scan would pass vacuously")
    files = {
        p.relative_to(repo_root).as_posix(): p.read_text(encoding="utf-8", errors="replace")
        for p in paths
    }
    return {"duplicate_blocks": duplicate_blocks(files), "cardinality": stale_counts(files)}


def _load_baseline(repo_root: Path) -> dict[str, dict[str, Any]]:
    path = repo_root / BASELINE_PATH
    if not path.is_file():
        raise ScanError(f"baseline missing: {BASELINE_PATH}; run with --update-baseline")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScanError(f"baseline is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"duplicate_blocks", "cardinality"}:
        raise ScanError("baseline must hold exactly `duplicate_blocks` and `cardinality`")
    if not all(isinstance(data[k], dict) for k in data):
        raise ScanError("baseline sections must be objects")
    counts = data["duplicate_blocks"].values()
    if not all(type(v) is int and v > 0 for v in counts):
        raise ScanError("baseline `duplicate_blocks` values must be positive integers")
    if not all(isinstance(v, str) for v in data["cardinality"].values()):
        raise ScanError("baseline `cardinality` values must be strings")
    return data


def compare(
    current: dict[str, dict[str, Any]], baseline: dict[str, dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """Return (growth, shrink) findings; growth always fails, shrink demands a baseline update."""
    growth: list[str] = []
    shrink: list[str] = []
    for key, count in current["duplicate_blocks"].items():
        allowed = baseline["duplicate_blocks"].get(key, 0)
        if count > allowed:
            growth.append(f"duplicate block {key}: {count} shared windows, baseline {allowed}")
    for key in current["cardinality"]:
        if key not in baseline["cardinality"]:
            growth.append(f"stale count {key}: write `{current['cardinality'][key]}` instead")
    for key, allowed in baseline["duplicate_blocks"].items():
        if current["duplicate_blocks"].get(key, 0) < allowed:
            shrink.append(f"duplicate block {key} shrank below baseline {allowed}")
    shrink.extend(
        f"stale count {key} is gone"
        for key in baseline["cardinality"]
        if key not in current["cardinality"]
    )
    return sorted(growth), sorted(shrink)


def amplification(repo_root: Path, duplicates: dict[str, int]) -> dict[str, dict[str, int]]:
    """Report authored change amplification per capability owner (steady state is 1).

    Raises GraphViolationError over an invalid graph: fan-out from a broken graph misleads.
    """
    nodes, owners, findings = survey(repo_root)
    if findings:
        raise GraphViolationError(
            f"capability graph has {len(findings)} violation(s); fix them before "
            "--report: " + "; ".join(findings[:3])
        )
    report: dict[str, dict[str, int]] = {}
    for name, owner in sorted(owners.items()):
        copies = sum(1 for pair in duplicates if owner.path in pair.split("|"))
        dependents = sum(1 for n in nodes if n.canonical and name in n.depends_on)
        report[name] = {"amplification": 1 + copies, "dependents": dependents}
    return report


def _remediation() -> str:
    return (
        "Fix, in order of preference: delete the repeated text; keep one owner and "
        "depend on it; drop the derived count. Do not resync copies, because a "
        "synchronized copy keeps the obligation. To lock in a burn-down, run "
        "`uv run python scripts/validation/check_nl_structural_debt.py --update-baseline`."
    )


def validate_nl_structural_debt(repo_root: Path) -> bool:
    """Return True when debt is at or below the baseline. Entry point for pre_pr_sequence."""
    return run(repo_root, update=False) == 0


def run(repo_root: Path, update: bool, report: bool = False) -> int:
    """Measure, compare, and return an ADR-035 exit code."""
    try:
        current = measure(repo_root)
        path = repo_root / BASELINE_PATH
        baseline = current if update and not path.is_file() else _load_baseline(repo_root)
        fanout = amplification(repo_root, current["duplicate_blocks"]) if report else {}
    except GraphViolationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    except (ScanError, TreeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    growth, shrink = compare(current, baseline)
    examined = len(authored_files(repo_root))
    if report:
        payload = {**current, "amplification": fanout, "examined": examined}
        print(json.dumps(payload, indent=2, sort_keys=True))
    if growth:
        print(f"[FAIL] {len(growth)} structural debt increase(s):", file=sys.stderr)
        print("\n".join(f"  {g}" for g in growth), file=sys.stderr)
        print(_remediation(), file=sys.stderr)
        return 1
    if shrink and not update:
        print(f"[FAIL] {len(shrink)} baseline entr(ies) are stale; debt shrank:", file=sys.stderr)
        print("\n".join(f"  {s}" for s in shrink), file=sys.stderr)
        print(_remediation(), file=sys.stderr)
        return 1
    if update:
        path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not report:
        print(f"[PASS] NL structural debt: 0 increases, {examined} authored artifacts examined")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo_root", nargs="?", default=None)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    root = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parents[2]
    if not root.is_dir():
        print(f"[FAIL] Invalid repository root: {root}", file=sys.stderr)
        return 2
    return run(root, args.update_baseline, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
