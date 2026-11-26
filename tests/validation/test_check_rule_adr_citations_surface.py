"""Surface, existence and pointer tests for check_rule_adr_citations.py.

Split from test_check_rule_adr_citations.py to stay under the file-size limit.
pos: the three live lines that named superseded ADR-080 as the pin owner, a
terse `label: ADR-NNN` pointer, a compliance verb, a number with no tracked
record. neg: history labels, trailing prose, code spans, the same lines
repointed. edge: lineage outranks a verb, an untracked record, a fragment
fence, a file matched by two globs, git failing to list records.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_rule_adr_citations as gate
from check_rule_adr_citations import (
    BINDING,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REGRESSION,
    META,
    MISSING,
    UNCLASSIFIED,
    citations_in,
)

from tests.validation.test_check_rule_adr_citations import (
    BAD,
    GOOD,
    STATUSES,
    _adr,
    _baseline,
    _git,
    _kinds,
    _make_repo,
    _run,
)

# --------------------------------------------------------------------------
# Terse pointers and compliance verbs (the ADR-080 citations ADR-111 retired)
# --------------------------------------------------------------------------

AGENTS_PINS_LINE = (
    "Effort|by task shape+verifier, never vendor default|bounded: lowest|"
    "specified: low/medium|judgment: medium, high when ambiguity/repair/"
    "architecture/acceptance dominate|more != better, validate per task+harness|"
    "pins: ADR-080\n"
)
ORCHESTRATOR_PIN_LINE = "Pin changes pass ADR-080; this policy never justifies a pin.\n"
PLUGIN_GUIDE_PIN_LINE = (
    "- `model:` needs an ADR-080 `KEEP_PIN` sidecar entry, or a bare alias "
    "(`sonnet`, `opus`, `haiku`) plus `model-rationale:`.\n"
)


@pytest.mark.parametrize("line", [AGENTS_PINS_LINE, ORCHESTRATOR_PIN_LINE, PLUGIN_GUIDE_PIN_LINE])
def test_live_citations_of_superseded_adr_080_are_binding(line: str) -> None:
    """Regression: the exact lines that named superseded ADR-080 as the pin owner
    in `AGENTS.md`, the orchestrator partial, and the plugin guide."""
    assert _kinds(line) == [(80, BINDING, 1)]


@pytest.mark.parametrize("line", [AGENTS_PINS_LINE, ORCHESTRATOR_PIN_LINE, PLUGIN_GUIDE_PIN_LINE])
def test_the_same_lines_repointed_to_an_accepted_adr_are_clean(line: str) -> None:
    assert _kinds(line.replace("ADR-080", "ADR-106")) == []


@pytest.mark.parametrize(
    "text",
    [
        "pins: ADR-080\n",
        "- Pins: ADR-080.\n",
        "**Pins**: ADR-080\n",
        "a|pins: ADR-080, ADR-079|b\n",
        "Owner: ADR-002\n",
        "Policy: ADR-095\n",
    ],
)
def test_a_label_and_number_pointer_is_binding(text: str) -> None:
    assert all(kind == BINDING for _, kind, _ in _kinds(text))
    assert _kinds(text)


@pytest.mark.parametrize(
    "text",
    [
        "Refs: ADR-080\n",
        "Replaces: ADR-080\n",
        "Formerly: ADR-080\n",
        "See also: ADR-080\n",
        "History: ADR-080\n",
        "Example: ADR-080\n",
    ],
)
def test_a_history_or_reference_label_is_not_a_pointer(text: str) -> None:
    assert BINDING not in [kind for _, kind, _ in _kinds(text)]


def test_a_long_run_of_numbers_that_is_not_a_pointer_classifies_in_linear_time() -> None:
    """Blanked code spans leave long space runs; a failed match must not backtrack."""
    text = "pins: " + ", ".join("ADR-080" + " " * 40 for _ in range(60)) + " and more prose\n"
    started = time.perf_counter()
    kinds = {kind for _, kind, _ in _kinds(text)}
    assert kinds == {UNCLASSIFIED}
    assert time.perf_counter() - started < 2.0


def test_a_pointer_with_trailing_prose_is_not_a_pointer() -> None:
    """Only a cell that is nothing but the label and the numbers is a pointer."""
    assert _kinds("pins: ADR-080 was the first attempt\n") == [(80, UNCLASSIFIED, 1)]


@pytest.mark.parametrize("verb", ["pass", "passes", "satisfy", "satisfies", "meet", "follows"])
def test_a_compliance_verb_before_the_mention_is_binding(verb: str) -> None:
    assert _kinds(f"Pin changes {verb} ADR-080 first.\n") == [(80, BINDING, 1)]
    assert _kinds(f"Pin changes {verb} the ADR-080 bar.\n") == [(80, BINDING, 1)]


def test_parenthetical_and_example_mentions_are_unclassified() -> None:
    """A trailing "(ADR-NNN)" and an example sentence carry no authority signal."""
    assert _kinds("A router retries on a signal it can read (ADR-078).\n") == [
        (78, UNCLASSIFIED, 1)
    ]
    text = '- **What**: The specific conflict (e.g., "architecture violates ADR-007")\n'
    assert _kinds(text) == [(7, UNCLASSIFIED, 1)]


def test_a_compliance_verb_does_not_outrank_lineage() -> None:
    """META wins: the mention is history even after a compliance verb."""
    assert _kinds("Pins pass ADR-080, superseded by ADR-106.\n") == [(80, META, 1)]


def test_a_compliance_verb_elsewhere_in_the_sentence_is_not_a_signal() -> None:
    assert _kinds("Changes pass review, as ADR-080 once described.\n") == [(80, UNCLASSIFIED, 1)]


# --------------------------------------------------------------------------
# Existence: a cited number needs a tracked record
# --------------------------------------------------------------------------

RECORDS = frozenset(STATUSES)


def _found(text: str, records: frozenset[int] | None = RECORDS) -> list[tuple[int, str, int]]:
    found = citations_in("f.md", text, STATUSES, set(), records)
    return [(c.adr, c.kind, c.line) for c in found]


def test_a_number_with_no_record_is_missing_whatever_the_sentence_says() -> None:
    assert _found("Authors MUST comply with ADR-999.\n") == [(999, MISSING, 1)]
    assert _found("Background reading: see ADR-999 and ADR-042.\n") == [(999, MISSING, 1)]
    assert _found("## References\n\n- ADR-999\n") == [(999, MISSING, 3)]


def test_a_missing_number_in_code_or_a_file_name_is_not_a_citation() -> None:
    assert _found("Name the file `ADR-999-slug.md`, as in `ADR-999`.\n") == []
    assert _found("```text\nADR-999\n```\n") == []
    assert _found("See docs/ADR-999-slug.md for the shape.\n") == []


def test_a_record_with_an_unusable_status_exists_and_is_only_counted() -> None:
    unknown: set[int] = set()
    found = citations_in("f.md", "Per ADR-55.\n", {55: ""}, unknown, frozenset({55}))
    assert found == []
    assert unknown == {55}


def test_existence_is_skipped_when_no_record_set_is_given() -> None:
    assert _found("Authors MUST comply with ADR-999.\n", None) == []


def test_missing_render_names_the_record_directory() -> None:
    (citation,) = citations_in("f.md", "See ADR-999.\n", STATUSES, set(), RECORDS)
    assert "ADR-999 has no tracked record" in citation.render()
    assert citation.key == "f.md::ADR-999"


# --------------------------------------------------------------------------
# CLI: ratchet, surface, fragments
# --------------------------------------------------------------------------


def test_missing_record_fails_and_names_the_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"AGENTS.md": "Background: ADR-999 came first.\n"})
    code = _run(repo, _baseline(tmp_path, []))
    captured = capsys.readouterr()
    assert code == EXIT_REGRESSION
    assert re.search(r"^AGENTS\.md:1: .*ADR-999 has no tracked record", captured.out, re.M)
    assert "1 missing record(s)" in captured.err
    assert _run(repo, _baseline(tmp_path, ["AGENTS.md::ADR-999"])) == EXIT_OK


def test_an_untracked_record_does_not_satisfy_existence(tmp_path: Path) -> None:
    """Control: the same record staged turns the run green."""
    repo = _make_repo(tmp_path, {"AGENTS.md": "Background: ADR-150 came first.\n"})
    _adr(repo / ".project-toolkit" / "architecture", 150, "accepted")
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION
    _git(repo, "add", "--force", "--", ".project-toolkit/architecture")
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK


def test_the_agents_md_pins_line_fails_before_the_fix_and_passes_after(tmp_path: Path) -> None:
    """The gap this closes: `pins: ADR-080` read as UNCLASSIFIED and shipped."""
    repo = _make_repo(tmp_path, {"AGENTS.md": AGENTS_PINS_LINE})
    adr_dir = repo / ".project-toolkit" / "architecture"
    _adr(adr_dir, 80, "superseded")
    _adr(adr_dir, 111, "accepted")
    _git(repo, "add", "--force", "--", ".project-toolkit/architecture")
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION
    (repo / "AGENTS.md").write_text(AGENTS_PINS_LINE.replace("ADR-080", "ADR-111"), "utf-8")
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK


@pytest.mark.parametrize("status", ["superseded", "deprecated", "rejected", "proposed"])
def test_every_non_accepted_status_fails_a_pointer(tmp_path: Path, status: str) -> None:
    repo = _make_repo(tmp_path, {"AGENTS.md": "pins: ADR-090\n"})
    _adr(repo / ".project-toolkit" / "architecture", 90, status)
    _git(repo, "add", "--force", "--", ".project-toolkit/architecture")
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION


def test_an_unclosed_fence_in_a_fragment_is_counted_not_failed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A partial opens a fence another file closes. A whole document still fails."""
    body = GOOD + "```text\nopen\n"
    repo = _make_repo(
        tmp_path,
        {"templates/agents/partials/a.mustache": body, "templates/agents/a.claude.md.tmpl": body},
    )
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK
    assert "2 fragment fence(s) not failed" in capsys.readouterr().out
    whole = repo / "templates" / "agents" / "a.shared.md"
    whole.write_text(body, encoding="utf-8")
    _git(repo, "add", "--force", "--", "templates/agents/a.shared.md")
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION


def test_a_violation_before_a_fragment_fence_is_still_read(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"templates/agents/partials/a.mustache": BAD + "```text\nx\n"})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION


def test_a_file_matched_by_two_globs_is_examined_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"AGENTS.md": GOOD, "templates/agents/AGENTS.md": GOOD})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK
    assert "2 of 2 tracked rule file(s)" in capsys.readouterr().out


def test_git_failing_to_list_records_is_an_external_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD})
    real = gate.tracked_files

    def _records_fail(root: Path, globs: tuple[str, ...]) -> list[str] | None:
        return None if globs == (gate.ADR_RECORD_GLOB,) else real(root, globs)

    monkeypatch.setattr(gate, "tracked_files", _records_fail)
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_EXTERNAL


@pytest.mark.parametrize(
    "rel",
    [
        ".claude/CLAUDE.md",
        ".claude/AGENTS.md",
        "src/claude/AGENTS.md",
        "templates/agents/a.shared.md",
        "templates/agents/a.claude.md.tmpl",
        "templates/agents/partials/a.mustache",
        "src/claude/agents/a.md",
        "src/copilot-cli/agents/a.agent.md",
        "src/vs-code-agents/a.agent.md",
        "src/cursor/agents/a.md",
        "src/muse/agents/a.md",
        ".github/agents/a.agent.md",
    ],
)
def test_nested_guides_agent_templates_and_rendered_agents_are_checked(
    tmp_path: Path, rel: str
) -> None:
    """The surface no gate read while `pins: ADR-080` and its siblings shipped."""
    repo = _make_repo(tmp_path, {rel: BAD})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION
    assert _run(repo, _baseline(tmp_path, [f"{rel}::ADR-078"])) == EXIT_OK


def test_the_toml_agent_tree_is_outside_the_scan_set(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD, "src/codex/agents/a.toml": BAD})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK
