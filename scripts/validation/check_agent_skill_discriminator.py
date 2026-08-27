#!/usr/bin/env python3
"""Phase 3 CI check: detect new agents added in skill shape (Issue #2008).

Backstop for the agent-skill classification audit (Issue #2003). The audit
found 42 percent of 23 agents were skill-shape candidates. This check stops
new agents from accumulating the same misclassification debt at PR time.

Discriminator (locked by the #2003 audit; canonical source:
``.agents/audits/2026-05-10-agent-skill-classification-audit.md``):

A new or materially changed agent under ``.claude/agents/`` (or its
``templates/agents/*.shared.md`` sibling per ADR-036) is a skill-shape
candidate when 2 or more of these hold:

- c1: invoked from a slash command via ``Task(subagent_type="<name>")``
  (searched across ``.claude/commands/`` and ``templates/commands/``).
- c2: body is at least 70 percent structured-reference material (tables,
  decision-tree list items, anti-pattern catalogs, format/schema specs,
  validation rule lists). Counted conservatively; see ``score_c2``.
- c3: a sibling artifact invoked from the same slash-command pipeline is
  already a skill (``Skill(skill="<name>")``), AND the agent is invoked from
  fewer than 3 distinct pipelines (the 3-pipeline rule). c3 is N/A (scores 0)
  when c1 is false or the agent is invoked from 3 or more pipelines.

c4 (PR-history schema drift) requires git history and is out of scope for CI.

An agent scoring 2 or more FAILS the check unless one escape hatch is present:

- Agent frontmatter contains ``isolation_required: true`` (with a rationale),
  or
- The PR description carries the token ``[skill-discriminator: <rationale>]``
  (passed via ``--pr-body`` / ``PR_BODY``), or
- ``--baseline`` names a recorded baseline (issue #4087) and the agent's
  score has not risen above the value recorded there.

Baseline mode (issue #4087): the check is change-triggered by default, so an
agent that is already skill-shaped on ``main`` stays invisible until an
unrelated edit happens to touch it, which makes the gate fire on PRs that
cannot have caused the condition (PR #4067, PR #4063). ``--update-baseline``
scores every agent in the repo (like ``--all``) and records each one's score
in a checked-in JSON file. A later run with ``--baseline <path>`` then fails
an agent only when its score has risen above the recorded value; a new agent
absent from the baseline still uses the ordinary score>=2 threshold. See
``is_regression`` below for the exact comparison and why it does not reuse
the shared ``portability_common.diff_against_baseline`` ratchet as is.

Exit codes follow ADR-035:
    0 - Success: no changed agent fails the discriminator (or escape hatch set)
    1 - Error: one or more changed agents score 2+ without an escape hatch
    2 - Config error: repo root, commands directory, or baseline not found;
        a baseline score outside 0..3; a full-corpus scan that git could not
        answer or that found no tracked agent; or a --update-baseline run
        started from outside the repo root it was told to write into

Related: ADR-006 (thin workflows / testable modules), ADR-042 (Python-first),
ADR-030 (Skills Pattern Superiority), ADR-036 (Two-Source Agent Templates).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Bootstrap: this module is invoked both as a bare script
# (`python3 scripts/validation/check_agent_skill_discriminator.py`, from CI
# and from the test suite) and via `-m`. A bare-script invocation puts only
# this file's own directory on sys.path, so the scripts.validation package
# does not resolve without help. Mirrors the identical bootstrap block at
# `scripts/validation/check_skill_portability.py:50-53`.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_PACKAGE_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _VALIDATION_PACKAGE_SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.agent_skill_discriminator_baseline import (  # noqa: E402
    AGENT_CORPUS_ROOTS,
    DEFAULT_BASELINE_NAME,
    baseline_from_scores,
    baseline_note,
    full_corpus_agent_paths,
    is_regression,
    validate_baseline_scores,
)
from scripts.validation.portability_common import (  # noqa: E402
    load_baseline,
    resolve_checked_baseline,
    write_baseline,
)

AUDIT_PATH = ".agents/audits/2026-05-10-agent-skill-classification-audit.md"
ADR_PATH = ".agents/architecture/ADR-030-skills-pattern-superiority.md"

# Reserved metadata files that are not agents.
_NON_AGENT_NAMES: frozenset[str] = frozenset({"AGENTS", "CLAUDE", "README"})

# c2: an agent body counts as skill-shape when this fraction of its content
# lines are structured-reference. Locked at 0.70 by the #2003 audit (PRD s.11).
C2_THRESHOLD: float = 0.70

# The 3-pipeline rule: an agent invoked from this many distinct slash-command
# pipelines (or more) is too cross-cutting to be a skill candidate; c3 is N/A.
PIPELINE_RULE_LIMIT: int = 3

# PR-description escape-hatch token: ``[skill-discriminator: rationale text]``.
_OVERRIDE_TOKEN: re.Pattern[str] = re.compile(
    r"\[skill-discriminator:\s*(?P<rationale>[^\]]+)\]", re.IGNORECASE
)
_DESCRIPTIVE_TASK: re.Pattern[str] = re.compile(
    r"Task\([ \t]*subagent_type[ \t]*=[ \t]*\.\.\.[ \t]*\)[^\n]*?\((?P<agents>[^)\n]+)\)"
)

# Structured-reference line markers (c2). Conservative: only lines that are
# clearly reference shapes count. Prose bullets that are full sentences are
# excluded by the sentence heuristic in ``_is_reference_line``.
_TABLE_ROW: re.Pattern[str] = re.compile(r"^\s*\|.*\|\s*$")
_LIST_ITEM: re.Pattern[str] = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\S")
_HEADING: re.Pattern[str] = re.compile(r"^\s*#{1,6}\s+\S")


@dataclass(frozen=True, slots=True)
class AgentScore:
    """Discriminator outcome for a single agent."""

    name: str
    path: str
    c1: bool
    c2: bool
    c3: bool
    pipeline_count: int
    isolation_required: bool

    @property
    def score(self) -> int:
        """Number of true discriminator criteria (c1 + c2 + c3)."""
        return int(self.c1) + int(self.c2) + int(self.c3)

    @property
    def is_candidate(self) -> bool:
        """True when the agent is a skill-shape candidate (score >= 2)."""
        return self.score >= 2


@dataclass
class CheckResult:
    """Aggregate outcome across all changed agents."""

    scores: list[AgentScore] = field(default_factory=list)
    override_rationale: str | None = None
    baseline: dict[str, int] | None = None

    def fails_gate(self, score: AgentScore) -> bool:
        """True when ``score`` fails the discriminator before the override.

        Threshold mode (``baseline`` unset) is the original score>=2 rule.
        Baseline mode (issue #4087) makes this a ratchet instead: see
        ``is_regression``.

        Public because the report must label each agent by the gate that
        actually ran. Labelling from ``is_candidate`` instead reported a
        baseline regression from 0 to 1 as ``[ok]`` on the same run that
        exited 1 because of it.
        """
        if score.isolation_required:
            return False
        if self.baseline is None:
            return score.is_candidate
        return is_regression(score, self.baseline)

    @property
    def candidates(self) -> list[AgentScore]:
        """Scores that fail the gate, before the PR-description override."""
        return [s for s in self.scores if self.fails_gate(s)]

    @property
    def failing(self) -> list[AgentScore]:
        """Candidates that fail the check (no escape hatch of any kind)."""
        if self.override_rationale:
            return []
        return self.candidates


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


def split_frontmatter(content: str) -> tuple[str, str]:
    """Return (frontmatter_block, body) for a markdown file.

    The frontmatter block excludes the ``---`` fences. When no frontmatter is
    present the first element is empty and the body is the whole content.
    """
    if not content.startswith("---"):
        return "", content

    lines = content.splitlines()
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :])
    return "", content


def has_isolation_required(frontmatter: str) -> bool:
    """True when frontmatter declares ``isolation_required: true``.

    The audit accepts the flag as the machine-readable escape hatch. Rationale
    text can live in a comment or nearby frontmatter, but this parser only
    evaluates the truthy flag value. A bare ``isolation_required: false`` does
    not qualify.
    """
    match = re.search(
        r"^isolation_required:[ \t]*['\"]?(?P<value>true|yes|1|false|no|0)['\"]?[ \t]*(?:#.*)?$",
        frontmatter,
        re.IGNORECASE | re.MULTILINE,
    )
    if match is None:
        return False
    return match.group("value").lower() in {"true", "yes", "1"}


# ---------------------------------------------------------------------------
# c2: structured-reference heuristic
# ---------------------------------------------------------------------------


def _is_reference_line(line: str) -> bool:
    """True when a non-blank body line is structured-reference, not prose.

    Conservative count rule (issue note: the audit heuristic over-estimated
    reasoning agents). A line counts as reference when it is a table row,
    a heading, or a short list item. A list item that reads as a full prose
    sentence (ends in a period and runs long) does NOT count.
    """
    if _TABLE_ROW.match(line):
        return True
    if _HEADING.match(line):
        return True
    if _LIST_ITEM.match(line):
        stripped = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", line).strip()
        # A long bullet that ends like a sentence is reasoning prose, not a
        # decision-tree entry. Keep short, label-like bullets as reference.
        words = stripped.split()
        if len(words) > 18 and stripped.endswith((".", "!", "?")):
            return False
        return True
    return False


def _content_lines(body: str) -> list[str]:
    """Body lines that count toward the c2 denominator.

    Excludes blank lines and fenced-code-block content (code is neither prose
    nor decision-tree reference; counting it skews both ways).
    """
    out: list[str] = []
    in_fence = False
    for raw in body.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            continue
        out.append(raw)
    return out


def score_c2(body: str) -> tuple[bool, float]:
    """Return (is_skill_shape, ratio) for the structured-reference heuristic."""
    lines = _content_lines(body)
    if not lines:
        return False, 0.0
    reference = sum(1 for line in lines if _is_reference_line(line))
    ratio = reference / len(lines)
    return ratio >= C2_THRESHOLD, ratio


# ---------------------------------------------------------------------------
# c1 / c3: slash-command pipeline analysis
# ---------------------------------------------------------------------------


def _task_invocations(text: str) -> set[str]:
    """Agent names invoked via literal or descriptive ``Task`` forms."""
    agents = set(
        re.findall(
            r"Task\([ \t]*subagent_type[ \t]*=[ \t]*['\"]([a-z0-9-]+)['\"]",
            text,
        )
    )
    for match in _DESCRIPTIVE_TASK.finditer(text):
        agents.update(
            name
            for raw in match.group("agents").split(",")
            if (name := raw.strip()) and re.fullmatch(r"[a-z0-9-]+", name)
        )
    return agents


def _skill_invocations(text: str) -> set[str]:
    """Skill names invoked via ``Skill(skill="<name>")`` in one file."""
    return set(
        re.findall(
            r"Skill\([ \t]*skill[ \t]*=[ \t]*['\"]([a-z0-9-]+)['\"]",
            text,
        )
    )


def _command_files(repo_root: Path) -> list[Path]:
    """Slash-command markdown files across both command source trees."""
    files: list[Path] = []
    for rel in (".claude/commands", "templates/commands"):
        base = repo_root / rel
        if base.is_dir():
            files.extend(sorted(base.rglob("*.md")))
    return files


@dataclass(frozen=True, slots=True)
class PipelineIndex:
    """Per-command-file map of agents invoked and skills invoked."""

    agents_by_file: dict[str, frozenset[str]]
    skills_by_file: dict[str, frozenset[str]]

    def pipelines_for(self, agent: str) -> list[str]:
        """Command files that invoke the agent via Task()."""
        return [f for f, agents in self.agents_by_file.items() if agent in agents]

    def sibling_skill_in_pipeline(self, agent: str) -> bool:
        """True when any pipeline invoking the agent also invokes a skill."""
        for path in self.pipelines_for(agent):
            if self.skills_by_file.get(path):
                return True
        return False


def build_pipeline_index(repo_root: Path) -> PipelineIndex:
    """Index every slash command's Task() and Skill() invocations."""
    agents_by_file: dict[str, frozenset[str]] = {}
    skills_by_file: dict[str, frozenset[str]] = {}
    for path in _command_files(repo_root):
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(repo_root))
        agents_by_file[rel] = frozenset(_task_invocations(text))
        skills_by_file[rel] = frozenset(_skill_invocations(text))
    return PipelineIndex(agents_by_file, skills_by_file)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def agent_name_from_path(path: str) -> str:
    """Derive the agent name from a .claude/agents or templates/agents path."""
    stem = Path(path).name
    # templates/agents/<name>.shared.md -> <name>
    if stem.endswith(".shared.md"):
        return stem[: -len(".shared.md")]
    return Path(stem).stem


def is_agent_path(path: str) -> bool:
    """True when the path is an agent definition (not metadata, not a skill).

    Excludes reference documentation under ``agents/*/references/`` (#4813).
    """
    norm = path.replace("\\", "/")
    name = agent_name_from_path(norm)
    if name in _NON_AGENT_NAMES:
        return False
    if norm.endswith(".shared.md"):
        return "templates/agents/" in norm
    if "/references/" in norm:
        return False
    return "/.claude/agents/" in f"/{norm}" and norm.endswith(".md")


def resolve_repo_path(repo_root: Path, relative_path: str) -> Path:
    """Return a resolved path only when it stays under the repo root."""
    resolved_root = repo_root.resolve()
    full_path = (resolved_root / relative_path).resolve()
    if not full_path.is_relative_to(resolved_root):
        raise ValueError(f"Path escapes repo root: {relative_path}")
    return full_path


def score_agent(repo_root: Path, agent_path: str, index: PipelineIndex) -> AgentScore:
    """Score one resolved agent file against c1 + c2 + c3."""
    full = resolve_repo_path(repo_root, agent_path)
    name = agent_name_from_path(str(full))
    content = full.read_text(encoding="utf-8")

    frontmatter, body = split_frontmatter(content)
    isolation = has_isolation_required(frontmatter)

    pipelines = index.pipelines_for(name)
    pipeline_count = len(pipelines)
    c1 = pipeline_count > 0

    c2_shape, _ratio = score_c2(body)

    # c3 is N/A (False) when c1 is false or the agent spans 3+ pipelines.
    if not c1 or pipeline_count >= PIPELINE_RULE_LIMIT:
        c3 = False
    else:
        c3 = index.sibling_skill_in_pipeline(name)

    return AgentScore(
        name=name,
        path=agent_path,
        c1=c1,
        c2=c2_shape,
        c3=c3,
        pipeline_count=pipeline_count,
        isolation_required=isolation,
    )


def filter_agent_paths(changed_files: list[str]) -> list[str]:
    """Keep only agent-definition paths, de-duplicated, order-stable."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in changed_files:
        path = raw.strip()
        if not path or not is_agent_path(path):
            continue
        if path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def run_check(
    repo_root: Path, changed_files: list[str], pr_body: str
) -> CheckResult:
    """Score every changed agent and resolve the PR-description override."""
    index = build_pipeline_index(repo_root)
    result = CheckResult()

    override = _OVERRIDE_TOKEN.search(pr_body or "")
    if override is not None:
        result.override_rationale = override.group("rationale").strip()

    for agent_path in filter_agent_paths(changed_files):
        result.scores.append(score_agent(repo_root, agent_path, index))
    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _criteria_str(score: AgentScore) -> str:
    parts = [
        f"c1={'Y' if score.c1 else 'n'}",
        f"c2={'Y' if score.c2 else 'n'}",
        f"c3={'Y' if score.c3 else 'n'}",
    ]
    return " ".join(parts)


def _status_label(result: CheckResult, score: AgentScore) -> str:
    """Per-agent report label, named for the gate that actually ran.

    ``ok`` is reserved for an agent that passes the gate in force. In baseline
    mode that gate is the ratchet, so a rise from a recorded 0 to 1 fails and
    must not read ``ok`` merely because 1 is below the score>=2 threshold. The
    two failing labels are kept distinct because they mean different things to
    the reader: ``CANDIDATE`` says the agent is skill-shaped, ``REGRESSION``
    says only that it got more skill-shaped than the recorded floor.
    """
    if not result.fails_gate(score):
        return "ok"
    return "REGRESSION" if result.baseline is not None else "CANDIDATE"


def print_report(result: CheckResult) -> None:
    """Print a human-readable summary of the scoring."""
    print("Agent-skill discriminator check (Issue #2008)")
    print("=" * 60)

    if not result.scores:
        print("No changed agent definitions to score.")
        return

    for score in result.scores:
        status = _status_label(result, score)
        print(
            f"  [{status}] {score.name} "
            f"(score {score.score}/3: {_criteria_str(score)}, "
            f"pipelines={score.pipeline_count}, "
            f"isolation_required={'yes' if score.isolation_required else 'no'})"
            f"{baseline_note(score, result.baseline)}"
        )

    if result.override_rationale:
        print()
        print(f"PR override present: {result.override_rationale}")

    failing = result.failing
    scored = len(result.scores)
    print()
    if not failing:
        if result.baseline is not None:
            print(
                f"PASS: no agent regressed above its recorded baseline score "
                f"({scored} scored)."
            )
        else:
            print(f"PASS: no agent fails the discriminator ({scored} scored).")
        return

    if result.baseline is not None:
        # Baseline mode fails at any score, not only at 2+: an agent recorded
        # at 0 fails on a rise to 1. Only an agent with no recorded floor
        # falls back to the score>=2 threshold, and its annotation says so.
        print(
            f"FAIL: the following agents fail the baseline ratchet "
            f"({len(failing)} of {scored} scored). An agent recorded in the "
            "baseline fails when its score rises above the recorded value, at "
            "any score. An agent marked 'baseline=new' has no recorded floor "
            "and failed the ordinary score>=2 threshold instead:"
        )
    else:
        print(
            f"FAIL: the following agents are skill-shape candidates (score 2+) "
            f"({len(failing)} of {scored} scored):"
        )
    for score in failing:
        print(
            f"  - {score.name} (score {score.score}/3: {_criteria_str(score)})"
            f"{baseline_note(score, result.baseline)}"
        )
    print()
    print("Each candidate must either:")
    print("  1. Be refactored into a skill before merge, or")
    print("  2. Add 'isolation_required: true' (with a one-line rationale) to")
    print("     the agent frontmatter, or")
    print("  3. Carry the PR-description token")
    print("     '[skill-discriminator: <rationale>]' for a one-off override.")
    if result.baseline is not None:
        print()
        print("Raising the recorded baseline score is not one of the options.")
        print("A ratchet baseline may only fall")
        print("(.claude/rules/ci-scripts.md, 'Count ratchets').")
    print()
    print(f"See {AUDIT_PATH}")
    print(f"and {ADR_PATH}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _split_changed_arg(values: list[str] | None, env_value: str | None) -> list[str]:
    """Normalize changed-file inputs from CLI args or a whitespace/newline env."""
    if values is not None:
        return list(values)
    if env_value:
        return [p for p in re.split(r"\s+", env_value.strip()) if p]
    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect new agents added in skill shape (Issue #2008).",
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
        help="Changed agent file paths to score (space-separated).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Score every agent in the repo, not just changed files. "
        "Used by the scheduled full-corpus audit (Issue #4087).",
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
            "Path to a skill-discriminator baseline JSON (issue #4087). "
            "Passing it switches the gate from the plain score>=2 threshold "
            "to a ratchet: an agent already recorded there fails only if its "
            "score rose above the recorded value, while an agent absent from "
            "it still uses the score>=2 threshold. There is no default in "
            "gate mode. Omit this flag and the gate stays on the plain "
            "threshold, reading no baseline at all. The only mode that falls "
            "back to a default path is --update-baseline, which writes to "
            f"scripts/validation/{DEFAULT_BASELINE_NAME} when this flag is "
            "omitted."
        ),
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Score every agent in the repo (like --all) and write the "
            "result to --baseline (or the default path) instead of gating. "
            "Exits 0 on a successful write."
        ),
    )
    parser.add_argument(
        "--allow-baseline-shrink",
        action="store_true",
        help=(
            "With --update-baseline, permit a rewrite that lowers or drops "
            "a recorded score. Without it, a lower score requires this flag "
            "so a decrease is a reviewable, deliberate act."
        ),
    )
    return parser


def _refuse_incomplete_corpus(corpus: list[str] | None, repo_root: Path) -> int | None:
    """Config-error code when a full-corpus scan did not produce a corpus.

    Two refusals, both fail-closed, both ADR-035 exit 2:

    ``None`` means ``git ls-tree HEAD`` could not answer, so what the commit
    contains is unknown. Falling back to a directory walk here would restore
    the defect the ref read exists to remove.

    An empty list means git answered and no agent definition is tracked. That
    is indistinguishable in outcome from a scan that examined nothing, and
    `.claude/rules/ci-scripts.md` MUST-12 forbids reporting the two the same
    way: a full-corpus run that scores zero agents would pass the gate and
    write an empty baseline, which disables the ratchet for every path at
    once. There is no legitimate full-corpus run over an empty corpus.
    """
    if corpus is None:
        print(
            f"Cannot list the files tracked at HEAD in {repo_root}. "
            "Full-corpus mode scores what the commit contains and will not "
            "fall back to a filesystem walk, which counts untracked files "
            "and reads a partial checkout as an empty repository "
            "(.claude/rules/ci-scripts.md MUST-9).",
            file=sys.stderr,
        )
        return 2
    if not corpus:
        print(
            f"No agent definitions are tracked at HEAD in {repo_root} "
            f"(examined 0 of the paths under {', '.join(AGENT_CORPUS_ROOTS)}). "
            "Refusing a full-corpus run over an empty corpus: it would pass "
            "the gate and record a baseline that gates nothing.",
            file=sys.stderr,
        )
        return 2
    return None


def _resolve_baseline_scope(
    args: argparse.Namespace, repo_root: Path
) -> tuple[list[str] | None, Path | None, int | None]:
    """Resolve the baseline-mode changed-file scope and baseline path.

    Returns ``(changed_override, baseline_path, error_code)``. ``error_code``
    is ``None`` on success. ``changed_override`` is ``None`` when the ordinary
    ``--changed-files``/``CHANGED_FILES`` scope applies unmodified; the caller
    substitutes it for ``changed`` only when it is not ``None``.
    """
    changed_override: list[str] | None = None
    if args.all or args.update_baseline:
        # Full-corpus mode: score every agent tracked at HEAD (Issue #4087).
        # Overrides --changed-files and CHANGED_FILES. --update-baseline
        # always needs the full corpus: it has nothing else to record.
        changed_override = full_corpus_agent_paths(repo_root, is_agent_path)
        if error := _refuse_incomplete_corpus(changed_override, repo_root):
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


def _refuses_write_from_outside(repo_root: Path) -> bool:
    """True when the process is not standing inside ``repo_root``.

    ``.claude/rules/ci-scripts.md`` MUST-7, quoted verbatim: "A script that
    resolves the repository root and then writes to it MUST confirm the
    current directory is inside the resolved root before the first write
    (``Path.cwd().resolve().is_relative_to(top_level)``)."

    Different than canonical: the rule's worked example is a root taken from
    ``git rev-parse --show-toplevel``, which ``GIT_WORK_TREE`` or a local
    ``core.worktree`` can redirect to a directory the process is not in. The
    root here comes from ``--repo-root``/``REPO_ROOT`` instead, so the
    redirection is one argument rather than one environment variable, and the
    failure it produces is the same: the baseline lands in a checkout other
    than the one being worked in, recording scores nobody reviewed against a
    tree nobody was looking at. The check is identical either way, and it runs
    before the first write rather than after a partial one.
    """
    cwd = Path.cwd().resolve()
    if cwd.is_relative_to(repo_root):
        return False
    print(
        f"Refusing to write a baseline into {repo_root} while running from "
        f"{cwd}. --update-baseline records the checkout it is run from; a "
        "repo root that is not an ancestor of the current directory means "
        "the two disagree about which tree is being recorded "
        "(.claude/rules/ci-scripts.md MUST-7).",
        file=sys.stderr,
    )
    return True


def _update_baseline(
    baseline_path: Path, result: CheckResult, *, repo_root: Path, allow_shrink: bool
) -> int:
    """Write the full-corpus baseline for ``--update-baseline``."""
    if _refuses_write_from_outside(repo_root):
        return 2
    return write_baseline(
        baseline_path,
        baseline_from_scores(result.scores),
        (
            "Skill-shape discriminator full-corpus baseline (issue "
            "#4087). Per-path scores (0-3), one entry per agent "
            "definition under .claude/agents/ and templates/agents/. "
            "Generated by check_agent_skill_discriminator.py "
            "--update-baseline. A gate run with --baseline fails an "
            "agent only when its score rises above the value recorded "
            "here; a run with no --baseline uses the plain score>=2 "
            "threshold instead."
        ),
        "score points",
        repo_root=repo_root,
        allow_shrink=allow_shrink,
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"Repo root not found: {repo_root}", file=sys.stderr)
        return 2

    commands_dir = repo_root / ".claude" / "commands"
    if not commands_dir.is_dir():
        print(
            f"Commands directory not found: {commands_dir} "
            "(cannot score c1/c3).",
            file=sys.stderr,
        )
        return 2

    changed = _split_changed_arg(
        args.changed_files, os.environ.get("CHANGED_FILES")
    )

    changed_override, baseline_path, error = _resolve_baseline_scope(args, repo_root)
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
        return _update_baseline(
            baseline_path, result, repo_root=repo_root, allow_shrink=args.allow_baseline_shrink
        )

    if baseline_path is not None:
        try:
            # load_baseline vets the JSON shape and the integer type; it is
            # shared with the portability ratchets, whose values are unbounded
            # counts. validate_baseline_scores adds the 0..3 bound this gate
            # needs on top of it, in the same fail-closed path.
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
