#!/usr/bin/env python3
"""Detect normative or procedural content written into Serena memories (#5391).

`.serena/memories/` is a retrieval aid, not a binding surface: it is MCP-gated,
so Claude, Codex, and Copilot are not guaranteed to load it.
`.claude/rules/knowledge-persistence.md` MUST NOT item 1, quoted verbatim:

    MUST NOT rely on Serena memory or Copilot Memory alone to persist a
    convention that other harnesses or contributors must obey. Those are
    retrieval complements, not the cross-harness binding.

This check is the placement backstop for that rule. It flags a memory whose
content reads as a rule, a procedure, or an agent-role contract rather than as
evidence, so the normative half moves to `.claude/rules/`, `.claude/skills/`,
or `.claude/agents/` and the memory keeps the evidence.

Scope: placement only. Memory-index integrity, orphan and duplicate targets
(#4313, #4776, #4705), capability ownership (#5396), prompt duplication
(#5397), and context budgets (#5400) are owned elsewhere and are not measured
here.

Signals are scored in `scripts/validation/memory_placement_signals.py`, which
documents the four of them and the threshold. Baseline mode and the corpus
inventory live in `scripts/validation/memory_placement_baseline.py`, which
documents how the ratchet differs from the discriminator's.

Escape hatches, both copied from the agent-skill discriminator
(`scripts/validation/check_agent_skill_discriminator.py`) rather than invented
here: ``placement_exception: <rationale>`` in the memory's frontmatter, or
``[memory-placement: <rationale>]`` in the PR description (``--pr-body`` /
``PR_BODY``). A third exemption comes from ``--baseline``, which forgives a
file whose score has not risen above the value recorded there.

Exit codes follow ADR-035:
    0 - Success: no scored memory fails the gate (or an escape hatch applies)
    1 - Error: one or more scored memories fail the gate
    2 - Config error: repo root or memories directory not found; a baseline
        that cannot be read, resolved, or holds a score outside 0..5; a
        full-corpus scan git could not answer or that found no tracked
        memory; or a --update-baseline run started outside the repo root

Related: ADR-006 (thin workflows / testable modules), ADR-035 (exit codes),
ADR-042 (Python-first).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Bootstrap: this module is invoked both as a bare script and via ``-m``. A
# bare-script invocation puts only this file's own directory on sys.path, so
# the scripts.validation package does not resolve without help. Mirrors the
# identical block at `scripts/validation/check_agent_skill_discriminator.py`.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_PACKAGE_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _VALIDATION_PACKAGE_SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.memory_placement_baseline import (  # noqa: E402
    DEFAULT_BASELINE_NAME,
    MAX_SCORE,
    MEMORY_ROOT,
    baseline_note,
    filter_memory_paths,
    full_corpus_memory_paths,
    refuse_incomplete_corpus,
    resolve_repo_path,
    update_baseline,
    validate_baseline_scores,
)
from scripts.validation.memory_placement_signals import (  # noqa: E402
    FLAG_THRESHOLD,
    MemoryScore,
    score_content,
)
from scripts.validation.portability_common import (  # noqa: E402
    load_baseline,
    resolve_checked_baseline,
)

RULE_PATH = ".claude/rules/knowledge-persistence.md"


@dataclass
class CheckResult:
    """Aggregate outcome across every scored memory."""

    scores: list[MemoryScore] = field(default_factory=list)
    override_rationale: str | None = None
    baseline: dict[str, int] | None = None

    def fails_gate(self, score: MemoryScore) -> bool:
        """True when ``score`` fails the gate before the PR-body override.

        Threshold mode (``baseline`` unset) is the plain candidate rule.
        Baseline mode makes it a ratchet: a recorded file fails only when its
        score rises above the recorded value, an unrecorded one falls back to
        the plain rule.
        """
        if score.exception is not None:
            return False
        if self.baseline is None:
            return score.is_candidate
        recorded = self.baseline.get(score.path)
        if recorded is None:
            return score.is_candidate
        return score.score > recorded

    @property
    def failing(self) -> list[MemoryScore]:
        """Files that fail the gate, after the PR-description override."""
        if self.override_rationale:
            return []
        return [s for s in self.scores if self.fails_gate(s)]


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

_OVERRIDE_TOKEN = re.compile(
    r"\[memory-placement:\s*(?P<rationale>[^\]]+)\]", re.IGNORECASE
)


def run_check(repo_root: Path, changed_files: list[str], pr_body: str) -> CheckResult:
    """Score every scoped memory and resolve the PR-description override."""
    result = CheckResult()
    if override := _OVERRIDE_TOKEN.search(pr_body or ""):
        result.override_rationale = override.group("rationale").strip()

    for path in filter_memory_paths(changed_files):
        full = resolve_repo_path(repo_root, path)
        result.scores.append(score_content(path, full.read_text(encoding="utf-8")))
    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _signals(score: MemoryScore) -> str:
    return (
        f"sections={score.section_hits} "
        f"ordered={score.ordered_hits} "
        f"modals={score.modal_hits} "
        f"role={'Y' if score.role_contract else 'n'}"
    )


def print_report(result: CheckResult) -> None:
    """Print a human-readable summary. Always names the examined count."""
    print("Memory placement check (Issue #5391)")
    print("=" * 60)

    if not result.scores:
        print("Examined 0 memory files: no memory changes in scope.")
        return

    failing_paths = {s.path for s in result.failing}
    for score in sorted(result.scores, key=lambda s: (-s.score, s.path)):
        if score.path not in failing_paths and score.score < FLAG_THRESHOLD:
            continue
        status = "FLAG" if score.path in failing_paths else "ok"
        print(
            f"  [{status}] {score.path} (score {score.score}/{MAX_SCORE}: "
            f"{_signals(score)})"
            f"{baseline_note(score.path, score.score, result.baseline)}"
            + (f" exception={score.exception}" if score.exception else "")
        )

    if result.override_rationale:
        print(f"\nPR override present: {result.override_rationale}")

    failing = result.failing
    print()
    if not failing:
        print(
            f"PASS: 0 placement violations in {len(result.scores)} memory files "
            "examined."
        )
        return

    print(
        f"FAIL: {len(failing)} placement violations in {len(result.scores)} "
        "memory files examined. These read as normative or procedural content, "
        "which Serena memory MUST NOT carry alone:"
    )
    for score in failing:
        print(f"  - {score.path} (score {score.score}/{MAX_SCORE}: {_signals(score)})")
    print()
    print("Each flagged file must either:")
    print("  1. Move the binding half to .claude/rules/, .claude/skills/, or")
    print("     .claude/agents/ and keep only evidence in the memory, or")
    print("  2. Carry 'placement_exception: <rationale>' in its frontmatter, or")
    print("  3. Carry the PR-description token '[memory-placement: <rationale>]'.")
    print()
    print(f"See {RULE_PATH}, 'Placement contract'.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _split_changed_arg(values: list[str] | None, env_value: str | None) -> list[str]:
    """Normalize changed-file inputs from CLI args or a whitespace-separated env."""
    if values is not None:
        return list(values)
    if env_value:
        return [p for p in re.split(r"\s+", env_value.strip()) if p]
    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect normative content added to .serena/memories (#5391).",
    )
    parser.add_argument(
        "--repo-root",
        default=os.environ.get("REPO_ROOT", "."),
        help="Repository root (env: REPO_ROOT, default: .)",
    )
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Changed memory paths to score (space-separated; env: CHANGED_FILES).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Score every memory tracked at HEAD, not just changed files.",
    )
    parser.add_argument(
        "--pr-body",
        default=os.environ.get("PR_BODY", ""),
        help="PR description text; scanned for the override token (env: PR_BODY).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help=(
            "Path to a placement baseline JSON. Passing it switches the gate "
            "from the plain threshold to a ratchet: a file recorded there "
            "fails only when its score rises above the recorded value, while "
            "a file absent from it uses the plain threshold. There is no "
            "default in gate mode; only --update-baseline falls back to "
            f"scripts/validation/{DEFAULT_BASELINE_NAME}."
        ),
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Score every tracked memory (like --all) and write the result to "
            "--baseline (or the default path) instead of gating."
        ),
    )
    parser.add_argument(
        "--allow-baseline-shrink",
        action="store_true",
        help=(
            "With --update-baseline, permit a rewrite that lowers or drops a "
            "recorded score."
        ),
    )
    return parser


def _resolve_scope(
    args: argparse.Namespace, repo_root: Path
) -> tuple[list[str] | None, Path | None, int | None]:
    """Resolve the full-corpus scope and the baseline path.

    Returns ``(changed_override, baseline_path, error_code)``.
    ``changed_override`` is ``None`` when the ordinary changed-files scope
    applies unmodified.
    """
    changed_override: list[str] | None = None
    if args.all or args.update_baseline:
        changed_override = full_corpus_memory_paths(repo_root)
        if error := refuse_incomplete_corpus(changed_override, repo_root):
            return None, None, error

    if args.baseline is None and not args.update_baseline:
        return changed_override, None, None

    baseline_path = resolve_checked_baseline(
        repo_root, args.baseline, DEFAULT_BASELINE_NAME
    )
    if baseline_path is None:
        # resolve_checked_baseline already explained the refusal.
        return changed_override, None, 2
    return changed_override, baseline_path, None


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    args = build_parser().parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"Repo root not found: {repo_root}", file=sys.stderr)
        return 2
    if not (repo_root / MEMORY_ROOT).is_dir():
        print(
            f"Memories directory not found: {repo_root / MEMORY_ROOT}",
            file=sys.stderr,
        )
        return 2

    changed = _split_changed_arg(args.changed_files, os.environ.get("CHANGED_FILES"))
    changed_override, baseline_path, error = _resolve_scope(args, repo_root)
    if error is not None:
        return error
    if changed_override is not None:
        changed = changed_override

    try:
        result = run_check(repo_root, changed, args.pr_body)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if args.update_baseline:
        if baseline_path is None:  # pragma: no cover - resolved above
            return 2
        # Record only the files already at or above the threshold: the
        # register is a debt list, not a full-corpus snapshot. See the module
        # docstring of memory_placement_baseline.py for why.
        return update_baseline(
            baseline_path,
            {s.path: s.score for s in result.scores if s.score >= FLAG_THRESHOLD},
            repo_root=repo_root,
            allow_shrink=args.allow_baseline_shrink,
            flag_threshold=FLAG_THRESHOLD,
        )

    if baseline_path is not None:
        try:
            loaded = load_baseline(baseline_path)
            validate_baseline_scores(loaded)
        except (OSError, ValueError) as exc:
            print(f"Could not read baseline {baseline_path}: {exc}", file=sys.stderr)
            return 2
        result.baseline = loaded

    print_report(result)
    return 1 if result.failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
