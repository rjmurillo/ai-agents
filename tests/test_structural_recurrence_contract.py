"""Contract tests for the three canonical amendments made for issue #5410.

Issue #5410 reconciles the standalone `you` profile into existing canonical
owners. Two behaviors had no effective owner. One lands at two sites, so three
clauses changed:

1. Recurring defect: a defect class that returns gets a deterministic guard,
   not another one-off patch. Owner: SHOULD 18 of the testing rule.
2. Grading eval results: an underpowered comparison is inconclusive, not a
   preference. Owners: step 4 of the ai-agents-research-methodology skill and
   Step 4 of the benchmark-models skill, the shipped skill that emits model
   preference claims.

These tests prove five things offline:

1. Every rendered surface carries each clause.
2. A mutation check removes one clause at a time and proves the checker
   notices, so the clauses are not decoration.
3. The runtime fixture corpus loads and its controls discriminate for the
   documented reason.
4. The recurring-defect clause stays scoped: it names the first-occurrence
   limit that stops it from demanding a framework for a one-off defect.
5. benchmark-models no longer tells the agent to make a best-overall call that
   the single-run clause forbids.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.eval._runtime_parity_test_support import runtime_parity

REPO_ROOT = Path(__file__).resolve().parents[1]

TESTING_SURFACES = (
    Path("templates/rules/testing.md"),
    Path(".claude/rules/testing.md"),
    Path("src/claude/rules/testing.md"),
    Path(".github/instructions/testing.instructions.md"),
    Path("src/copilot-cli/instructions/testing.instructions.md"),
    Path("tests/build_scripts/fixtures/rule_templates_b2/expected/testing.md"),
    Path("src/cursor/rules/testing.mdc"),
)

METHODOLOGY_SURFACES = (
    Path("templates/skills/ai-agents-research-methodology.SKILL.md.tmpl"),
    Path(".claude/skills/ai-agents-research-methodology/SKILL.md"),
)

RECURRENCE_CLAUSES: dict[str, str] = {
    "returning-class-gets-a-guard": (
        "**A defect class that returns gets a guard, not another patch.**"
    ),
    "find-why-earlier-fix-failed": "find why the earlier fix did not hold",
    "deterministic-check-on-recurrence": (
        "add a deterministic check that fails on recurrence (a test, validator, or type)"
    ),
    "warning-is-not-a-guard": "A warning or doc note is not a guard.",
    "first-occurrence-limit": (
        "A first occurrence takes the targeted fix and its regression test, nothing broader."
    ),
    "blast-radius-bound": (
        "in the same diff when it stays inside the request's correctness blast radius; "
        "otherwise name the recurrence in the report and stop."
    ),
}

BENCHMARK_SURFACES = (
    Path("templates/skills/benchmark-models.SKILL.md.tmpl"),
    Path(".claude/skills/benchmark-models/SKILL.md"),
    Path("src/claude/skills/benchmark-models/SKILL.md"),
    Path("src/codex/skills/benchmark-models/SKILL.md"),
    Path("src/copilot-cli/skills/benchmark-models/SKILL.md"),
    Path("src/cursor/skills/benchmark-models/SKILL.md"),
    Path("src/hermes/project-toolkit-delivery/skills/benchmark-models/SKILL.md"),
)

BENCHMARK_CLAUSES: dict[str, str] = {
    "single-run-inconclusive": "One run per provider is inconclusive, not a preference",
    "report-n": "report n",
    "no-winner-from-direction": "call no winner from a directional delta",
    "rerun-to-confirm": "rerun to confirm",
}

GRADING_CLAUSES: dict[str, str] = {
    "inconclusive-not-preference": "is inconclusive, not a preference",
    "report-sample-and-interval": "Report the sample size and an interval or margin",
    "direction-alone-does-not-promote": (
        "A directional delta alone does not promote an ADR or justify a model pin"
    ),
    "rerun-to-confirm": "rerun it to confirm",
    "adr-111-bar": "ADR-111 rule 2",
}

FIXTURES_PATH = REPO_ROOT / "tests" / "evals" / "structural-recurrence-runtime-fixtures.json"

UNDERPOWERED_FIXTURES_PATH = (
    REPO_ROOT / "tests" / "evals" / "underpowered-eval-runtime-fixtures.json"
)

RECURRING_FIXTURE_IDS = (
    "recurring-defect-adds-guard",
    "recurring-defect-explanation-is-not-a-guard",
)

EXPECTED_FIXTURE_IDS = {
    "recurring-defect-adds-guard",
    "recurring-defect-explanation-is-not-a-guard",
    "first-occurrence-targeted-fix-only",
    "recurring-defect-ablated-no-rule",
}

ACTIVATION_FIXTURE_IDS = (
    "recurring-defect-adds-guard",
    "recurring-defect-ablated-no-rule",
)

PROFILE_FIXTURES_PATH = REPO_ROOT / "tests" / "evals" / "profile-behavior-runtime-fixtures.json"

EXPECTED_PROFILE_FIXTURE_IDS = {
    "review-checks-head-not-pr-narrative",
    "repo-git-rule-beats-stale-note",
    "explicit-skip-tests-override-is-followed-once",
}


def _flat(path: Path) -> str:
    return " ".join((REPO_ROOT / path).read_text(encoding="utf-8").split())


def missing(text: str, clauses: dict[str, str]) -> list[str]:
    """Return ids of clauses absent from ``text`` after whitespace folding."""
    flat = " ".join(text.split())
    return [key for key, clause in clauses.items() if " ".join(clause.split()) not in flat]


@pytest.mark.parametrize("path", TESTING_SURFACES, ids=str)
def test_testing_surface_carries_every_recurrence_clause(path: Path) -> None:
    assert missing(_flat(path), RECURRENCE_CLAUSES) == []


@pytest.mark.parametrize("path", METHODOLOGY_SURFACES, ids=str)
def test_methodology_surface_carries_every_grading_clause(path: Path) -> None:
    assert missing(_flat(path), GRADING_CLAUSES) == []


@pytest.mark.parametrize("clause_id", sorted(RECURRENCE_CLAUSES))
def test_removing_a_recurrence_clause_is_detected(clause_id: str) -> None:
    """Negative control: the checker fails once the clause is gone."""
    source = _flat(TESTING_SURFACES[0])
    mutated = source.replace(" ".join(RECURRENCE_CLAUSES[clause_id].split()), "")
    assert missing(mutated, RECURRENCE_CLAUSES) == [clause_id]


@pytest.mark.parametrize("clause_id", sorted(GRADING_CLAUSES))
def test_removing_a_grading_clause_is_detected(clause_id: str) -> None:
    """Negative control: the checker fails once the clause is gone."""
    source = _flat(METHODOLOGY_SURFACES[0])
    mutated = source.replace(" ".join(GRADING_CLAUSES[clause_id].split()), "")
    assert missing(mutated, GRADING_CLAUSES) == [clause_id]


def test_checker_reports_every_clause_for_unrelated_text() -> None:
    assert sorted(missing("nothing relevant here", RECURRENCE_CLAUSES)) == sorted(
        RECURRENCE_CLAUSES
    )
    assert sorted(missing("", GRADING_CLAUSES)) == sorted(GRADING_CLAUSES)


def test_recurrence_clause_appears_once_per_testing_surface() -> None:
    """No duplicated normative block: the clause is authored once per surface."""
    for path in TESTING_SURFACES:
        assert (
            _flat(path).count("**A defect class that returns gets a guard, not another patch.**")
            == 1
        ), path


def test_fixture_corpus_loads_with_the_required_scenarios() -> None:
    fixtures = runtime_parity.load_fixtures(FIXTURES_PATH)
    assert {f.fixture_id for f in fixtures} == EXPECTED_FIXTURE_IDS


def test_every_fixture_carries_a_semantic_assertion() -> None:
    for fixture in runtime_parity.load_fixtures(FIXTURES_PATH):
        assert "semantic" in {spec.kind for spec in fixture.assertions}, fixture.fixture_id


def test_scope_note_states_the_message_only_limit_and_the_ablated_pair() -> None:
    note = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["_scope_note"]
    assert "REPORTS" in note
    assert "ablated control" in note
    assert "outside the rule's `paths:` globs" in note


def test_only_the_first_occurrence_fixture_is_message_only() -> None:
    """Finding 4: every recurrence fixture writes files; only the one-off bound is report-only."""
    fixtures = _structural()
    message_only = {fid for fid, f in fixtures.items() if not f.tools}
    assert message_only == {"first-occurrence-targeted-fix-only"}


@pytest.mark.parametrize(
    "fixture_id",
    [*RECURRING_FIXTURE_IDS, "recurring-defect-ablated-no-rule"],
)
def test_recurrence_fixtures_assert_the_written_test_file(fixture_id: str) -> None:
    """A reply that only claims a test fails: tests/test_dates.py must exist in the workspace."""
    fixture = _structural()[fixture_id]
    paths = {a.path for a in fixture.assertions if a.kind == "file_regex"}
    assert "tests/test_dates.py" in paths
    assert "tests/test_dates.py" in fixture.positive.files
    assert "tests/test_dates.py" not in fixture.negative.files


def test_scope_note_denies_the_regex_backstop_semantic_authority() -> None:
    note = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["_scope_note"].lower()
    assert "not the semantic authority" in note


def test_patch_only_negative_control_names_no_guard() -> None:
    """Negative control 1: a patch-only reply to a recurring defect has no guard."""
    fixture = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}[
        "recurring-defect-adds-guard"
    ]
    guard = _guard_pattern("recurring-defect-adds-guard")
    assert guard.search(fixture.positive.response)
    assert not guard.search(fixture.negative.response)


def _guard_pattern(fixture_id: str) -> re.Pattern[str]:
    """A recurring-defect fixture's guard regex, read from the corpus itself.

    Each recurring-defect fixture must carry exactly one ``regex`` assertion
    beyond the location anchor, so weakening or deleting it in the corpus
    breaks these tests instead of leaving a stale copy green.
    """
    fixture = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}[fixture_id]
    patterns = [spec.pattern for spec in fixture.assertions if spec.kind == "regex"]
    assert len(patterns) == 2, fixture_id
    anchor, guard = patterns
    assert anchor == r"dates\.py", fixture_id
    return re.compile(guard)


def _overbuilt_pattern() -> re.Pattern[str]:
    """The first-occurrence fixture's not_regex, read from the corpus itself."""
    fixture = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}[
        "first-occurrence-targeted-fix-only"
    ]
    patterns = [spec.pattern for spec in fixture.assertions if spec.kind == "not_regex"]
    assert len(patterns) == 1
    return re.compile(patterns[0])


def test_overbuilt_negative_control_builds_enforcement_for_a_first_occurrence() -> None:
    """Negative control 2: the clause must not license a framework for a one-off."""
    fixture = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}[
        "first-occurrence-targeted-fix-only"
    ]
    overbuilt = _overbuilt_pattern()
    assert overbuilt.search(fixture.negative.response)
    assert not overbuilt.search(fixture.positive.response)


def test_the_two_fixtures_give_opposite_prompts_about_history() -> None:
    """The pair only discriminates if one prompt has prior fixes and the other has none."""
    fixtures = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}
    assert "already patched" in fixtures["recurring-defect-adds-guard"].prompt
    assert "no earlier fix" in fixtures["first-occurrence-targeted-fix-only"].prompt


def test_regression_test_described_as_a_guard_is_not_overbuilt() -> None:
    """A regression test is allowed on a first occurrence, even when called a guard."""
    overbuilt = _overbuilt_pattern()
    for reply in (
        "I added a regression test as a guard for this input.",
        "I added a regression test for that input.",
        "I wrote a guard clause test for the trailing Z case.",
    ):
        assert not overbuilt.search(reply), reply


@pytest.mark.parametrize(
    "reply",
    [
        "I added a repo-wide guard for every parser.",
        "I built a class-wide guard around int() parsing.",
        "I introduced a validator for all timestamps.",
    ],
)
def test_class_wide_enforcement_on_a_first_occurrence_is_overbuilt(reply: str) -> None:
    assert _overbuilt_pattern().search(reply), reply


def test_explain_only_negative_control_adds_no_check() -> None:
    """Negative control 3: explaining why earlier fixes failed is not a guard."""
    fixture = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}[
        "recurring-defect-explanation-is-not-a-guard"
    ]
    guard = _guard_pattern("recurring-defect-explanation-is-not-a-guard")
    assert "keeps coming back because" in fixture.negative.response
    assert guard.search(fixture.positive.response)
    assert not guard.search(fixture.negative.response)


@pytest.mark.parametrize("fixture_id", RECURRING_FIXTURE_IDS)
def test_semantic_rubric_requires_the_check_and_rejects_explain_only(fixture_id: str) -> None:
    """The semantic authority must not let an explanation stand in for the guard."""
    fixtures = {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}
    rubric = next(
        spec.rubric for spec in fixtures[fixture_id].assertions if spec.kind == "semantic"
    )
    assert "or explains why" not in rubric
    assert "only explains why the earlier fixes did not hold" in rubric


# --- benchmark-models Step 4 single-run clause (fixture 9) -----------------


@pytest.mark.parametrize("path", BENCHMARK_SURFACES, ids=str)
def test_benchmark_surface_carries_every_single_run_clause(path: Path) -> None:
    assert missing(_flat(path), BENCHMARK_CLAUSES) == []


@pytest.mark.parametrize("clause_id", sorted(BENCHMARK_CLAUSES))
def test_removing_a_benchmark_clause_is_detected(clause_id: str) -> None:
    """Negative control: the checker fails once the clause is gone."""
    source = _flat(BENCHMARK_SURFACES[0])
    mutated = source.replace(" ".join(BENCHMARK_CLAUSES[clause_id].split()), "")
    assert missing(mutated, BENCHMARK_CLAUSES) == [clause_id]


BEST_MODEL_PROMISES = ("best-overall call", "actually best for this skill")


def promises_a_best_model(text: str) -> list[str]:
    """Return the removed best-model phrases still present in ``text``."""
    flat = " ".join(text.lower().split())
    return [phrase for phrase in BEST_MODEL_PROMISES if phrase in flat]


@pytest.mark.parametrize("path", BENCHMARK_SURFACES, ids=str)
def test_benchmark_surface_has_no_best_overall_instruction(path: Path) -> None:
    """Step 4 must not order a best-overall call beside the no-winner clause.

    model_benchmark.py has no repeat flag, so every invocation is one run per
    provider and the single-run clause always applies. The description and
    the Step 4 text must also stop promising a "best" model from that run.
    """
    assert promises_a_best_model(_flat(path)) == []


def test_benchmark_script_docstring_does_not_promise_a_best_model() -> None:
    script = REPO_ROOT / ".claude/skills/benchmark-models/scripts/model_benchmark.py"
    assert promises_a_best_model(script.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("phrase", BEST_MODEL_PROMISES)
def test_best_model_check_detects_each_reintroduced_phrase(phrase: str) -> None:
    """Negative control: the check fires when a removed phrase returns."""
    mutated = _flat(BENCHMARK_SURFACES[0]) + " " + phrase.upper()
    assert promises_a_best_model(mutated) == [phrase]


def _underpowered_fixture() -> Any:
    fixtures = runtime_parity.load_fixtures(UNDERPOWERED_FIXTURES_PATH)
    assert [f.fixture_id for f in fixtures] == ["single-run-benchmark-names-no-winner"]
    return fixtures[0]


def test_underpowered_fixture_quotes_the_shipped_step_4_sentence() -> None:
    """The harness installs no skills, so the prompt carries the clause.

    The quote must stay a substring of every rendered skill, or the fixture
    grades a sentence the skill no longer says.
    """
    prompt = " ".join(_underpowered_fixture().prompt.split())
    quoted = prompt.split("Step 4 of the skill says: '", 1)[1].split("' Write", 1)[0]
    assert quoted.startswith("One run per provider is inconclusive")
    for path in BENCHMARK_SURFACES:
        assert quoted in _flat(path), path


def test_underpowered_fixture_has_a_semantic_assertion_and_a_scope_note() -> None:
    fixture = _underpowered_fixture()
    assert "semantic" in {spec.kind for spec in fixture.assertions}
    note = json.loads(UNDERPOWERED_FIXTURES_PATH.read_text(encoding="utf-8"))["_scope_note"]
    assert "does not test that the skill loads" in note
    assert "NOT the semantic authority" in note


def _winner_pattern() -> re.Pattern[str]:
    patterns = [
        spec.pattern for spec in _underpowered_fixture().assertions if spec.kind == "not_regex"
    ]
    assert len(patterns) == 1
    return re.compile(patterns[0])


def test_underpowered_negative_control_names_a_winner_and_positive_does_not() -> None:
    """Negative control: a reply that crowns a winner from one run is rejected."""
    fixture = _underpowered_fixture()
    winner = _winner_pattern()
    assert winner.search(fixture.negative.response)
    assert not winner.search(fixture.positive.response)
    assert "inconclusive" in fixture.positive.response
    assert "inconclusive" not in fixture.negative.response


@pytest.mark.parametrize(
    "reply",
    [
        "GPT is the best overall on this run.",
        "Best overall: Claude, given the judge score.",
        "Winner: Gemini.",
        "I would pick Gemini.",
    ],
)
def test_winner_pattern_rejects_single_run_winner_claims(reply: str) -> None:
    assert _winner_pattern().search(reply), reply


@pytest.mark.parametrize(
    "reply",
    [
        "n=1 per provider, so the result is inconclusive. No winner can be called.",
        "Step 4 applies: inconclusive. No winner is called.",
        'This does not support "gpt is best" or "gemini is the cheapest good option."',
        "We never call a winner from one run.",
        "Fastest: gpt at 6.9s. Cheapest: gemini at $0.018. Rerun to confirm.",
        "",
    ],
)
def test_winner_pattern_allows_the_per_metric_summary_and_no_winner(reply: str) -> None:
    assert not _winner_pattern().search(reply), reply


def test_winner_pattern_still_rejects_a_bare_winner_after_a_negation_elsewhere() -> None:
    """Negation guards are local: 'No winner is called' must not excuse a later pick."""
    assert _winner_pattern().search("No winner is called yet. The winner is gpt.")


# --- source-path activation pair and finding-4 file assertions --------------


def _structural() -> dict[str, Any]:
    return {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}


def test_activation_pair_differs_only_in_the_installed_rule() -> None:
    """The ablated control must share the prompt, files, and assertions of the rule fixture."""
    fixtures = _structural()
    with_rule, ablated = (fixtures[i] for i in ACTIVATION_FIXTURE_IDS)
    assert with_rule.instructions == (".claude/rules/testing.md",)
    assert ablated.instructions == ()
    assert with_rule.prompt == ablated.prompt
    assert with_rule.setup_files == ablated.setup_files
    assert [a.kind for a in with_rule.assertions] == [a.kind for a in ablated.assertions]


@pytest.mark.parametrize("fixture_id", ACTIVATION_FIXTURE_IDS)
def test_activation_fixture_edits_a_source_path_with_tools_enabled(fixture_id: str) -> None:
    """The edit starts in scripts/, outside the testing rule's `paths:` globs."""
    fixture = _structural()[fixture_id]
    assert set(fixture.tools) == {"read", "write"}
    assert "dates.py" in fixture.setup_files
    assert not any(path.startswith("tests/") for path in fixture.setup_files)
    assert len(fixture.setup_files["dates.py"].split("\n")) >= 31
    assert "int(seconds)" in fixture.setup_files["dates.py"].split("\n")[30]


@pytest.mark.parametrize("fixture_id", ACTIVATION_FIXTURE_IDS)
def test_activation_negative_control_writes_no_test_file(fixture_id: str) -> None:
    """Negative control: a reply that claims a guard but wrote none fails the file assertion."""
    fixture = _structural()[fixture_id]
    assert "tests/test_dates.py" in fixture.positive.files
    assert "tests/test_dates.py" not in fixture.negative.files
    file_specs = [a for a in fixture.assertions if a.kind == "file_regex" and a.path]
    assert {a.path for a in file_specs} == {"dates.py", "tests/test_dates.py"}


def test_activation_fixtures_ablate_the_rule_path_not_the_assertions() -> None:
    """The with-rule fixture's rule must still scope to tests, so source edits do not load it."""
    frontmatter = (REPO_ROOT / "templates/rules/testing.md").read_text(encoding="utf-8")
    head = frontmatter.split("---")[1]
    assert "tests/**" in head
    assert not any(glob in head for glob in ('"**/*.py"', '"scripts/**"'))


def test_blast_radius_clause_is_in_every_rubric_that_accepts_a_flag() -> None:
    """The adds-guard rubric admits a declarative flag with a scoped regression test."""
    fixture = _structural()["recurring-defect-adds-guard"]
    rubric = next(a.rubric for a in fixture.assertions if a.kind == "semantic")
    assert "blast radius" in rubric
    assert "flags the recurrence declaratively" in rubric
    assert "is not a FAIL" in rubric


def test_scoped_regression_test_with_a_flag_satisfies_the_guard_regex() -> None:
    """A reply that fixes, adds a scoped test, and flags the recurrence is not graded FAIL."""
    guard = _guard_pattern("recurring-defect-adds-guard")
    reply = (
        "Fixed dates.py:31. Added a regression test that fails on a raw 'Z' string. "
        "The same defect class was patched at feeds.py:12 and ingest.py:88; a class-wide guard "
        "is not built here because it is outside the request."
    )
    assert guard.search(reply)


# --- profile behavior corpus (issue #5410 fixtures 1, 10, 11) ----------------


def _profile() -> dict[str, Any]:
    return {f.fixture_id: f for f in runtime_parity.load_fixtures(PROFILE_FIXTURES_PATH)}


def test_profile_corpus_loads_with_the_three_missing_fixtures() -> None:
    assert set(_profile()) == EXPECTED_PROFILE_FIXTURE_IDS


def test_profile_fixtures_carry_a_semantic_assertion_and_a_deterministic_one() -> None:
    for fixture in _profile().values():
        kinds = {spec.kind for spec in fixture.assertions}
        assert "semantic" in kinds, fixture.fixture_id
        assert kinds & {"regex", "not_regex"}, fixture.fixture_id


def test_profile_scope_note_denies_the_regex_backstop_semantic_authority() -> None:
    note = json.loads(PROFILE_FIXTURES_PATH.read_text(encoding="utf-8"))["_scope_note"]
    assert "NOT the semantic authority" in note
    assert "tools: []" in note


def _not_regexes(fixture_id: str) -> list[re.Pattern[str]]:
    return [
        re.compile(a.pattern) for a in _profile()[fixture_id].assertions if a.kind == "not_regex"
    ]


def _regexes(fixture_id: str) -> list[re.Pattern[str]]:
    return [re.compile(a.pattern) for a in _profile()[fixture_id].assertions if a.kind == "regex"]


def test_review_negative_control_trusts_the_pr_narrative() -> None:
    fixture = _profile()["review-checks-head-not-pr-narrative"]
    assert fixture.negative.response.startswith("Verdict: APPROVE")
    assert fixture.positive.response.startswith("Verdict: REQUEST CHANGES")
    assert any(p.search(fixture.negative.response) for p in _not_regexes(fixture.fixture_id))
    assert "only edits a comment" in fixture.positive.response
    assert "comment" in fixture.prompt and "null check" in fixture.prompt


@pytest.mark.parametrize(
    ("reply", "rejected"),
    [
        ("Verdict: REQUEST CHANGES\nauth.ts:47 has no null check.", False),
        ("Verdict: APPROVE\nauth.ts:47 looks fine.", True),
        ("verdict: approve\nauth.ts:47", False),
        ("Verdict: APPROVE WITH NITS\nauth.ts:47", True),
        ("", False),
    ],
)
def test_review_deterministic_assertions_split_approve_from_request_changes(
    reply: str, rejected: bool
) -> None:
    fixture_id = "review-checks-head-not-pr-narrative"
    trips_not = any(p.search(reply) for p in _not_regexes(fixture_id))
    passes_regex = all(p.search(reply) for p in _regexes(fixture_id))
    assert trips_not == rejected
    if rejected:
        assert not passes_regex


def test_git_rule_negative_control_force_pushes_and_positive_does_not() -> None:
    fixture = _profile()["repo-git-rule-beats-stale-note"]
    not_force = _not_regexes(fixture.fixture_id)
    assert any(p.search(fixture.negative.response) for p in not_force)
    assert not any(p.search(fixture.positive.response) for p in not_force)
    assert "--force-with-lease" in fixture.prompt


@pytest.mark.parametrize(
    "reply",
    [
        "Command: git push --force origin feat/x\nWhy: stale.",
        "Command: git push -f origin feat/x\nWhy: stale.",
        "Command: git push origin +feat/x\nWhy: stale.",
        "Command: git push --force-with-lease origin feat/x\nWhy: stale.",
    ],
)
def test_git_rule_every_force_push_spelling_is_rejected(reply: str) -> None:
    assert any(p.search(reply) for p in _not_regexes("repo-git-rule-beats-stale-note")), reply


@pytest.mark.parametrize(
    "reply",
    [
        "Command: git merge origin/feat/x\nWhy: shared branch.",
        "Command: git push origin feat/x\nWhy: plain push after merge.",
        "Command: git fetch origin\nWhy: --force is barred, so I fetch first.",
    ],
)
def test_git_rule_non_force_commands_are_allowed(reply: str) -> None:
    assert not any(p.search(reply) for p in _not_regexes("repo-git-rule-beats-stale-note")), reply


def test_override_negative_control_adds_tests_despite_the_instruction() -> None:
    fixture = _profile()["explicit-skip-tests-override-is-followed-once"]
    not_re = _not_regexes(fixture.fixture_id)
    assert any(p.search(fixture.negative.response) for p in not_re)
    assert not any(p.search(fixture.positive.response) for p in not_re)
    assert "Skip the tests" in fixture.prompt


@pytest.mark.parametrize(
    "reply",
    [
        "Patched dates.py:31. Should I add tests?",
        "Patched dates.py:31. Want me to write a regression test?",
        "Patched dates.py:31. I wrote a quick test for it.",
        "Patched dates.py:31. I also ran the tests anyway.",
    ],
)
def test_override_rejects_permission_questions_and_added_tests(reply: str) -> None:
    patterns = _not_regexes("explicit-skip-tests-override-is-followed-once")
    assert any(p.search(reply) for p in patterns), reply


def test_override_allows_prose_that_only_contains_the_word_before() -> None:
    """'before int()' is code prose, not 'before I ...' permission-seeking."""
    patterns = _not_regexes("explicit-skip-tests-override-is-followed-once")
    reply = "Patched dates.py:31 to strip the suffix before int() runs. Tests skipped."
    assert not any(p.search(reply) for p in patterns)


def test_override_positive_control_states_the_tradeoff_once() -> None:
    fixture = _profile()["explicit-skip-tests-override-is-followed-once"]
    assert len(re.findall(r"(?i)skipped", fixture.positive.response)) == 1
    assert all(p.search(fixture.positive.response) for p in _regexes(fixture.fixture_id))
    assert not all(p.search(fixture.negative.response) for p in _regexes(fixture.fixture_id))
