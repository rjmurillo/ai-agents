"""Tests for scripts/validation/check_rule_adr_citations.py (issue #5200).

pos: each non-accepted status cited with a binding signal is flagged, including
the shapes of the issue's two live instances, a compliance verb, and a terse
`label: ADR-NNN` pointer; a number with no tracked record is flagged. neg:
accepted ADRs, code spans, fences, comments, frontmatter, paths, bibliography
and lineage clauses are not.
edge: mixed binding and historical citations, heading scope, wrapped sentences,
unknown numbers, and unclassified mentions (reported, never failed). Ratchet and
CLI: known passes, new fails, stale fails, unusable scope exits 2 or 3.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_rule_adr_citations as gate
from check_rule_adr_citations import (
    BINDING,
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REGRESSION,
    META,
    MISSING,
    UNCLASSIFIED,
    citations_in,
    main,
)

STATUSES = {
    2: "deprecated",
    7: "superseded",
    42: "accepted",
    78: "proposed",
    79: "superseded",
    80: "superseded",
    92: "accepted",
    93: "proposed",
    95: "rejected",
    106: "accepted",
}


def _kinds(text: str, unknown: set[int] | None = None) -> list[tuple[int, str, int]]:
    """``(adr, kind, line)`` for every non-accepted mention in ``text``."""
    found = citations_in("f.md", text, STATUSES, unknown if unknown is not None else set())
    return [(c.adr, c.kind, c.line) for c in found]


# --------------------------------------------------------------------------
# Positive: a binding citation of a non-accepted ADR is flagged
# --------------------------------------------------------------------------


def test_claude_md_live_instance_is_binding() -> None:
    """The CLAUDE.md sentence the issue names, ADR-078 being `proposed`."""
    text = (
        "`/autoplan` is the canonical intent router for concrete requests that "
        "name no skill, per ADR-078. It routes to skills.\n"
    )
    assert _kinds(text) == [(78, BINDING, 1)]


def test_must_line_citing_a_proposed_adr_is_binding() -> None:
    """MUST-4 of universal.md states ADR-093's rule and does not name it. A MUST
    line that does name it, as the issue assumed, is the shape this catches."""
    text = (
        "4. **Verify a red remote check with equivalent evidence, or report it "
        "unreproduced.** MUST NOT claim a red check is cleared by a local run "
        "(ADR-093).\n"
    )
    assert _kinds(text) == [(93, BINDING, 1)]


@pytest.mark.parametrize("adr", [2, 78, 79, 95])
def test_every_non_accepted_status_is_flagged(adr: int) -> None:
    """deprecated, proposed, superseded and rejected, each with a MUST."""
    assert _kinds(f"Authors MUST comply with ADR-{adr:03d}.\n") == [(adr, BINDING, 1)]


def test_a_binding_prefix_without_a_modal_is_binding() -> None:
    assert _kinds("Behaviour is defined by ADR-078.\n") == [(78, BINDING, 1)]
    assert _kinds("Pins live under ADR-080 today.\n") == [(80, BINDING, 1)]


def test_wrapped_sentence_reports_the_line_of_the_mention() -> None:
    text = "Agents MUST honor the policy\nin ADR-080 for generated mirrors.\n"
    assert _kinds(text) == [(80, BINDING, 2)]


def test_table_row_is_its_own_block() -> None:
    text = "| rule | source |\n| a | MUST follow ADR-078 |\n| b | ADR-079 |\n"
    assert _kinds(text) == [(78, BINDING, 2), (79, UNCLASSIFIED, 3)]


# --------------------------------------------------------------------------
# Negative: not a binding citation
# --------------------------------------------------------------------------


def test_an_accepted_adr_is_never_reported() -> None:
    assert _kinds("Authors MUST comply with ADR-042 and ADR-106.\n") == []


def test_supersedes_clause_marks_only_the_older_record_as_history() -> None:
    """plugin-version-bump.md:46: one binding and one historical citation in a
    seven-word sentence. The older record is META, not a finding."""
    assert _kinds("See ADR-092, which supersedes ADR-079.\n") == [(79, META, 1)]


def test_binding_and_historical_citation_in_one_sentence_are_split() -> None:
    text = "Agents MUST follow ADR-078, which supersedes ADR-079.\n"
    assert _kinds(text) == [(78, BINDING, 1), (79, META, 1)]


def test_formerly_cited_and_deprecated_is_lineage() -> None:
    """templates.md:28 text: the deprecated record is named only to say it left."""
    text = (
        "`model_tier` is optional. ADR-002, formerly cited here, is deprecated in "
        "favor of ADR-080 (2026-08-25).\n"
    )
    assert _kinds(text) == [(2, META, 1), (80, UNCLASSIFIED, 1)]


def test_passive_superseded_by_sentence_is_lineage_both_ways() -> None:
    assert _kinds("ADR-007 was superseded by ADR-079.\n") == [(7, META, 1), (79, META, 1)]


def test_lineage_list_marks_every_older_record() -> None:
    assert _kinds("ADR-092 supersedes ADR-079 and ADR-080.\n") == [
        (79, META, 1),
        (80, META, 1),
    ]


def test_inline_code_span_is_not_a_citation() -> None:
    """code-quality.md:188 teaches a citation format inside backticks."""
    text = "Reference ADRs MUST name the record: `# See ADR-007 (memory-first)`.\n"
    assert _kinds(text) == []


def test_file_path_and_line_range_are_not_citations() -> None:
    """tool-use-hook-bar.md:35 cites a path with a line range, bare-regex bait."""
    text = (
        "MUST read `ADR-085-asymmetry.md:428-431` and "
        ".project-toolkit/architecture/ADR-080-model-pin.md first.\n"
    )
    assert _kinds(text) == []


def test_fenced_block_comment_and_frontmatter_are_ignored() -> None:
    text = (
        "---\ndescription: MUST follow ADR-078\n---\n"
        "<!-- MUST comply with ADR-079 -->\n"
        "```\nMUST comply with ADR-080\n```\n"
        "~~~text\nMUST comply with ADR-095\n~~~\n"
    )
    assert _kinds(text) == []


def test_unclosed_fence_masks_to_end_of_file() -> None:
    assert _kinds("```\nMUST comply with ADR-078\n") == []


def test_references_heading_makes_entries_bibliography() -> None:
    text = "## References\n\n- ADR-078 MUST be read first\n- ADR-079\n"
    assert _kinds(text) == [(78, META, 3), (79, META, 4)]


def test_bibliography_scope_ends_at_the_next_peer_heading() -> None:
    text = (
        "## References\n\n- ADR-078 background\n\n### Detail\n\n- ADR-079 detail\n\n"
        "## Rules\n\nAuthors MUST comply with ADR-078.\n"
    )
    assert _kinds(text) == [(78, META, 3), (79, META, 7), (78, BINDING, 11)]


def test_inline_references_label_is_bibliography() -> None:
    assert _kinds("**References**: ADR-078, ADR-079.\n") == [(78, META, 1), (79, META, 1)]
    assert _kinds("Refs ADR-073, ADR-078 - the debate.\n") == [(78, UNCLASSIFIED, 1)]


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


def test_a_pointer_with_trailing_prose_is_not_a_pointer() -> None:
    """Only a cell that is nothing but the label and the numbers is a pointer."""
    assert _kinds("pins: ADR-080 was the first attempt\n") == [(80, UNCLASSIFIED, 1)]


@pytest.mark.parametrize("verb", ["pass", "passes", "satisfy", "satisfies", "meet", "follows"])
def test_a_compliance_verb_before_the_mention_is_binding(verb: str) -> None:
    assert _kinds(f"Pin changes {verb} ADR-080 first.\n") == [(80, BINDING, 1)]
    assert _kinds(f"Pin changes {verb} the ADR-080 bar.\n") == [(80, BINDING, 1)]


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
# Edge: reported, never failed
# --------------------------------------------------------------------------


def test_parenthetical_and_example_mentions_are_unclassified() -> None:
    """A trailing "(ADR-NNN)" and an example sentence carry no authority signal."""
    assert _kinds("A router retries on a signal it can read (ADR-078).\n") == [
        (78, UNCLASSIFIED, 1)
    ]
    text = '- **What**: The specific conflict (e.g., "architecture violates ADR-007")\n'
    assert _kinds(text) == [(7, UNCLASSIFIED, 1)]


def test_unknown_adr_number_is_counted_not_flagged() -> None:
    unknown: set[int] = set()
    assert _kinds("Authors MUST comply with ADR-999.\n", unknown) == []
    assert unknown == {999}


def test_a_capitalised_wrap_starts_a_new_block_and_loses_the_signal() -> None:
    """Conservative direction: a split can turn BINDING into UNCLASSIFIED and
    never the reverse."""
    text = "Agents MUST honor the policy of\nADR-080 for mirrors.\n"
    assert _kinds(text) == [(80, UNCLASSIFIED, 2)]


def test_same_adr_twice_in_one_file_is_one_baseline_key() -> None:
    found = citations_in("a.md", "MUST obey ADR-078.\n\nMUST also obey ADR-078.\n", STATUSES, set())
    assert [c.key for c in found if c.kind == BINDING] == ["a.md::ADR-078"] * 2
    assert len({c.key for c in found}) == 1


# --------------------------------------------------------------------------
# Repository fixtures
# --------------------------------------------------------------------------


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )


def _adr(adr_dir: Path, number: int, status: str) -> None:
    (adr_dir / f"ADR-{number:03d}-x.md").write_text(
        f"---\nid: ADR-{number:03d}\nstatus: {status}\n---\n\n# ADR-{number:03d}\n",
        encoding="utf-8",
    )


def _make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """A git repo with ADR-042 accepted and ADR-078 proposed, ``files`` staged."""
    _git(tmp_path, "init", "--quiet")
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    adr_dir.mkdir(parents=True)
    _adr(adr_dir, 42, "accepted")
    _adr(adr_dir, 78, "proposed")
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        _git(tmp_path, "add", "--force", "--", rel)
    _git(tmp_path, "add", "--force", "--", ".project-toolkit/architecture")
    return tmp_path


def _baseline(tmp_path: Path, known: list[str]) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"schema_version": "1", "known": known}), encoding="utf-8")
    return path


BAD = "Authors MUST comply with ADR-078.\n"
GOOD = "Authors MUST comply with ADR-042.\n"


def _run(repo: Path, baseline: Path, *extra: str) -> int:
    return main(["--repo-root", str(repo), "--baseline", str(baseline), *extra])


# --------------------------------------------------------------------------
# Ratchet
# --------------------------------------------------------------------------


def test_known_violation_passes_and_names_the_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": BAD})
    code = _run(repo, _baseline(tmp_path, ["CLAUDE.md::ADR-078"]))
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "1 binding violation(s) (1 known)" in out
    assert "1 of 1 tracked rule file(s)" in out


def test_new_violation_fails_and_names_the_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": BAD})
    code = _run(repo, _baseline(tmp_path, []))
    captured = capsys.readouterr()
    assert code == EXIT_REGRESSION
    assert re.search(r"^CLAUDE\.md:1: ", captured.out, re.MULTILINE)
    assert "ADR-078 is proposed" in captured.out
    assert "1 new, 0 stale" in captured.err


def test_a_fix_cannot_hide_a_new_violation_elsewhere(tmp_path: Path) -> None:
    """Identity, not count: one repaired entry and one new one is still red."""
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD, "AGENTS.md": BAD})
    assert _run(repo, _baseline(tmp_path, ["CLAUDE.md::ADR-078"])) == EXIT_REGRESSION


def test_stale_baseline_entry_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD})
    code = _run(repo, _baseline(tmp_path, ["CLAUDE.md::ADR-078"]))
    captured = capsys.readouterr()
    assert code == EXIT_REGRESSION
    assert "no longer produced" in captured.out
    assert "0 new, 1 stale" in captured.err


def test_clean_tree_with_empty_baseline_passes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK


def test_unclassified_does_not_fail_and_verbose_lists_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _make_repo(tmp_path, {"AGENTS.md": "Effort|see the debate (ADR-078)\n"})
    code = _run(repo, _baseline(tmp_path, []), "--verbose")
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert re.search(r"^AGENTS\.md:1: .*unclassified ADR-078", out, re.MULTILINE)
    assert "1 unclassified" in out


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


# --------------------------------------------------------------------------
# Scope: tracked files, every shipped tree
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "AGENTS.md",
        "CLAUDE.md",
        "templates/rules/a.md",
        ".claude/rules/a.md",
        "src/claude/rules/a.md",
        ".github/instructions/a.instructions.md",
        "src/copilot-cli/instructions/a.instructions.md",
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
def test_every_scanned_tree_is_checked(tmp_path: Path, rel: str) -> None:
    """The mirrors are in scope: a clean canonical tree must not let a stale
    mirror ship the violation to plugin consumers."""
    repo = _make_repo(tmp_path, {rel: BAD})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION
    assert _run(repo, _baseline(tmp_path, [f"{rel}::ADR-078"])) == EXIT_OK


def test_a_file_outside_the_scan_set_is_not_read(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD, "docs/notes.md": BAD})
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK


def test_untracked_rule_file_is_never_counted(tmp_path: Path) -> None:
    """Control: the same file staged is red, so the green below is the index."""
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD})
    stray = repo / ".claude" / "rules" / "stray.md"
    stray.parent.mkdir(parents=True)
    stray.write_text(BAD, encoding="utf-8")
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK
    _git(repo, "add", "--force", "--", ".claude/rules/stray.md")
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_REGRESSION


def test_tracked_symlink_leaving_the_repo_is_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text(BAD, encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_repo(repo, {"CLAUDE.md": GOOD})
    (repo / "AGENTS.md").symlink_to(outside)
    _git(repo, "add", "--force", "--", "AGENTS.md")
    # Not followed, and not silent: a skipped tracked file fails the run (issue #6506).
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_CONFIG


# --------------------------------------------------------------------------
# Configuration and external faults
# --------------------------------------------------------------------------


def test_missing_adr_directory_is_a_config_fault(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    assert _run(tmp_path, _baseline(tmp_path, [])) == EXIT_CONFIG


def test_adr_directory_without_records_is_a_config_fault(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": BAD})
    for record in (repo / ".project-toolkit" / "architecture").glob("ADR-*.md"):
        record.unlink()
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_CONFIG


@pytest.mark.parametrize(
    "payload",
    ["not json", "[]", '{"known": "x"}', '{"known": [1]}', '{"counts": {}}'],
)
def test_unusable_baseline_is_a_config_fault(tmp_path: Path, payload: str) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD})
    path = tmp_path / "baseline.json"
    path.write_text(payload, encoding="utf-8")
    assert _run(repo, path) == EXIT_CONFIG


def test_absent_baseline_is_a_config_fault(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": GOOD})
    assert _run(repo, tmp_path / "missing.json") == EXIT_CONFIG


def test_run_that_examined_nothing_is_a_config_fault(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Tracked but deleted from the working tree: nothing was read, so an empty
    findings list is not a pass."""
    repo = _make_repo(tmp_path, {"CLAUDE.md": BAD})
    (repo / "CLAUDE.md").unlink()
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_CONFIG
    assert "examined 0 of 1" in capsys.readouterr().err


def test_root_git_cannot_list_is_an_external_fault(tmp_path: Path) -> None:
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    adr_dir.mkdir(parents=True)
    _adr(adr_dir, 78, "proposed")
    assert _run(tmp_path, _baseline(tmp_path, [])) == EXIT_EXTERNAL


def test_adapter_is_false_on_every_non_ok_exit(tmp_path: Path) -> None:
    assert gate.validate_rule_adr_citations(tmp_path / "no-such-repo") is False


# --------------------------------------------------------------------------
# The shipped tree and the shipped baseline
# --------------------------------------------------------------------------


def test_the_shipped_baseline_matches_the_tracked_tree() -> None:
    """ci-scripts MUST 13: the gate passes against the full corpus, and the
    baseline holds exactly the binding and missing citations the tree produces."""
    repo_root = Path(__file__).resolve().parents[2]
    statuses = gate.adr_statuses(repo_root, repo_root / ".project-toolkit" / "architecture")
    result = gate.scan(repo_root, statuses)
    assert isinstance(result, gate.ScanResult), result
    assert result.examined == result.candidates > 0, result.absent
    baseline = gate.read_baseline(gate._BASELINE_PATH)
    assert isinstance(baseline, set), baseline
    assert baseline == {c.key for c in result.failing}
    assert result.missing == []
    assert main(["--repo-root", str(repo_root)]) == EXIT_OK


def test_unresolvable_path_is_absent_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path, {"CLAUDE.md": BAD})

    def _boom(self: Path, strict: bool = False) -> Path:
        raise OSError("loop")

    monkeypatch.setattr(Path, "resolve", _boom)
    assert gate._readable(repo, "CLAUDE.md") is None


def test_cli_process_exits_nonzero_on_a_new_violation(tmp_path: Path) -> None:
    """ci-scripts.md MUST 10: the exit code is asserted on the process, not on a
    helper's return value."""
    repo = _make_repo(tmp_path, {"CLAUDE.md": BAD})
    script = Path(gate.__file__)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo-root",
            str(repo),
            "--baseline",
            str(_baseline(tmp_path, [])),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert proc.returncode == EXIT_REGRESSION, proc.stderr
    assert re.search(r"^CLAUDE\.md:1: ", proc.stdout, re.MULTILINE)
