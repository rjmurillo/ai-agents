"""Contract tests for the three canonical amendments made for issue #5410.

Issue #5410 reconciles the standalone `you` profile into existing canonical
owners. Two behaviors had no effective owner. One lands at two sites, so three
clauses changed:

1. Recurring defect: a defect class that returns gets a deterministic guard,
   not another one-off patch. Owner: the recurring-defect bullet under Fix Completeness in the
   code-quality rule, which loads on source files (review thread
   PRRT_kwDOQoWRls6tpCo9 moved it out of the tests-only testing rule).
2. Grading eval results: an underpowered comparison is inconclusive, not a
   preference. Owners: step 4 of the ai-agents-research-methodology skill and
   Step 4 of the benchmark-models skill, the shipped skill that emits model
   preference claims.

The benchmark-models clause lives in test_single_run_benchmark_contract.py and the
profile-behavior corpus in test_profile_behavior_fixtures.py.

These tests prove four things offline:

1. Every rendered surface carries each clause.
2. A mutation check removes one clause at a time and proves the checker
   notices, so the clauses are not decoration.
3. The runtime fixture corpus loads and its controls discriminate for the
   documented reason.
4. The recurring-defect clause stays scoped: it names the first-occurrence
   limit that stops it from demanding a framework for a one-off defect.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.eval._runtime_parity_test_support import runtime_parity
from tests.structural_recurrence_support import REPO_ROOT, flat, missing

RECURRENCE_SURFACES = (
    Path("templates/rules/code-quality.md"),
    Path(".claude/rules/code-quality.md"),
    Path("src/claude/rules/code-quality.md"),
    Path(".github/instructions/code-quality.instructions.md"),
    Path("src/copilot-cli/instructions/code-quality.instructions.md"),
    Path("src/cursor/rules/code-quality.mdc"),
)

TESTING_SURFACES = (
    Path("templates/rules/testing.md"),
    Path(".claude/rules/testing.md"),
    Path("src/claude/rules/testing.md"),
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
    "find-why-earlier-fix-failed": "Find why the earlier fix did not hold",
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
PROFILE_FIXTURES_PATH = REPO_ROOT / "tests" / "evals" / "profile-behavior-runtime-fixtures.json"

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


@pytest.mark.parametrize("path", RECURRENCE_SURFACES, ids=str)
def test_code_quality_surface_carries_every_recurrence_clause(path: Path) -> None:
    assert missing(flat(path), RECURRENCE_CLAUSES) == []


@pytest.mark.parametrize("path", METHODOLOGY_SURFACES, ids=str)
def test_methodology_surface_carries_every_grading_clause(path: Path) -> None:
    assert missing(flat(path), GRADING_CLAUSES) == []


@pytest.mark.parametrize("clause_id", sorted(RECURRENCE_CLAUSES))
def test_removing_a_recurrence_clause_is_detected(clause_id: str) -> None:
    """Negative control: the checker fails once the clause is gone."""
    source = flat(RECURRENCE_SURFACES[0])
    mutated = source.replace(" ".join(RECURRENCE_CLAUSES[clause_id].split()), "")
    assert missing(mutated, RECURRENCE_CLAUSES) == [clause_id]


@pytest.mark.parametrize("clause_id", sorted(GRADING_CLAUSES))
def test_removing_a_grading_clause_is_detected(clause_id: str) -> None:
    """Negative control: the checker fails once the clause is gone."""
    source = flat(METHODOLOGY_SURFACES[0])
    mutated = source.replace(" ".join(GRADING_CLAUSES[clause_id].split()), "")
    assert missing(mutated, GRADING_CLAUSES) == [clause_id]


def test_checker_reports_every_clause_for_unrelated_text() -> None:
    assert sorted(missing("nothing relevant here", RECURRENCE_CLAUSES)) == sorted(
        RECURRENCE_CLAUSES
    )
    assert sorted(missing("", GRADING_CLAUSES)) == sorted(GRADING_CLAUSES)


def test_recurrence_clause_appears_once_per_surface() -> None:
    """No duplicated normative block: the clause is authored once per surface."""
    for path in RECURRENCE_SURFACES:
        assert (
            flat(path).count("**A defect class that returns gets a guard, not another patch.**")
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
    assert "matches the rule's `**/*.py` `paths:` glob" in note


def test_scope_note_records_the_write_tool_mapping() -> None:
    """The note names the #6710 mapping that lets the agent create tests/test_dates.py."""
    note = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["_scope_note"]
    assert "#6710" in note
    assert "Claude Write and Edit" in note
    assert "until #6710 lands" not in note


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


# --- source-path activation pair and finding-4 file assertions --------------


def _structural() -> dict[str, Any]:
    return {f.fixture_id: f for f in runtime_parity.load_fixtures(FIXTURES_PATH)}


def test_activation_pair_differs_only_in_the_installed_rule() -> None:
    """The ablated control must share the prompt, files, and assertions of the rule fixture."""
    fixtures = _structural()
    with_rule, ablated = (fixtures[i] for i in ACTIVATION_FIXTURE_IDS)
    assert with_rule.instructions == (".claude/rules/code-quality.md",)
    assert ablated.instructions == ()
    assert with_rule.prompt == ablated.prompt
    assert with_rule.setup_files == ablated.setup_files
    assert [a.kind for a in with_rule.assertions] == [a.kind for a in ablated.assertions]


@pytest.mark.parametrize("fixture_id", ACTIVATION_FIXTURE_IDS)
def test_activation_fixture_edits_a_source_path_with_tools_enabled(fixture_id: str) -> None:
    """The edit starts in a source file at the repo root, not under tests/."""
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


def test_recurrence_clause_loads_on_source_paths_and_not_only_on_tests() -> None:
    """Review thread PRRT_kwDOQoWRls6tpCo9: the owner rule must match a source-only edit."""
    head = (REPO_ROOT / "templates/rules/code-quality.md").read_text(encoding="utf-8")
    head = head.split("---")[1]
    assert '"**/*.py"' in head
    assert not any(glob in head for glob in ('"tests/**"', "Tests.ps1"))
    assert "defect class that returns" not in flat(Path("templates/rules/testing.md"))
    for fixture_id in ACTIVATION_FIXTURE_IDS:
        assert "dates.py" in _structural()[fixture_id].setup_files


def test_testing_rule_no_longer_carries_the_recurrence_clause() -> None:
    """The clause moved to the source-scoped owner; no surface keeps a second copy."""
    for path in TESTING_SURFACES:
        assert "defect class that returns" not in flat(path), path


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


DATES_FIX_PATTERNS = {
    (path, a.pattern)
    for path in (FIXTURES_PATH, PROFILE_FIXTURES_PATH)
    for f in runtime_parity.load_fixtures(path)
    for a in f.assertions
    if a.kind == "file_regex" and a.path == "dates.py"
}

_DATES_HEAD = (
    "# timestamp helpers\n\n\ndef parse_stamp(value: str) -> int:\n"
    '    hours, minutes, seconds = value.split(":")\n'
)


@pytest.mark.parametrize(
    "body",
    [
        '    return int(hours) * 3600 + int(minutes) * 60 + int(seconds.rstrip("Z"))\n',
        '    return int(hours) * 3600 + int(minutes) * 60 + int(seconds.removesuffix("Z"))\n',
        "    return int(hours) * 3600 + int(minutes) * 60 + int(seconds[:-1])\n",
        '    return int(hours) * 3600 + int(minutes) * 60 + int(re.sub(r"Z$", "", seconds))\n',
        "    return int(hours) * 3600 + int(minutes) * 60 + _seconds(seconds)\n",
        '    seconds = seconds.rstrip("Z")\n    return int(hours) * 3600 + int(seconds)\n',
    ],
)
def test_dates_fix_check_accepts_every_form_that_removes_the_crash_line(body: str) -> None:
    """Behaviour, not spelling: a slice, re.sub, or helper call fixes the crash too."""
    assert DATES_FIX_PATTERNS
    for _path, pattern in DATES_FIX_PATTERNS:
        assert re.search(pattern, _DATES_HEAD + body), body


@pytest.mark.parametrize(
    "content",
    [
        _DATES_HEAD
        + "    return int(hours) * 3600 + int(minutes) * 60 + int(seconds)  # crash: ends in 'Z'\n",
        "",
        "# dates.py was emptied\n",
    ],
)
def test_dates_fix_check_rejects_the_unfixed_empty_and_function_less_file(content: str) -> None:
    for _path, pattern in DATES_FIX_PATTERNS:
        assert not re.search(pattern, content), content


def test_dates_fix_check_rejects_the_shipped_unfixed_setup_file() -> None:
    for fixture in _structural().values():
        if "dates.py" not in fixture.setup_files:
            continue
        for _path, pattern in DATES_FIX_PATTERNS:
            assert not re.search(pattern, fixture.setup_files["dates.py"]), fixture.fixture_id


@pytest.mark.parametrize("corpus", [FIXTURES_PATH, PROFILE_FIXTURES_PATH])
def test_every_python_setup_file_is_valid_python(corpus: Path) -> None:
    """A tool-enabled agent that imports a setup file must not hit a SyntaxError."""
    for fixture in runtime_parity.load_fixtures(corpus):
        for name, text in fixture.setup_files.items():
            if name.endswith(".py"):
                ast.parse(text, filename=f"{fixture.fixture_id}/{name}")


def test_stub_setup_files_keep_the_cited_return_lines() -> None:
    """The prompt and rubric cite feeds.py:12 and ingest.py:88; the stubs must not shift them."""
    files = _structural()["recurring-defect-adds-guard"].setup_files
    assert files["feeds.py"].split("\n")[11].strip().startswith("return int(")
    assert files["ingest.py"].split("\n")[87].strip().startswith("return int(")
