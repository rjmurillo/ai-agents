"""Tests for scripts/validation/check_rule_adr_citations.py (issue #5200).

pos: each non-accepted status cited with a binding signal is flagged, including
the shapes of the issue's two live instances. neg: accepted ADRs, code spans,
fences, comments, frontmatter, paths, bibliography and lineage clauses are not.
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
# Edge: reported, never failed
# --------------------------------------------------------------------------


def test_terse_agents_md_pointer_is_unclassified() -> None:
    """AGENTS.md:16 `pins: ADR-080` carries no signal either way."""
    assert _kinds("Effort|by task shape|pins: ADR-080\n") == [(80, UNCLASSIFIED, 1)]


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
    repo = _make_repo(tmp_path, {"AGENTS.md": "Effort|pins: ADR-078\n"})
    code = _run(repo, _baseline(tmp_path, []), "--verbose")
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert re.search(r"^AGENTS\.md:1: .*unclassified ADR-078", out, re.MULTILINE)
    assert "1 unclassified" in out


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
    assert _run(repo, _baseline(tmp_path, [])) == EXIT_OK


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
    """ci-scripts.md MUST 13: the gate passes against the full corpus. Also pins
    the issue's live CLAUDE.md instance so the baseline cannot silently drop it."""
    repo_root = Path(__file__).resolve().parents[2]
    statuses = gate.adr_statuses(repo_root, repo_root / ".project-toolkit" / "architecture")
    result = gate.scan(repo_root, statuses)
    assert isinstance(result, gate.ScanResult), result
    assert result.examined == result.candidates > 0, result.absent
    baseline = gate.read_baseline(gate._BASELINE_PATH)
    assert isinstance(baseline, set), baseline
    assert baseline == {c.key for c in result.binding}
    assert "CLAUDE.md::ADR-078" in baseline
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
