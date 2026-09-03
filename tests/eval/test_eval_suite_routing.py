# taste-lint: ignore file-size, routing table and its negative controls stay paired.
"""Routing tests for scripts/eval/eval-suite.py (issue #4882).

The bug these pin: `AGENT_PATTERNS` carried a bare `src/copilot-cli/` prefix and
the agent branch ran before the skill branch, so every Markdown file in that
tree was routed to `eval-agents.py`. Measured on pristine
`2628d8c1282277ad39bc605eb6a31131eff2d77e` with
`eval-suite.py --base-ref HEAD~1 --dry-run --scope all`:

    Changed files: 17
    agents: 4 files
    skills: 2 files
    other: 11 files
    Overall: FAIL
    exit 3

`eval-agents.py --agent canonical-source-mirror.instructions` exits 1 with empty
stdout ("ERROR: Agent definition not found"), which `_parse_child_json` turns
into EXIT_EXTERNAL. That is where the exit 3 came from.

Two classes of test here:

  * Behavioral: each supported path shape lands in its category.
  * Structural: no row of ROUTING_RULES can be shadowed by an earlier row, and
    a negative control replays the broad prefix to prove these tests would fail
    if it were reintroduced.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"


def _load_suite():
    added = False
    if str(EVAL_DIR) not in sys.path:
        sys.path.insert(0, str(EVAL_DIR))
        added = True
    try:
        spec = importlib.util.spec_from_file_location(
            "eval_suite_routing", EVAL_DIR / "eval-suite.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if added and str(EVAL_DIR) in sys.path:
            sys.path.remove(str(EVAL_DIR))


suite = _load_suite()


# ---------------------------------------------------------------------------
# Positive routing: every supported artifact type reaches its category
# ---------------------------------------------------------------------------

# The four paths the issue measured as misrouted, plus one representative per
# supported category. Keep the issue's paths verbatim.
ROUTING_CASES = [
    # Misrouted by the pre-fix table (issue #4882 reproduction).
    ("src/copilot-cli/instructions/canonical-source-mirror.instructions.md", "instructions"),
    ("src/copilot-cli/instructions/lsp-first.instructions.md", "instructions"),
    ("src/copilot-cli/skills/context-optimizer/references/model-context-doctrine.md",
     "skill_references"),
    ("src/copilot-cli/skills/context-optimizer/references/rule-audit-procedure.md",
     "skill_references"),
    # Silently dropped into `other` by the pre-fix table.
    (".claude/rules/canonical-source-mirror.md", "rules"),
    (".claude/rules/lsp-first.md", "rules"),
    (".github/instructions/canonical-source-mirror.instructions.md", "instructions"),
    (".github/instructions/lsp-first.instructions.md", "instructions"),
    # Skills.
    ("src/copilot-cli/skills/context-optimizer/SKILL.md", "skills"),
    (".claude/skills/analyze/SKILL.md", "skills"),
    (".claude/skills/analyze/references/deep-dive.md", "skill_references"),
    # Agents, which must keep routing as agents.
    (".claude/agents/implementer.md", "agents"),
    ("src/claude/architect.md", "agents"),
    ("src/copilot-cli/agents/implementer.agent.md", "agents"),
    ("src/vs-code-agents/analyst.agent.md", "agents"),
    # Agent-tree reference material: same failure shape as the skill case.
    ("src/claude/security/references/threat-model-template.md", "references"),
    # Entrypoints.
    ("AGENTS.md", "entrypoints"),
    ("CLAUDE.md", "entrypoints"),
    ("src/copilot-cli/lib/github_core/CLAUDE.md", "entrypoints"),
    # Prompts and scenarios, unchanged by this fix.
    (".claude/commands/spec.md", "prompts"),
    (".github/prompts/pr-quality-gate-architect.md", "prompts"),
    ("tests/evals/rule-scenarios/code-quality.json", "scenarios"),
    # Genuinely unclassified.
    ("src/copilot-cli/docs/copilot-instructions.md", "other"),
    ("scripts/eval/eval-suite.py", "other"),
]


@pytest.mark.parametrize("path,expected", ROUTING_CASES)
def test_classify_path_routes_to_expected_category(path: str, expected: str) -> None:
    assert suite.classify_path(path) == expected


@pytest.mark.parametrize("path,expected", ROUTING_CASES)
def test_classify_changes_agrees_with_classify_path(path: str, expected: str) -> None:
    classified = suite.classify_changes([path])
    assert classified[expected] == [path]


# ---------------------------------------------------------------------------
# Negative routing: nothing that is not an agent may reach eval-agents.py
# ---------------------------------------------------------------------------

NON_AGENT_PATHS = [p for p, category in ROUTING_CASES if category != "agents"]


@pytest.mark.parametrize("path", NON_AGENT_PATHS)
def test_non_agent_paths_never_route_to_the_agent_evaluator(path: str) -> None:
    """AC: skill references and instruction mirrors must not reach eval-agents.py."""
    category = suite.classify_path(path)
    assert category != "agents"
    assert suite.RUNNER_BY_CATEGORY.get(category) != "eval-agents.py"


def test_agent_exclusions_are_preserved() -> None:
    """README/INDEX/template files stay out of the agent category, as before."""
    assert suite.classify_path("src/claude/README.md") == "other"
    assert suite.classify_path(".claude/agents/INDEX.md") == "other"
    assert suite.classify_path(".claude/agents/agent.template.md") == "other"


def test_non_markdown_under_an_agent_tree_is_not_an_agent() -> None:
    assert suite.classify_path("src/claude/.claude-plugin/plugin.json") == "other"


# ---------------------------------------------------------------------------
# Negative control: the broad prefix that caused the bug
# ---------------------------------------------------------------------------

# The pre-fix table, quoted from eval-suite.py at
# 2628d8c1282277ad39bc605eb6a31131eff2d77e:
#
#     AGENT_PATTERNS = [
#         ".claude/agents/",
#         "src/claude/",
#         "src/copilot-cli/",
#         "src/vs-code-agents/",
#     ]
NAIVE_AGENT_PREFIXES = (
    ".claude/agents/",
    "src/claude/",
    "src/copilot-cli/",
    "src/vs-code-agents/",
)

MISROUTED_BY_NAIVE_PREFIX = [
    "src/copilot-cli/instructions/canonical-source-mirror.instructions.md",
    "src/copilot-cli/skills/context-optimizer/references/model-context-doctrine.md",
    "src/copilot-cli/skills/context-optimizer/SKILL.md",
    "src/claude/security/references/threat-model-template.md",
]


@pytest.mark.parametrize("path", MISROUTED_BY_NAIVE_PREFIX)
def test_negative_control_broad_prefix_would_capture_these(path: str) -> None:
    """Prove the broad prefix really does capture non-agents.

    Without this, `test_non_agent_paths_never_route_to_the_agent_evaluator`
    could pass against a table that never had the overlap in the first place.
    """
    assert any(path.startswith(prefix) for prefix in NAIVE_AGENT_PREFIXES)
    assert path.endswith(".md")
    assert Path(path).name not in suite.AGENT_EXCLUDED_BASENAMES


@pytest.mark.parametrize("path", MISROUTED_BY_NAIVE_PREFIX)
def test_shipped_table_does_not_capture_them(path: str) -> None:
    assert suite.classify_path(path) != "agents"


def test_agent_rows_no_longer_carry_the_broad_copilot_prefix() -> None:
    """The specific prefix that caused issue #4882 must not come back."""
    assert "src/copilot-cli/" not in suite.AGENT_PATTERNS
    assert "src/copilot-cli/agents/" in suite.AGENT_PATTERNS


def _classify_with(rules, path: str) -> str:
    for rule in rules:
        if rule.matches(path):
            return rule.category
    return "other"


def test_negative_control_broad_prefix_placed_first_recreates_the_bug() -> None:
    """Ordering is the defense; prove that losing it recreates issue #4882.

    Narrowing AGENT_PATTERNS alone is not what protects skill references and
    instruction mirrors: the rows for those categories sit ahead of the agent
    rows. This control rebuilds the pre-fix table (broad prefix, agent rows
    first) and asserts the exact misroutes the issue measured, so the ordering
    claim above is tested rather than asserted.
    """
    broken = (
        *(
            suite.RoutingRule(
                "agents",
                prefix=prefix,
                exclude_basenames=suite.AGENT_EXCLUDED_BASENAMES,
                exclude_substrings=suite.AGENT_EXCLUDED_SUBSTRINGS,
            )
            for prefix in NAIVE_AGENT_PREFIXES
        ),
        *suite.ROUTING_RULES,
    )

    for path in MISROUTED_BY_NAIVE_PREFIX:
        assert _classify_with(broken, path) == "agents", (
            f"control did not reproduce the misroute for {path}"
        )
        assert suite.classify_path(path) != "agents"


def test_negative_control_reordering_skills_after_agents_breaks_references() -> None:
    """Moving the agent rows ahead of the reference rows misroutes references."""
    agent_rows = tuple(r for r in suite.ROUTING_RULES if r.category == "agents")
    rest = tuple(r for r in suite.ROUTING_RULES if r.category != "agents")
    reordered = (*agent_rows, *rest)

    path = "src/claude/security/references/threat-model-template.md"
    assert _classify_with(reordered, path) == "agents"
    assert suite.classify_path(path) == "references"


# ---------------------------------------------------------------------------
# Structural: ordering, reachability, and category bookkeeping
# ---------------------------------------------------------------------------

# Rows with a filesystem predicate cannot use a synthetic name, because the
# predicate asks the tree a question about it. `spec` is a real command mirror:
# `.claude/commands/spec.md` exists and `.claude/skills/spec/` does not.
PREDICATE_ROW_REPRESENTATIVES = {
    "command_mirrors": "src/copilot-cli/skills/spec/SKILL.md",
}


def _representative_path(rule) -> str:
    """Build a path the rule is meant to claim."""
    if rule.predicate is not None:
        return PREDICATE_ROW_REPRESENTATIVES[rule.category]
    if rule.basenames:
        return f"sample/{sorted(rule.basenames)[0]}"
    segment = f"{rule.segment}/" if rule.segment else ""
    suffix = rule.suffix or ".md"
    return f"{rule.prefix}sample/{segment}sample{suffix}"


@pytest.mark.parametrize(
    "index", range(len(suite.ROUTING_RULES)), ids=lambda i: f"row{i}"
)
def test_no_routing_row_is_shadowed_by_an_earlier_row(index: int) -> None:
    """Ordering invariant: every row wins for its own representative path.

    This is the guard that fails if a broad prefix is moved ahead of a narrow
    one, which is exactly how issue #4882 happened.
    """
    rule = suite.ROUTING_RULES[index]
    path = _representative_path(rule)
    assert rule.matches(path), f"representative path does not match its own row: {path}"
    assert suite.classify_path(path) == rule.category, (
        f"row {index} ({rule.category}, prefix={rule.prefix!r}) is shadowed; "
        f"{path} resolved to {suite.classify_path(path)!r}"
    )


# ---------------------------------------------------------------------------
# Entrypoints are identified by filename, so their row must win over prefixes
# ---------------------------------------------------------------------------

# Every one of these exists in the tree. Behind the prefix rows they were all
# captured as prompts or skills.
SHADOWED_ENTRYPOINTS = [
    ".claude/commands/CLAUDE.md",
    ".claude/skills/CLAUDE.md",
    ".claude/skills/adr-review/CLAUDE.md",
    ".claude/skills/adr-review/scripts/CLAUDE.md",
    ".claude/skills/github/CLAUDE.md",
    ".claude/skills/github/scripts/issue/CLAUDE.md",
    ".claude/skills/memory/CLAUDE.md",
    "src/copilot-cli/skills/adr-review/CLAUDE.md",
    "src/copilot-cli/skills/github/CLAUDE.md",
    ".claude/agents/AGENTS.md",
    ".claude/agents/CLAUDE.md",
]


@pytest.mark.parametrize("path", SHADOWED_ENTRYPOINTS)
def test_entrypoints_inside_prompt_and_skill_trees_are_not_shadowed(path: str) -> None:
    """Exercised through classify_path, not the matcher in isolation.

    The matcher always matched these; the bug was that broader prefix rows ran
    first, so only the full ordered table reproduces it.
    """
    assert suite.classify_path(path) == "entrypoints"


@pytest.mark.parametrize("path", SHADOWED_ENTRYPOINTS)
def test_shadowed_entrypoints_exist_in_the_tree(path: str) -> None:
    """Negative control: these must be real, or the test above proves nothing."""
    assert (REPO_ROOT / path).is_file(), f"{path} is not in the tree"


def test_entrypoint_row_is_first_in_the_table() -> None:
    assert suite.ROUTING_RULES[0].category == "entrypoints"


def test_negative_control_entrypoints_after_prefixes_recreates_the_shadowing() -> None:
    """Move the row back where it was and the misroute returns."""
    entry_row = suite.ROUTING_RULES[0]
    rest = suite.ROUTING_RULES[1:]
    shadowed = (*rest, entry_row)
    assert _classify_with(shadowed, ".claude/commands/CLAUDE.md") == "prompts"
    assert _classify_with(shadowed, ".claude/skills/github/CLAUDE.md") == "skills"
    assert suite.classify_path(".claude/commands/CLAUDE.md") == "entrypoints"


# ---------------------------------------------------------------------------
# Command mirrors: same tree as skills, different generator
# ---------------------------------------------------------------------------

COMMAND_MIRROR_SKILLS = [
    "build", "checkpoint", "context-hub-setup", "plan", "pr-autofix",
    "pr-review", "push-pr", "research", "retro", "ship", "spec", "sync",
    "test", "validate-pr-description",
]


@pytest.mark.parametrize("name", COMMAND_MIRROR_SKILLS)
def test_command_mirror_skills_do_not_route_to_the_skill_evaluator(name: str) -> None:
    """The skill evaluator resolves only .claude/skills/ and exits 1 otherwise."""
    path = f"src/copilot-cli/skills/{name}/SKILL.md"
    assert suite.classify_path(path) == "command_mirrors"
    assert suite.RUNNER_BY_CATEGORY.get("command_mirrors") is None


@pytest.mark.parametrize("name", COMMAND_MIRROR_SKILLS)
def test_command_mirror_premise_holds_in_the_tree(name: str) -> None:
    """Negative control for the premise: no Claude skill, but a Claude command."""
    assert not (REPO_ROOT / ".claude" / "skills" / name).is_dir()
    assert (REPO_ROOT / ".claude" / "commands" / f"{name}.md").is_file()


@pytest.mark.parametrize("name", ["analyze", "github", "review", "planner"])
def test_mirrored_claude_skills_still_route_as_skills(name: str) -> None:
    """The narrowing must not capture ordinary mirrored skills."""
    assert (REPO_ROOT / ".claude" / "skills" / name).is_dir()
    assert suite.classify_path(f"src/copilot-cli/skills/{name}/SKILL.md") == "skills"


def test_command_mirror_predicate_ignores_paths_outside_the_copilot_skill_tree() -> None:
    assert suite.is_command_mirror_skill(".claude/skills/spec/SKILL.md") is False
    assert suite.is_command_mirror_skill("src/copilot-cli/skills") is False
    assert suite.is_command_mirror_skill("README.md") is False


def test_command_mirror_reason_points_at_the_generating_command() -> None:
    reason = suite.NOT_EVALUATED_REASONS["command_mirrors"]
    assert ".claude/commands/" in reason
    assert ".claude/skills/" in reason


def test_references_rows_precede_the_trees_that_contain_them() -> None:
    order = [rule.category for rule in suite.ROUTING_RULES]
    assert order.index("skill_references") < order.index("skills")
    assert order.index("references") < order.index("agents")


def test_instruction_rows_precede_agent_rows() -> None:
    order = [rule.category for rule in suite.ROUTING_RULES]
    assert order.index("instructions") < order.index("agents")


def test_every_category_is_either_routed_or_explicitly_not_evaluated() -> None:
    """Required work item 2: no context-bearing category may fall silently."""
    for category in suite.CATEGORIES:
        routed = category in suite.RUNNER_BY_CATEGORY
        excused = category in suite.NOT_EVALUATED_REASONS
        assert routed != excused, (
            f"{category} must appear in exactly one of RUNNER_BY_CATEGORY "
            f"and NOT_EVALUATED_REASONS"
        )


def test_every_routing_row_names_a_known_category() -> None:
    for rule in suite.ROUTING_RULES:
        assert rule.category in suite.CATEGORIES


def test_classify_changes_returns_every_category_key() -> None:
    classified = suite.classify_changes([])
    assert set(classified) == set(suite.CATEGORIES)


# ---------------------------------------------------------------------------
# RoutingRule matcher edges
# ---------------------------------------------------------------------------

def test_segment_matches_directories_only_not_the_basename() -> None:
    rule = suite.RoutingRule("skill_references", prefix=".claude/skills/", segment="references")
    assert rule.matches(".claude/skills/analyze/references/x.md")
    # A file literally named `references.md` is not a reference directory.
    assert not rule.matches(".claude/skills/analyze/references.md")


def test_empty_suffix_disables_the_suffix_filter() -> None:
    rule = suite.RoutingRule("skills", prefix=".claude/skills/", suffix="")
    assert rule.matches(".claude/skills/analyze/scripts/run.py")


def test_exclusions_reject_before_the_row_claims_the_path() -> None:
    rule = suite.ROUTING_RULES[
        [r.category for r in suite.ROUTING_RULES].index("agents")
    ]
    assert not rule.matches(f"{rule.prefix}README.md")
    assert not rule.matches(f"{rule.prefix}agent.template.md")


def test_empty_prefix_row_matches_at_any_depth() -> None:
    rule = suite.RoutingRule("entrypoints", basenames=frozenset({"AGENTS.md"}))
    assert rule.matches("AGENTS.md")
    assert rule.matches("a/b/c/AGENTS.md")
    assert not rule.matches("a/b/c/OTHER.md")


# ---------------------------------------------------------------------------
# Rule id resolution and scenario lookup
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path,expected",
    [
        (".claude/rules/code-quality.md", "code-quality"),
        (".github/instructions/code-quality.instructions.md", "code-quality"),
        ("src/copilot-cli/instructions/code-quality.instructions.md", "code-quality"),
        (".claude/agents/implementer.md", None),
        ("scripts/eval/eval-suite.py", None),
    ],
)
def test_rule_id_for_path(path: str, expected: str | None) -> None:
    assert suite.rule_id_for_path(path) == expected


def test_instruction_mirrors_resolve_to_the_same_rule_id() -> None:
    """A rule and both of its generated mirrors are one artifact."""
    ids = {
        suite.rule_id_for_path(".claude/rules/universal.md"),
        suite.rule_id_for_path(".github/instructions/universal.instructions.md"),
        suite.rule_id_for_path("src/copilot-cli/instructions/universal.instructions.md"),
    }
    assert ids == {"universal"}


def test_find_rule_scenarios_reads_rule_path_not_the_filename() -> None:
    """Scenario files carrying skill_path must not claim a rule id.

    `tests/evals/rule-scenarios/` holds ADR-088 reference scenarios whose target
    key is `skill_path`. A stem convention would invent rule ids for them.
    """
    scenarios = suite.find_rule_scenarios()
    assert scenarios, "no rule scenarios discovered"
    for rule_id, scenario_path in scenarios.items():
        assert (REPO_ROOT / ".claude" / "rules" / f"{rule_id}.md").is_file(), (
            f"{scenario_path} claims rule id {rule_id!r}, which has no rule file"
        )


def test_known_rule_scenario_is_discovered() -> None:
    scenarios = suite.find_rule_scenarios()
    assert scenarios.get("code-quality") == "tests/evals/rule-scenarios/code-quality.json"


# ---------------------------------------------------------------------------
# Routing plan: three evidence states, no silent categories
# ---------------------------------------------------------------------------

def _plan_for(paths: list[str]) -> list[dict]:
    return suite.build_routing_plan(suite.classify_changes(paths))


def test_plan_marks_a_scenario_backed_rule_as_scenario_defined() -> None:
    entries = _plan_for([".claude/rules/code-quality.md"])
    assert len(entries) == 1
    assert entries[0]["evidence"] == suite.EVIDENCE_SCENARIO
    assert entries[0]["runner"] == "eval-rule-activation.py"


def test_plan_marks_a_scenarioless_rule_as_not_evaluated() -> None:
    entries = _plan_for([".claude/rules/canonical-source-mirror.md"])
    assert len(entries) == 1
    assert entries[0]["evidence"] == suite.EVIDENCE_NONE
    assert entries[0]["runner"] is None
    assert "no activation scenario" in entries[0]["reason"]


def test_plan_splits_scenario_backed_and_scenarioless_rules() -> None:
    entries = _plan_for([
        ".claude/rules/code-quality.md",
        ".claude/rules/canonical-source-mirror.md",
    ])
    by_evidence = {e["evidence"]: e["files"] for e in entries}
    assert by_evidence[suite.EVIDENCE_SCENARIO] == [".claude/rules/code-quality.md"]
    assert by_evidence[suite.EVIDENCE_NONE] == [".claude/rules/canonical-source-mirror.md"]


def test_plan_never_leaves_a_populated_category_without_a_reason() -> None:
    entries = _plan_for([path for path, _ in ROUTING_CASES])
    covered = {e["category"] for e in entries}
    classified = suite.classify_changes([path for path, _ in ROUTING_CASES])
    populated = {k for k, v in classified.items() if v}
    assert populated == covered
    for entry in entries:
        assert entry["reason"]
        assert entry["evidence"] in {
            suite.EVIDENCE_STRUCTURAL,
            suite.EVIDENCE_SCENARIO,
            suite.EVIDENCE_SCORED,
            suite.EVIDENCE_NONE,
        }
        if entry["runner"] is None:
            assert entry["evidence"] == suite.EVIDENCE_NONE


def test_plan_is_deterministic_and_sorted() -> None:
    paths = [path for path, _ in ROUTING_CASES]
    first = _plan_for(paths)
    second = _plan_for(list(reversed(paths)))
    assert first == second
    for entry in first:
        assert entry["files"] == sorted(entry["files"])


def test_plan_follows_category_order() -> None:
    entries = _plan_for([path for path, _ in ROUTING_CASES])
    seen = [e["category"] for e in entries]
    ranks = [suite.CATEGORIES.index(c) for c in seen]
    assert ranks == sorted(ranks)


def test_empty_classification_yields_an_empty_plan() -> None:
    assert suite.build_routing_plan(suite.classify_changes([])) == []


# ---------------------------------------------------------------------------
# find_rule_scenarios: defensive branches
# ---------------------------------------------------------------------------

def _scenario_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    scenario_dir = tmp_path / suite.RULE_SCENARIO_DIR
    scenario_dir.mkdir(parents=True)
    monkeypatch.setattr(suite, "REPO_ROOT", tmp_path)
    return scenario_dir


def test_find_rule_scenarios_returns_empty_when_the_directory_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(suite, "REPO_ROOT", tmp_path)
    assert suite.find_rule_scenarios() == {}


def test_find_rule_scenarios_raises_on_malformed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken scenario file is an authoring bug, not an absent scenario.

    Mirrors `check_rule_activation_coverage.py:_read_scenario_json`, which
    raises CoverageConfigError rather than skipping the file.
    """
    scenario_dir = _scenario_root(tmp_path, monkeypatch)
    (scenario_dir / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(suite.ScenarioConfigError, match="invalid JSON"):
        suite.find_rule_scenarios()


def test_find_rule_scenarios_raises_on_unreadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = _scenario_root(tmp_path, monkeypatch)
    # A directory named *.json satisfies the glob but cannot be read as text.
    (scenario_dir / "adirectory.json").mkdir()
    with pytest.raises(suite.ScenarioConfigError, match="cannot read scenario file"):
        suite.find_rule_scenarios()


def test_find_rule_scenarios_raises_on_a_non_utf8_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """UnicodeDecodeError subclasses ValueError, not OSError.

    An OSError-only guard lets a binary or mis-encoded scenario file escape as
    an unhandled traceback instead of the documented config exit.
    """
    scenario_dir = _scenario_root(tmp_path, monkeypatch)
    (scenario_dir / "binary.json").write_bytes(b'{"rule_path": "\xff\xfe\x00\x81"}')
    with pytest.raises(suite.ScenarioConfigError, match="cannot read scenario file"):
        suite.find_rule_scenarios()


def test_non_utf8_is_not_an_oserror() -> None:
    """Pins the reason the guard needs a second exception type."""
    assert not issubclass(UnicodeDecodeError, OSError)
    assert issubclass(UnicodeDecodeError, ValueError)


def test_find_rule_scenarios_raises_on_a_non_object_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = _scenario_root(tmp_path, monkeypatch)
    (scenario_dir / "case.json").write_text('["not", "an", "object"]', encoding="utf-8")
    with pytest.raises(suite.ScenarioConfigError, match="must contain an object"):
        suite.find_rule_scenarios()


# Only the real ADR-088 shape is a legitimate skip. The canonical test is
# `check_rule_activation_coverage.py:_is_reference_scenario`:
#
#     has_reference = isinstance(reference, str) and bool(reference.strip())
#     has_skill = isinstance(skill, str) and bool(skill.strip())
#     has_rule = isinstance(rule, str) and bool(rule.strip())
#     if not (has_reference and has_skill and not has_rule):
#         return False
#
# so an empty object, a lone skill_path, a lone reference_path, and a blank or
# non-string rule_path are all malformed rather than reference scenarios.
@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"skill_path": ".claude/skills/analyze/SKILL.md"}',
        '{"reference_path": ".claude/skills/analyze/references/x.md"}',
        '{"skill_path": "   ", "reference_path": "   "}',
        '{"skill_path": ".claude/skills/analyze/SKILL.md", "reference_path": ""}',
        '{"rule_path": ""}',
        '{"rule_path": "   "}',
        '{"rule_path": 42}',
        '{"rule_path": null, "skill_path": ".claude/skills/analyze/SKILL.md"}',
    ],
    ids=[
        "empty_object",
        "lone_skill_path",
        "lone_reference_path",
        "blank_both",
        "blank_reference",
        "empty_rule_path",
        "blank_rule_path",
        "rule_path_not_a_string",
        "null_rule_path_lone_skill",
    ],
)
def test_malformed_scenarios_are_not_treated_as_reference_scenarios(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    scenario_dir = _scenario_root(tmp_path, monkeypatch)
    (scenario_dir / "case.json").write_text(payload, encoding="utf-8")
    with pytest.raises(suite.ScenarioConfigError):
        suite.find_rule_scenarios()


def test_a_real_adr_088_reference_scenario_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-empty skill_path AND reference_path, no rule_path: a valid skip."""
    scenario_dir = _scenario_root(tmp_path, monkeypatch)
    (scenario_dir / "ref.json").write_text(
        json.dumps({
            "skill_path": ".claude/skills/analyze/SKILL.md",
            "reference_path": ".claude/skills/analyze/references/x.md",
        }),
        encoding="utf-8",
    )
    assert suite.find_rule_scenarios() == {}


def test_the_repositorys_own_scenarios_all_satisfy_the_stricter_shape() -> None:
    """The tightened check must not reject any scenario already in the tree."""
    scenarios = suite.find_rule_scenarios()
    assert scenarios, "no rule scenarios discovered"


def test_find_rule_scenarios_reads_a_valid_rule_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = _scenario_root(tmp_path, monkeypatch)
    (scenario_dir / "good.json").write_text(
        '{"rule_path": ".claude/rules/good.md"}', encoding="utf-8"
    )
    assert suite.find_rule_scenarios() == {
        "good": f"{suite.RULE_SCENARIO_DIR}/good.json"
    }


# ---------------------------------------------------------------------------
# Dry-run output surface
# ---------------------------------------------------------------------------

def test_print_routing_plan_reports_nothing_to_route(
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite._print_routing_plan([])
    assert "(nothing to route)" in capsys.readouterr().err


def test_print_routing_plan_names_category_runner_evidence_and_files(
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite._print_routing_plan(_plan_for([".claude/rules/code-quality.md"]))
    err = capsys.readouterr().err
    assert "rules" in err
    assert "eval-rule-activation.py" in err
    assert suite.EVIDENCE_SCENARIO in err
    assert ".claude/rules/code-quality.md" in err


def test_print_routing_plan_shows_none_for_unrouted_categories(
    capsys: pytest.CaptureFixture[str],
) -> None:
    suite._print_routing_plan(_plan_for(["AGENTS.md"]))
    err = capsys.readouterr().err
    assert "(none)" in err
    assert suite.EVIDENCE_NONE in err
    assert suite.NOT_EVALUATED_REASONS["entrypoints"] in err


# ---------------------------------------------------------------------------
# run_rule_activation: reuses eval-rule-activation.py, never invents a harness
# ---------------------------------------------------------------------------

class _FakeCompleted:
    def __init__(self, stdout: str, returncode: int) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


# The real child prints a human table to stdout. Any mock that returns JSON on
# stdout encodes the imagined contract that shipped the first version of this
# runner; keep the stub faithful to
# `scripts/eval/eval-rule-activation.py:2450-2452`.
_CHILD_STDOUT = "code-quality  activation 4.2  citation 3.9\n\nWrote results: /tmp/x.json\n"


def _output_path_from(cmd: list[str]) -> Path | None:
    if "--output" not in cmd:
        return None
    return Path(cmd[cmd.index("--output") + 1])


# A scored run, shaped like the real child's output. The verdict path is set by
# `scripts/eval/eval-rule-activation.py:_process_scenario_file`:
#
#     all_results["rules"][rule_id] = result
#     state.worst_exit = max(state.worst_exit, _classify_verdict(result["summary"]["verdict"]))
#
# The default must carry a verdict. An earlier default of `{"rules": {}}`
# certified that "child produced zero verdicts" was a passing, scored shape,
# which is the bug that shape is now a negative test for.
_SCORED_PAYLOAD = json.dumps({
    "schema_version": 1,
    "model_id": "test-model",
    "rules": {"code-quality": {"summary": {"verdict": "PASS"}}},
})

_NO_VERDICT_PAYLOAD = '{"schema_version": 1, "rules": {}}'


def _stub_child(
    monkeypatch: pytest.MonkeyPatch,
    file_payload: str | None = _SCORED_PAYLOAD,
    returncode: int = 0,
) -> list[list[str]]:
    """Replace subprocess.run with a stub that honors the --output contract.

    `file_payload=None` simulates a child that writes no results file.
    """
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        target = _output_path_from(list(cmd))
        if target is not None and file_payload is not None:
            target.write_text(file_payload, encoding="utf-8")
        return _FakeCompleted(_CHILD_STDOUT, returncode)

    monkeypatch.setattr(suite.subprocess, "run", fake_run)
    return calls


def test_run_rule_activation_scores_a_scenario_backed_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_child(monkeypatch)
    result = suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")

    assert result["passed"] is True
    entry = result["rules"]["code-quality"]
    assert entry["evidence"] == suite.EVIDENCE_SCORED
    assert entry["exit_code"] == 0
    assert len(calls) == 1
    assert "eval-rule-activation.py" in calls[0][1]
    assert "--scenarios" in calls[0]
    assert "tests/evals/rule-scenarios/code-quality.json" in calls[0]
    # The results contract: JSON comes from --output, never stdout.
    assert "--output" in calls[0]
    assert "--dry-run" not in calls[0]


def test_run_rule_activation_reads_results_from_the_output_file_not_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the imagined-contract bug this runner shipped with.

    The child prints a table to stdout and serializes JSON only to --output.
    A runner that parsed stdout would fail on every real run.
    """
    _stub_child(monkeypatch)
    result = suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")
    entry = result["rules"]["code-quality"]
    assert entry["results"]["rules"]["code-quality"]["summary"]["verdict"] == "PASS"
    assert entry["passed"] is True


# ---------------------------------------------------------------------------
# Parseable is not scored: the verdict must actually be present
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload,ids",
    [
        (_NO_VERDICT_PAYLOAD, "empty_rules_map"),
        ('{"schema_version": 1}', "no_rules_key"),
        ('{"rules": []}', "rules_not_a_map"),
        ('{"rules": {"other-rule": {"summary": {"verdict": "PASS"}}}}', "wrong_rule_id"),
        ('{"rules": {"code-quality": "not an object"}}', "entry_not_object"),
        ('{"rules": {"code-quality": {}}}', "no_summary"),
        ('{"rules": {"code-quality": {"summary": {}}}}', "no_verdict"),
        ('{"rules": {"code-quality": {"summary": {"verdict": ""}}}}', "blank_verdict"),
        ('{"rules": {"code-quality": {"summary": {"verdict": 5}}}}', "verdict_not_string"),
    ],
    ids=lambda v: v if isinstance(v, str) and " " not in v and "{" not in v else "",
)
def test_a_parseable_payload_without_a_verdict_is_not_scored(
    monkeypatch: pytest.MonkeyPatch, payload: str, ids: str
) -> None:
    """Valid JSON naming no verdict must not read as scored efficacy evidence."""
    _stub_child(monkeypatch, file_payload=payload, returncode=0)
    entry = suite.run_rule_activation(
        [".claude/rules/code-quality.md"], "test-model"
    )["rules"]["code-quality"]
    assert entry["passed"] is False, ids
    assert entry["evidence"] == suite.EVIDENCE_SCENARIO, ids
    assert entry["exit_code"] == suite.EXIT_EXTERNAL, ids


def test_a_present_verdict_is_scored_even_when_it_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        {"rules": {"code-quality": {"summary": {"verdict": "FAIL"}}}}
    )
    _stub_child(monkeypatch, file_payload=payload, returncode=1)
    entry = suite.run_rule_activation(
        [".claude/rules/code-quality.md"], "test-model"
    )["rules"]["code-quality"]
    assert entry["evidence"] == suite.EVIDENCE_SCORED
    assert entry["passed"] is False
    assert entry["exit_code"] == 1


# ---------------------------------------------------------------------------
# Exit-code precedence: keep the child's own refusal code
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "child_exit,expected",
    [
        (suite.EXIT_CONFIG, suite.EXIT_CONFIG),
        (suite.EXIT_AUTH, suite.EXIT_AUTH),
        (suite.EXIT_LOGIC, suite.EXIT_LOGIC),
        (suite.EXIT_EXTERNAL, suite.EXIT_EXTERNAL),
        # Claimed success and wrote nothing: that IS an external failure.
        (suite.EXIT_OK, suite.EXIT_EXTERNAL),
    ],
    ids=["config", "auth", "logic", "external", "silent_success"],
)
def test_child_refusal_code_survives_a_missing_results_file(
    monkeypatch: pytest.MonkeyPatch, child_exit: int, expected: int
) -> None:
    """The child exits 2 on a bad scenario and 4 on a missing key, writing no
    file in either case. Flattening those to 3 would report an API failure for
    a config or auth fault."""
    _stub_child(monkeypatch, file_payload=None, returncode=child_exit)
    entry = suite.run_rule_activation(
        [".claude/rules/code-quality.md"], "test-model"
    )["rules"]["code-quality"]
    assert entry["exit_code"] == expected


def test_worst_exit_code_keeps_the_most_specific_child_code() -> None:
    results = {
        "agents": {"agents": {"a": {"exit_code": suite.EXIT_EXTERNAL}}},
        "rules": {"rules": {"r": {"exit_code": suite.EXIT_AUTH}}},
    }
    assert suite.worst_exit_code(results, any_failure=True) == suite.EXIT_AUTH


def test_worst_exit_code_is_ok_without_failure() -> None:
    results = {"rules": {"rules": {"r": {"exit_code": suite.EXIT_AUTH}}}}
    assert suite.worst_exit_code(results, any_failure=False) == suite.EXIT_OK


def test_worst_exit_code_floors_at_logic_when_no_code_was_recorded() -> None:
    assert suite.worst_exit_code({"skills": {"passed": False}}, True) == suite.EXIT_LOGIC


def test_worst_exit_code_ignores_zero_codes() -> None:
    results = {"rules": {"rules": {"r": {"exit_code": suite.EXIT_OK}}}}
    assert suite.worst_exit_code(results, any_failure=True) == suite.EXIT_LOGIC


def test_worst_exit_code_walks_into_lists() -> None:
    """`behavioral` results are a list, so codes nest inside one."""
    results = {"behavioral": [{"exit_code": suite.EXIT_CONFIG}, {"skipped": True}]}
    assert suite.worst_exit_code(results, any_failure=True) == suite.EXIT_CONFIG


def test_worst_exit_code_ignores_non_integer_codes() -> None:
    results = {"rules": {"rules": {"r": {"exit_code": "not an int"}}}}
    assert suite.worst_exit_code(results, any_failure=True) == suite.EXIT_LOGIC


def test_verdict_error_rejects_a_non_object_payload() -> None:
    assert "not an object" in (suite._verdict_error(None, "code-quality") or "")


def test_verdict_error_accepts_a_well_formed_payload() -> None:
    payload = {"rules": {"code-quality": {"summary": {"verdict": "PASS"}}}}
    assert suite._verdict_error(payload, "code-quality") is None


def test_run_rule_activation_fails_when_no_results_file_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit 0 with no results file must not read as a pass."""
    _stub_child(monkeypatch, file_payload=None, returncode=0)
    result = suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")
    entry = result["rules"]["code-quality"]
    assert entry["passed"] is False
    assert entry["exit_code"] == suite.EXIT_EXTERNAL
    assert entry["evidence"] == suite.EVIDENCE_SCENARIO
    assert "no results file" in entry["results"]["error"]


def test_run_rule_activation_marks_a_failing_run_as_scored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verdict that ran and failed is still scored evidence."""
    _stub_child(monkeypatch, returncode=1)
    result = suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")
    entry = result["rules"]["code-quality"]
    assert entry["passed"] is False
    assert entry["evidence"] == suite.EVIDENCE_SCORED


def test_run_rule_activation_dedupes_a_rule_and_its_two_mirrors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rule and both generated mirrors are one artifact, so one invocation."""
    calls = _stub_child(monkeypatch)
    result = suite.run_rule_activation(
        [
            ".claude/rules/code-quality.md",
            ".github/instructions/code-quality.instructions.md",
            "src/copilot-cli/instructions/code-quality.instructions.md",
        ],
        "test-model",
    )
    assert len(calls) == 1
    assert set(result["rules"]) == {"code-quality"}


def test_run_rule_activation_reports_a_scenarioless_rule_as_not_evaluated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_child(monkeypatch)
    result = suite.run_rule_activation(
        [".claude/rules/canonical-source-mirror.md"], "test-model"
    )
    entry = result["rules"]["canonical-source-mirror"]
    assert entry["skipped"] is True
    assert entry["evidence"] == suite.EVIDENCE_NONE
    assert "no activation scenario" in entry["reason"]
    assert calls == []
    # A skipped rule must not flip the verdict to failure.
    assert result["passed"] is True


def test_run_rule_activation_reports_an_unresolvable_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_child(monkeypatch)
    result = suite.run_rule_activation(["scripts/eval/eval-suite.py"], "test-model")
    entry = result["rules"]["scripts/eval/eval-suite.py"]
    assert entry["skipped"] is True
    assert entry["evidence"] == suite.EVIDENCE_NONE


def test_run_rule_activation_fails_when_the_child_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_child(monkeypatch, returncode=1)
    result = suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")
    assert result["passed"] is False
    assert result["rules"]["code-quality"]["exit_code"] == 1


def test_run_rule_activation_maps_unparseable_results_to_external(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_child(monkeypatch, file_payload="not json at all", returncode=0)
    result = suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")
    entry = result["rules"]["code-quality"]
    assert entry["exit_code"] == suite.EXIT_EXTERNAL
    assert entry["evidence"] == suite.EVIDENCE_SCENARIO
    assert "error" in entry["results"]
    assert suite._contains_external_failure(result) is True


def test_run_rule_activation_rejects_non_object_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_child(monkeypatch, file_payload='["a", "list"]', returncode=0)
    entry = suite.run_rule_activation(
        [".claude/rules/code-quality.md"], "test-model"
    )["rules"]["code-quality"]
    assert entry["exit_code"] == suite.EXIT_EXTERNAL


def test_run_rule_activation_handles_a_child_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd, **_kwargs):
        raise suite.subprocess.TimeoutExpired(cmd, 600)

    monkeypatch.setattr(suite.subprocess, "run", fake_run)
    result = suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")
    assert result["passed"] is False
    entry = result["rules"]["code-quality"]
    assert entry["reason"] == "timeout (600s)"
    # A timeout is an external failure: the evaluator never ran to completion,
    # so there is no logic verdict to report.
    assert entry["exit_code"] == suite.EXIT_EXTERNAL


def test_a_timed_out_child_reduces_to_exit_external(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The top-level code, not just the reason string.

    Without an explicit code the timeout fell through worst_exit_code's
    no-code default and surfaced as exit 1, reporting a content failure for an
    evaluator that never finished.
    """
    def fake_run(cmd, **_kwargs):
        raise suite.subprocess.TimeoutExpired(cmd, 600)

    monkeypatch.setattr(suite.subprocess, "run", fake_run)
    results = {"rules": suite.run_rule_activation(
        [".claude/rules/code-quality.md"], "test-model"
    )}
    assert suite.worst_exit_code(results, any_failure=True) == suite.EXIT_EXTERNAL


def test_every_timeout_path_records_an_external_exit_code() -> None:
    """All five runners, not just the one review flagged.

    `worst_exit_code` consumes every runner's records, so a sibling timeout
    without a code would surface as exit 1 through the same default.
    """
    source = (EVAL_DIR / "eval-suite.py").read_text(encoding="utf-8")
    timeout_blocks = source.count('"reason": "timeout (')
    assert timeout_blocks == 5, f"expected 5 timeout records, found {timeout_blocks}"
    for line_no, line in enumerate(source.splitlines(), start=1):
        if '"reason": "timeout (' not in line:
            continue
        window = source.splitlines()[max(0, line_no - 4):line_no]
        assert any("EXIT_EXTERNAL" in w for w in window), (
            f"timeout record at line {line_no} has no explicit exit code"
        )


def test_run_rule_activation_on_no_files_is_vacuously_passing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_child(monkeypatch)
    result = suite.run_rule_activation([], "test-model")
    assert result == {"rules": {}, "passed": True}
    assert calls == []


def test_run_rule_activation_pins_utf8_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matches the constraint tests/eval/test_eval_prompt_change.py enforces."""
    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return _FakeCompleted('{"ok": true}', 0)

    monkeypatch.setattr(suite.subprocess, "run", fake_run)
    suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")
    assert seen["encoding"] == "utf-8"
    assert seen["errors"] == "replace"
    assert seen["capture_output"] is True


# ---------------------------------------------------------------------------
# Real child CLI contract (no mock)
# ---------------------------------------------------------------------------

def _run_child(args: list[str], tmp_path: Path):
    import os
    import subprocess as _subprocess

    return _subprocess.run(
        [sys.executable, str(EVAL_DIR / "eval-rule-activation.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(EVAL_DIR)},
    )


def test_child_cli_does_not_emit_json_on_stdout() -> None:
    """The contract the first version of this runner got wrong.

    `eval-rule-activation.py` prints a human table to stdout and serializes
    JSON only to `--output`. This runs the real CLI to prove it, so the mock
    above cannot drift back to the imagined stdout-JSON contract.
    """
    import json as _json

    proc = _run_child(
        ["--scenarios", "tests/evals/rule-scenarios/code-quality.json", "--dry-run"],
        REPO_ROOT,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip(), "child produced no stdout at all"
    with pytest.raises(_json.JSONDecodeError):
        _json.loads(proc.stdout)


def test_child_cli_writes_no_results_file_during_dry_run(tmp_path: Path) -> None:
    """Why the suite never passes --dry-run to this child.

    The child returns before the --output write, so a dry run yields no
    results file. The suite short circuits its own dry run instead.
    """
    out = tmp_path / "results.json"
    proc = _run_child(
        [
            "--scenarios", "tests/evals/rule-scenarios/code-quality.json",
            "--dry-run", "--output", str(out),
        ],
        tmp_path,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert not out.exists()


def test_suite_invokes_the_child_with_output_and_without_dry_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ties the runner's argv to the contract the two tests above measured."""
    calls = _stub_child(monkeypatch)
    suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")
    argv = calls[0]
    assert "--output" in argv
    assert "--dry-run" not in argv
    assert argv[argv.index("--output") + 1].endswith(".json")


# ---------------------------------------------------------------------------
# _run_evals wiring
# ---------------------------------------------------------------------------

class _Args:
    def __init__(self, scope: str) -> None:
        self.scope = scope
        self.dry_run = False
        self.model = "test-model"
        self.base_ref = "main"


def _record_runners(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}

    def fake_skill(skills, _model, _dry_run):
        seen["skills"] = list(skills)
        return {"passed": True}

    def fake_rules(files, _model):
        seen["rules"] = list(files)
        return {"passed": True}

    def fake_agents(agents, _model, _dry_run):
        seen["agents"] = list(agents)
        return {"passed": True}

    monkeypatch.setattr(suite, "run_skill_knowledge", fake_skill)
    monkeypatch.setattr(suite, "run_rule_activation", fake_rules)
    monkeypatch.setattr(suite, "run_agent_quality", fake_agents)
    return seen


def test_run_evals_sends_skill_references_to_the_skill_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _record_runners(monkeypatch)
    classified = suite.classify_changes([
        ".claude/skills/analyze/SKILL.md",
        "src/copilot-cli/skills/context-optimizer/references/model-context-doctrine.md",
    ])
    suite._run_evals(classified, _Args("all"))
    assert seen["skills"] == [
        ".claude/skills/analyze/SKILL.md",
        "src/copilot-cli/skills/context-optimizer/references/model-context-doctrine.md",
    ]
    assert "agents" not in seen


def test_run_evals_sends_rules_and_instructions_to_the_rule_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _record_runners(monkeypatch)
    classified = suite.classify_changes([
        ".claude/rules/code-quality.md",
        "src/copilot-cli/instructions/code-quality.instructions.md",
    ])
    suite._run_evals(classified, _Args("all"))
    assert seen["rules"] == [
        ".claude/rules/code-quality.md",
        "src/copilot-cli/instructions/code-quality.instructions.md",
    ]


def test_rules_scope_runs_rules_only(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _record_runners(monkeypatch)
    classified = suite.classify_changes([
        ".claude/rules/code-quality.md",
        ".claude/agents/implementer.md",
    ])
    suite._run_evals(classified, _Args("rules"))
    assert "rules" in seen
    assert "agents" not in seen


def test_agents_scope_does_not_run_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _record_runners(monkeypatch)
    classified = suite.classify_changes([
        ".claude/rules/code-quality.md",
        ".claude/agents/implementer.md",
    ])
    suite._run_evals(classified, _Args("agents"))
    assert "agents" in seen
    assert "rules" not in seen


def test_run_evals_propagates_a_rule_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(suite, "run_rule_activation", lambda *_: {"passed": False})
    classified = suite.classify_changes([".claude/rules/code-quality.md"])
    _results, any_failure = suite._run_evals(classified, _Args("all"))
    assert any_failure is True


def test_run_evals_propagates_a_skill_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(suite, "run_skill_knowledge", lambda *_: {"passed": False})
    classified = suite.classify_changes([".claude/skills/analyze/SKILL.md"])
    _results, any_failure = suite._run_evals(classified, _Args("all"))
    assert any_failure is True


def test_run_evals_reports_no_failure_when_every_runner_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_runners(monkeypatch)
    classified = suite.classify_changes([
        ".claude/rules/code-quality.md",
        ".claude/skills/analyze/SKILL.md",
        ".claude/agents/implementer.md",
    ])
    _results, any_failure = suite._run_evals(classified, _Args("all"))
    assert any_failure is False


def test_rules_is_an_accepted_scope_value() -> None:
    source = (EVAL_DIR / "eval-suite.py").read_text(encoding="utf-8")
    assert '"prompts", "agents", "skills", "rules", "all"' in source


# ---------------------------------------------------------------------------
# Scope: the dry-run plan must describe what THIS invocation will do
# ---------------------------------------------------------------------------

SCOPED_PATHS = [
    ".claude/commands/spec.md",
    ".claude/agents/implementer.md",
    ".claude/skills/analyze/SKILL.md",
    ".claude/rules/code-quality.md",
]


@pytest.mark.parametrize(
    "scope,expected_runner_categories",
    [
        ("all", {"prompts", "agents", "skills", "rules"}),
        ("prompts", {"prompts"}),
        ("agents", {"agents"}),
        ("skills", {"skills"}),
        ("rules", {"rules"}),
    ],
)
def test_plan_reports_only_in_scope_categories_as_routed(
    scope: str, expected_runner_categories: set[str]
) -> None:
    plan = suite.build_routing_plan(suite.classify_changes(SCOPED_PATHS), scope)
    routed = {e["category"] for e in plan if e["runner"] is not None}
    assert routed == expected_runner_categories


@pytest.mark.parametrize("scope", ["prompts", "agents", "skills", "rules"])
def test_out_of_scope_categories_say_why(scope: str) -> None:
    plan = suite.build_routing_plan(suite.classify_changes(SCOPED_PATHS), scope)
    for entry in plan:
        if entry["runner"] is None and entry["category"] in suite.SCOPE_BY_CATEGORY:
            assert entry["evidence"] == suite.EVIDENCE_NONE
            assert entry["reason"] == f"excluded by --scope {scope}"


def test_plan_scope_gate_matches_run_evals_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plan must not promise work the real path skips.

    Runs both sides for every scope and asserts they agree on which
    runner-backed categories are active.
    """
    for scope in ("all", "prompts", "agents", "skills", "rules"):
        seen = _record_runners(monkeypatch)
        classified = suite.classify_changes(SCOPED_PATHS)
        suite._run_evals(classified, _Args(scope))
        planned = {
            e["category"] for e in suite.build_routing_plan(classified, scope)
            if e["runner"] is not None
        }
        # _run_evals reports skills and prompts under one key each.
        actually_ran = set(seen)
        planned_runners = {
            "skills" if c in ("skills", "skill_references") else
            "rules" if c in ("rules", "instructions") else c
            for c in planned
        }
        assert planned_runners - {"prompts"} == actually_ran - {"prompts"}, (
            f"scope {scope}: plan says {planned_runners}, _run_evals ran {actually_ran}"
        )


def test_category_in_scope_rejects_categories_with_no_runner() -> None:
    for category in ("entrypoints", "references", "scenarios", "other"):
        assert suite.category_in_scope(category, "all") is False


# ---------------------------------------------------------------------------
# Reconciliation: the published plan must match what actually happened
# ---------------------------------------------------------------------------

def test_reconcile_promotes_an_evaluated_rule_to_scored() -> None:
    plan = suite.build_routing_plan(
        suite.classify_changes([".claude/rules/code-quality.md"]), "all"
    )
    assert plan[0]["evidence"] == suite.EVIDENCE_SCENARIO

    results = {
        "rules": {
            "rules": {
                "code-quality": {
                    "passed": True,
                    "exit_code": 0,
                    "evidence": suite.EVIDENCE_SCORED,
                }
            }
        }
    }
    reconciled = suite.reconcile_routing_plan(plan, results)
    assert reconciled[0]["evidence"] == suite.EVIDENCE_SCORED


def test_reconcile_counts_a_failing_run_as_scored() -> None:
    """Scored means a verdict exists, not that the verdict was positive."""
    plan = suite.build_routing_plan(
        suite.classify_changes([".claude/rules/code-quality.md"]), "all"
    )
    results = {
        "rules": {
            "rules": {
                "code-quality": {
                    "passed": False,
                    "exit_code": 1,
                    "evidence": suite.EVIDENCE_SCORED,
                }
            }
        }
    }
    assert suite.reconcile_routing_plan(plan, results)[0]["evidence"] == (
        suite.EVIDENCE_SCORED
    )


def test_reconcile_leaves_a_skipped_rule_unscored() -> None:
    plan = suite.build_routing_plan(
        suite.classify_changes([".claude/rules/code-quality.md"]), "all"
    )
    results = {
        "rules": {"rules": {"code-quality": {"skipped": True, "reason": "no scenario"}}}
    }
    assert suite.reconcile_routing_plan(plan, results)[0]["evidence"] == (
        suite.EVIDENCE_SCENARIO
    )


@pytest.mark.parametrize(
    "outcome,label",
    [
        ({"passed": False, "reason": "timeout (600s)"}, "timeout"),
        (
            {
                "passed": False,
                "exit_code": 3,
                "evidence": "scenario_defined_not_scored",
                "results": {"error": "no results file"},
            },
            "missing_verdict",
        ),
        ({"passed": True}, "passed_without_evidence_label"),
    ],
    ids=["timeout", "missing_verdict", "passed_without_evidence_label"],
)
def test_reconcile_never_promotes_a_run_that_produced_no_verdict(
    outcome: dict, label: str
) -> None:
    """Promotion must key on the evidence label, not on `passed`.

    `passed` is False for a failing verdict, a timeout, and an unreadable
    result alike, so inferring from it would publish scored efficacy evidence
    for runs that produced none.
    """
    plan = suite.build_routing_plan(
        suite.classify_changes([".claude/rules/code-quality.md"]), "all"
    )
    results = {"rules": {"rules": {"code-quality": outcome}}}
    assert suite.reconcile_routing_plan(plan, results)[0]["evidence"] == (
        suite.EVIDENCE_SCENARIO
    ), label


def test_reconcile_leaves_a_scenarioless_rule_entry_untouched() -> None:
    """A rules entry already at not_evaluated has nothing to promote."""
    plan = suite.build_routing_plan(
        suite.classify_changes([".claude/rules/canonical-source-mirror.md"]), "all"
    )
    assert plan[0]["evidence"] == suite.EVIDENCE_NONE
    results = {"rules": {"rules": {"code-quality": {"passed": True}}}}
    assert suite.reconcile_routing_plan(plan, results) == plan


def test_reconcile_splits_a_mixed_entry_into_scored_and_unscored() -> None:
    """Two scenario-backed rules where only one actually ran."""
    plan = [{
        "category": "rules",
        "files": [".claude/rules/code-quality.md", ".claude/rules/universal.md"],
        "runner": "eval-rule-activation.py",
        "evidence": suite.EVIDENCE_SCENARIO,
        "reason": "activation scenario defined; run without --dry-run to score",
    }]
    results = {
        "rules": {
            "rules": {
                "code-quality": {
                    "passed": True,
                    "exit_code": 0,
                    "evidence": suite.EVIDENCE_SCORED,
                }
            }
        }
    }
    reconciled = suite.reconcile_routing_plan(plan, results)
    by_evidence = {e["evidence"]: e["files"] for e in reconciled}
    assert by_evidence[suite.EVIDENCE_SCORED] == [".claude/rules/code-quality.md"]
    assert by_evidence[suite.EVIDENCE_SCENARIO] == [".claude/rules/universal.md"]


def test_reconcile_is_a_noop_without_rule_results() -> None:
    plan = suite.build_routing_plan(suite.classify_changes(SCOPED_PATHS), "all")
    assert suite.reconcile_routing_plan(plan, {}) == plan


def test_reconcile_leaves_non_rule_categories_alone() -> None:
    plan = suite.build_routing_plan(
        suite.classify_changes([".claude/agents/implementer.md"]), "all"
    )
    results = {"rules": {"rules": {"code-quality": {"passed": True}}}}
    assert suite.reconcile_routing_plan(plan, results) == plan


# ---------------------------------------------------------------------------
# End to end: the dry run the issue reproduced
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> None:
    import subprocess as _subprocess

    _subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _build_fixture_repo(tmp_path: Path) -> Path:
    """A throwaway repo with a base commit and one changed file per category.

    Built rather than reusing this checkout: a clean CI checkout has no diff
    against HEAD, so a test pointed at the real repo skips itself and never
    exercises the path it claims to cover.
    """
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")

    tracked = {
        ".claude/agents/implementer.md": "base agent\n",
        ".claude/skills/analyze/SKILL.md": "base skill\n",
        "src/copilot-cli/skills/analyze/references/deep.md": "base reference\n",
        "src/copilot-cli/instructions/code-quality.instructions.md": "base mirror\n",
        ".claude/rules/code-quality.md": "base rule\n",
        "AGENTS.md": "base entrypoint\n",
        "unrelated.txt": "base other\n",
    }
    for rel, body in tracked.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")

    # Change every tracked artifact so each category is populated.
    for rel in tracked:
        (repo / rel).write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "change every artifact")
    return repo


def _run_suite_in(repo: Path, *args: str):
    """Run the suite against a fixture repo by pointing REPO_ROOT at it."""
    import os
    import subprocess as _subprocess

    runner = (
        "import importlib.util,sys;"
        f"spec=importlib.util.spec_from_file_location('es',{str(EVAL_DIR / 'eval-suite.py')!r});"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        f"m.REPO_ROOT=__import__('pathlib').Path({str(repo)!r});"
        "sys.argv=['eval-suite']+sys.argv[1:];m.main()"
    )
    return _subprocess.run(
        [sys.executable, "-c", runner, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=str(repo),
        env={**os.environ, "PYTHONPATH": str(EVAL_DIR)},
    )


def test_dry_run_over_a_real_diff_exits_zero_with_a_populated_plan(
    tmp_path: Path,
) -> None:
    """AC: a dry run exits successfully and prints a deterministic routing plan.

    Pre-fix this exited 3, because misrouted files reached the agent evaluator,
    which exits 1 with empty stdout. A dry run now invokes no evaluator at all.
    """
    import json as _json

    repo = _build_fixture_repo(tmp_path)
    proc = _run_suite_in(repo, "--base-ref", "HEAD~1", "--dry-run")

    assert proc.returncode == 0, proc.stderr[-3000:]
    payload = _json.loads(proc.stdout)

    assert payload["dry_run"] is True
    assert payload["passed"] is True
    assert payload["results"] == {}, "a dry run must invoke no evaluator"
    assert "JSON parse failed" not in proc.stderr

    plan = payload["routing_plan"]
    assert plan, "fixture diff produced an empty routing plan"
    by_category = {e["category"]: e for e in plan}
    for expected in ("agents", "skills", "skill_references", "instructions", "rules"):
        assert expected in by_category, f"{expected} missing from plan: {list(by_category)}"

    # The four paths issue #4882 misrouted must not be under `agents`.
    assert by_category["agents"]["files"] == [".claude/agents/implementer.md"]

    for entry in plan:
        assert entry["reason"]
        assert entry["files"] == sorted(entry["files"])


def test_dry_run_plan_honors_scope_over_a_real_diff(tmp_path: Path) -> None:
    import json as _json

    repo = _build_fixture_repo(tmp_path)
    proc = _run_suite_in(repo, "--base-ref", "HEAD~1", "--dry-run", "--scope", "agents")

    assert proc.returncode == 0, proc.stderr[-3000:]
    plan = _json.loads(proc.stdout)["routing_plan"]
    routed = {e["category"] for e in plan if e["runner"] is not None}
    assert routed == {"agents"}
    for entry in plan:
        if entry["category"] in ("rules", "skills") and entry["runner"] is None:
            assert entry["reason"] == "excluded by --scope agents"


def test_dry_run_exits_config_on_a_malformed_scenario_file(tmp_path: Path) -> None:
    """A broken scenario file must stop the run, not read as 'no scenario'.

    Exit 2 is EXIT_CONFIG, matching the canonical coverage checker's exit code
    for a scenario-file fault.
    """
    repo = _build_fixture_repo(tmp_path)
    scenario_dir = repo / "tests" / "evals" / "rule-scenarios"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "broken.json").write_text("{not json", encoding="utf-8")

    proc = _run_suite_in(repo, "--base-ref", "HEAD~1", "--dry-run")
    assert proc.returncode == 2, (proc.returncode, proc.stdout[-500:], proc.stderr[-2000:])
    assert "invalid JSON in scenario file" in proc.stderr


def test_dry_run_is_deterministic_across_runs(tmp_path: Path) -> None:
    import json as _json

    repo = _build_fixture_repo(tmp_path)
    first = _run_suite_in(repo, "--base-ref", "HEAD~1", "--dry-run")
    second = _run_suite_in(repo, "--base-ref", "HEAD~1", "--dry-run")
    assert first.returncode == 0 and second.returncode == 0
    assert _json.loads(first.stdout)["routing_plan"] == (
        _json.loads(second.stdout)["routing_plan"]
    )
