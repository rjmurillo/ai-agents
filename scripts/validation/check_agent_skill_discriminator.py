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
  (passed via ``--pr-body`` / ``PR_BODY``).

Exit codes follow ADR-035:
    0 - Success: no changed agent fails the discriminator (or escape hatch set)
    1 - Error: one or more changed agents score 2+ without an escape hatch
    2 - Config error (repo root or commands directory not found)

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

# Structured-reference line markers (c2). Conservative: only lines that are
# clearly reference shapes count. Prose bullets that are full sentences are
# excluded by the sentence heuristic in ``_is_reference_line``.
_TABLE_ROW: re.Pattern[str] = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP: re.Pattern[str] = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
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

    @property
    def candidates(self) -> list[AgentScore]:
        """Candidates that lack the frontmatter escape hatch."""
        return [
            s for s in self.scores if s.is_candidate and not s.isolation_required
        ]

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

    lines = content.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i]), "\n".join(lines[i + 1 :])
    return "", content


def has_isolation_required(frontmatter: str) -> bool:
    """True when frontmatter declares ``isolation_required: true``.

    The escape hatch must carry a non-empty rationale on the same line or be
    accompanied by other frontmatter context; the audit only requires the flag
    plus a one-line rationale, so any truthy value qualifies here. A bare
    ``isolation_required: false`` does not qualify.
    """
    match = re.search(
        r"^\s*isolation_required:\s*(?P<value>\S+)",
        frontmatter,
        re.MULTILINE,
    )
    if match is None:
        return False
    return match.group("value").strip().lower() in {"true", "yes", "1"}


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
    for raw in body.split("\n"):
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
    """Agent names invoked via ``Task(subagent_type="<name>")`` in one file."""
    return set(re.findall(r'Task\(subagent_type="([a-z0-9-]+)"', text))


def _skill_invocations(text: str) -> set[str]:
    """Skill names invoked via ``Skill(skill="<name>")`` in one file."""
    return set(re.findall(r'Skill\(skill="([a-z0-9-]+)"', text))


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
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
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
    """True when the path is an agent definition (not metadata, not a skill)."""
    norm = path.replace("\\", "/")
    name = agent_name_from_path(norm)
    if name in _NON_AGENT_NAMES:
        return False
    if norm.endswith(".shared.md"):
        return "templates/agents/" in norm
    return "/.claude/agents/" in f"/{norm}" and norm.endswith(".md")


def score_agent(
    repo_root: Path, agent_path: str, index: PipelineIndex
) -> AgentScore | None:
    """Score one agent file against c1 + c2 + c3. None when file is missing."""
    name = agent_name_from_path(agent_path)
    full = repo_root / agent_path
    try:
        content = full.read_text(encoding="utf-8")
    except OSError:
        return None

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
        score = score_agent(repo_root, agent_path, index)
        if score is not None:
            result.scores.append(score)
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


def print_report(result: CheckResult) -> None:
    """Print a human-readable summary of the scoring."""
    print("Agent-skill discriminator check (Issue #2008)")
    print("=" * 60)

    if not result.scores:
        print("No changed agent definitions to score.")
        return

    for score in result.scores:
        status = "CANDIDATE" if score.is_candidate else "ok"
        print(
            f"  [{status}] {score.name} "
            f"(score {score.score}/3: {_criteria_str(score)}, "
            f"pipelines={score.pipeline_count}, "
            f"isolation_required={'yes' if score.isolation_required else 'no'})"
        )

    if result.override_rationale:
        print()
        print(f"PR override present: {result.override_rationale}")

    failing = result.failing
    print()
    if not failing:
        print("PASS: no agent fails the discriminator.")
        return

    print("FAIL: the following agents are skill-shape candidates (score 2+):")
    for score in failing:
        print(f"  - {score.name} ({_criteria_str(score)})")
    print()
    print("Each candidate must either:")
    print("  1. Be refactored into a skill before merge, or")
    print("  2. Add 'isolation_required: true' (with a one-line rationale) to")
    print("     the agent frontmatter, or")
    print("  3. Carry the PR-description token")
    print("     '[skill-discriminator: <rationale>]' for a one-off override.")
    print()
    print(f"See {AUDIT_PATH}")
    print(f"and {ADR_PATH}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _split_changed_arg(values: list[str] | None, env_value: str | None) -> list[str]:
    """Normalize changed-file inputs from CLI args or a whitespace/newline env."""
    if values:
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
        "--pr-body",
        default=os.environ.get("PR_BODY", ""),
        help="PR description text; scanned for the override token (env: PR_BODY).",
    )
    return parser


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

    result = run_check(repo_root, changed, args.pr_body)
    print_report(result)

    return 1 if result.failing else 0


if __name__ == "__main__":
    raise SystemExit(main())
