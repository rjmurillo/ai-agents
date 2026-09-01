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

def _representative_path(rule) -> str:
    """Build a path the rule is meant to claim."""
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


def test_find_rule_scenarios_skips_malformed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_dir = _scenario_root(tmp_path, monkeypatch)
    (scenario_dir / "broken.json").write_text("{not json", encoding="utf-8")
    (scenario_dir / "good.json").write_text(
        '{"rule_path": ".claude/rules/good.md"}', encoding="utf-8"
    )
    assert suite.find_rule_scenarios() == {
        "good": f"{suite.RULE_SCENARIO_DIR}/good.json"
    }


@pytest.mark.parametrize(
    "payload",
    [
        '["not", "an", "object"]',
        '{"skill_path": ".claude/skills/analyze/SKILL.md"}',
        '{"rule_path": ""}',
        '{"rule_path": "   "}',
        '{"rule_path": 42}',
        "{}",
    ],
    ids=["list", "skill_target", "empty", "blank", "wrong_type", "no_keys"],
)
def test_find_rule_scenarios_ignores_non_rule_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    scenario_dir = _scenario_root(tmp_path, monkeypatch)
    (scenario_dir / "case.json").write_text(payload, encoding="utf-8")
    assert suite.find_rule_scenarios() == {}


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


def _stub_child(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str = '{"verdict": "PASS"}',
    returncode: int = 0,
) -> list[list[str]]:
    """Replace subprocess.run and record the argv of every invocation."""
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        return _FakeCompleted(stdout, returncode)

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
    entry = result["rules"]["code-quality"]
    assert entry["exit_code"] == 1
    assert entry["evidence"] == suite.EVIDENCE_SCENARIO


def test_run_rule_activation_maps_unparseable_child_output_to_external(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure shape issue #4882 produced: empty stdout from the child."""
    _stub_child(monkeypatch, stdout="", returncode=1)
    result = suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")
    entry = result["rules"]["code-quality"]
    assert entry["exit_code"] == suite.EXIT_EXTERNAL
    assert entry["evidence"] == suite.EVIDENCE_SCENARIO
    assert "error" in entry["results"]
    assert suite._contains_external_failure(result) is True


def test_run_rule_activation_handles_a_child_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd, **_kwargs):
        raise suite.subprocess.TimeoutExpired(cmd, 600)

    monkeypatch.setattr(suite.subprocess, "run", fake_run)
    result = suite.run_rule_activation([".claude/rules/code-quality.md"], "test-model")
    assert result["passed"] is False
    assert result["rules"]["code-quality"]["reason"] == "timeout (600s)"


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


def test_rules_is_an_accepted_scope_value() -> None:
    source = (EVAL_DIR / "eval-suite.py").read_text(encoding="utf-8")
    assert '"prompts", "agents", "skills", "rules", "all"' in source


# ---------------------------------------------------------------------------
# End to end: the dry run the issue reproduced
# ---------------------------------------------------------------------------

def test_dry_run_exits_zero_and_emits_a_routing_plan() -> None:
    """AC: a dry run exits successfully and prints a deterministic routing plan.

    Pre-fix, this exited 3 because misrouted files reached eval-agents.py, which
    exits 1 with empty stdout. A dry run now invokes no evaluator at all.
    """
    import json as _json
    import subprocess as _subprocess

    proc = _subprocess.run(
        [sys.executable, str(EVAL_DIR / "eval-suite.py"), "--base-ref", "HEAD", "--dry-run"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=str(REPO_ROOT),
        env={**__import__("os").environ, "PYTHONPATH": str(EVAL_DIR)},
    )
    if proc.returncode == 0 and not proc.stdout.strip():
        pytest.skip("no changes against HEAD, suite exited early")

    assert proc.returncode == 0, proc.stderr[-2000:]
    payload = _json.loads(proc.stdout)
    assert payload["dry_run"] is True
    assert payload["passed"] is True
    assert payload["results"] == {}
    assert "routing_plan" in payload
    for entry in payload["routing_plan"]:
        assert entry["reason"]
        assert entry["files"] == sorted(entry["files"])
    assert "JSON parse failed" not in proc.stderr
