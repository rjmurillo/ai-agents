"""Tests for scripts/validation/check_adr_supersession_citations.py.

pos: the ADR-107 Related Decisions text as it stood on main, and MUST, "per",
"governs" and "current owner" citations of a superseded record, fail.
neg: lineage, named successors, own `supersedes`, quotes, history words,
negation, code, fences, paths, other statuses and retired citers pass, as does
the PR #7482 ADR-107 wording. edge: split quotes, unclassified mentions, the rule
gate's META verdict, a long negated list. CLI exits and the pre_pr row.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_adr_supersession_citations as gate
import check_rule_adr_citations as rule_gate
from check_adr_lifecycle import Record, collect_records
from check_adr_supersession_citations import (
    AUTHORITY,
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REGRESSION,
    HISTORY,
    UNCLASSIFIED,
    build_corpus,
    citations_in,
    main,
    validate_adr_supersession_citations,
)


def _record(number: int, status: str, supersedes=None, superseded_by=None) -> Record:
    return Record(
        number=number,
        path=f"ADR-{number:03d}.md",
        frontmatter={
            "status": status,
            "supersedes": supersedes or [],
            "superseded-by": superseded_by,
        },
        body="",
    )


#: ADR-080 -> ADR-111; ADR-079 -> ADR-091 -> ADR-092; ADR-052 -> ADR-109;
#: ADR-036 -> ADR-052. ADR-002 is deprecated, ADR-078 proposed.
CORPUS = build_corpus(
    [
        _record(2, "deprecated"),
        _record(36, "superseded", superseded_by="ADR-052"),
        _record(52, "superseded", supersedes=["ADR-036"], superseded_by="ADR-109"),
        _record(78, "proposed"),
        _record(79, "superseded", superseded_by="ADR-091"),
        _record(80, "superseded", superseded_by="ADR-111"),
        _record(91, "superseded", superseded_by="ADR-092"),
        _record(92, "accepted", supersedes=["ADR-091"]),
        _record(107, "proposed"),
        _record(109, "accepted", supersedes=["ADR-052"]),
        _record(111, "accepted", supersedes=["ADR-080"]),
    ]
)

#: ADR-107 lines 699-714 as they stood on main at 797c1762c (2026-11-20).
ADR_107_AS_IT_STOOD = """\
## Related Decisions

- ADR-101 (enforcement planes, `proposed`, `implemented: false`): corroborates, does not
  authorize, the P0-advisory reading in section 2.
- ADR-105 (terminal-state completion contract): source of the precedence chain this record
  extends.
- ADR-085 (cross-harness permission surface asymmetry, `accepted`): evidence that harness
  differences are real, which is why R1 is rejected and why the permission rung is
  harness-conditional.
- ADR-094 (govern Copilot CLI compatibility through executable surfaces, `accepted`): executable
  configuration is the version record; ADR prose must not freeze versions or counts.
- ADR-080 (model pin justification policy): owns `model:` on any authored artifact. Source of the
  evidence, owner, and expiry shape used by the adapter exception process.
- ADR-052 (template strategy, `superseded` by ADR-109 2026-09-11, `implemented: false`): kept as
  history. ADR-109 is the governing agent-direction record.
- ADR-036 (two-source agent templates, superseded by ADR-052, procedure still operative).
"""

#: An excerpt of that span as PR #7482 rewrote it (three of its bullets).
ADR_107_FIXED = """\
## Related Decisions

- ADR-111 (skill model pins project per harness, `accepted`): owns `model:` on any authored
  artifact. It supersedes ADR-080.
- ADR-080 (model pin justification policy, `superseded` by ADR-111): kept as history. Origin of
  the measured-evidence bar (rule 2, restated as ADR-111 rule 2) behind section 7's overlay rule.
  Owner and expiry come from this record, not from ADR-080.
- ADR-052 (template strategy, `superseded` by ADR-109 2026-09-11, `implemented: false`): kept as
  history. ADR-109 is the governing agent-direction record.
"""


def _kinds(text: str, own: int = 107) -> list[tuple[int, str, int]]:
    return [(c.adr, c.kind, c.line) for c in citations_in("f.md", own, text, CORPUS)]


def _authority(text: str, own: int = 107) -> list[tuple[int, int]]:
    return [(adr, line) for adr, kind, line in _kinds(text, own) if kind == AUTHORITY]


# --------------------------------------------------------------------------
# Positive: current-authority citations of a superseded record fail
# --------------------------------------------------------------------------


def test_adr_107_line_710_as_it_stood_is_authority() -> None:
    """The defect that prompted this gate: ADR-080 named as the owner of `model:`."""
    assert _authority(ADR_107_AS_IT_STOOD) == [(80, 12)]


def test_rule_gate_classifies_line_710_as_bibliography_meta() -> None:
    """Why reuse of the rule gate's classifier was not enough: `## Related
    Decisions` matches its bibliography heading, so the ADR-080 bullet reads as META."""
    found = rule_gate.citations_in("f.md", ADR_107_AS_IT_STOOD, {80: "superseded"}, set())
    assert [(c.adr, c.kind) for c in found] == [(80, rule_gate.META)]


@pytest.mark.parametrize(
    "text",
    [
        "- ADR-080 now governs model pins and requires evidence.\n",
        "- Model policy has one current owner, ADR-080.\n",
        "Per ADR-080 (model pin policy), skills inherit the model.\n",
        "Agents MUST cite ADR-080 rule 2 for every pin.\n",
        "Pins stay under ADR-080 until the next release.\n",
        "ADR-080 is the authority for model pins.\n",
        "ADR-080 is used to decide the model pin and governs it.\n",
        "Cross-origin rules are owned by ADR-080.\n",
    ],
)
def test_authority_signal_on_a_superseded_record_fails(text: str) -> None:
    assert _authority(text) == [(80, 1)]


def test_wrapped_bullet_continuation_is_one_sentence() -> None:
    text = "- ADR-080 (model pin policy) is the record that\n  governs model pins.\n"
    assert _authority(text) == [(80, 1)]


# --------------------------------------------------------------------------
# Negative: historical mentions pass
# --------------------------------------------------------------------------


def test_fixed_adr_107_wording_passes() -> None:
    assert _authority(ADR_107_FIXED) == []
    assert {kind for _, kind, _ in _kinds(ADR_107_FIXED)} == {HISTORY}


@pytest.mark.parametrize(
    "text",
    [
        "ADR-111 supersedes ADR-080 and governs model pins.\n",
        "ADR-080, superseded by ADR-111, once governed model pins.\n",
        "ADR-080 (`superseded` by ADR-111) governs nothing now.\n",
        "Model pins were governed by ADR-080; ADR-111 governs them now.\n",
        "The supersession chain ADR-079 to ADR-092 governs version policy.\n",
        "Successor filed per the ADR-052 precedent and named here.\n",
        "Historically, ADR-080 governed model pins.\n",
        "Owner and expiry come from this record, not from ADR-080.\n",
        'The "Tier 1 per ADR-080" framing governs nothing.\n',
        "Skills MUST NOT cite ADR-080 as authority.\n",
        "Skills must not cite ADR-052 or ADR-080 as the owner of pins.\n",
        "Agents MUST NOT cite ADR-036, ADR-052, or ADR-080.\n",
        "This record is not governed by ADR-080.\n",
    ],
)
def test_historical_mention_passes(text: str) -> None:
    assert _authority(text) == []


def test_quotation_split_by_a_capitalised_wrap_is_still_quoted() -> None:
    """The ADR-089 tier-taxonomy paragraph: the quote opens on the previous line, and the shared
    block splitter starts a new block at the capital S."""
    text = 'The "Tier 1\n   Semantic / Tier 3 Causal, per ADR-080" framing is fabricated.\n'
    assert _authority(text) == []


def test_record_cited_in_its_own_supersedes_list_is_history() -> None:
    assert _kinds("ADR-080 governs model pins.\n", own=111) == [(80, HISTORY, 1)]


@pytest.mark.parametrize(
    "text",
    [
        "ADR-002 governs X. ADR-078 governs Y. ADR-111 governs Z.\n",
        "Run `ADR-080 governs` in a code span.\n",
        "```text\nADR-080 governs model pins.\n```\n",
        "1. Example:\n\n   ```text\n   ADR-080 governs model pins.\n   ```\n",
        "<!-- ADR-080 governs model pins. -->\n",
        "See ADR-080-model-pin-justification-policy.md:12 which governs pins.\n",
        "---\nstatus: accepted\nnote: ADR-080 governs\n---\nBody.\n",
    ],
)
def test_non_citation_text_is_never_seen(text: str) -> None:
    assert _kinds(text) == []


def test_mention_with_no_signal_is_unclassified_not_failed() -> None:
    assert _kinds("ADR-080 and ADR-094 both mention pins.\n") == [(80, UNCLASSIFIED, 1)]


def test_own_number_is_skipped() -> None:
    assert _kinds("ADR-080 governs model pins.\n", own=80) == []


@pytest.mark.timeout(10)
def test_long_negated_list_is_classified_in_linear_time() -> None:
    text = "Skills must not cite " + "ADR-052, " * 40 + "x ADR-080 owns pins.\n"
    assert _authority(text) == [(80, 1)]


# --------------------------------------------------------------------------
# Corpus edges
# --------------------------------------------------------------------------


def test_successor_chain_is_transitive() -> None:
    assert CORPUS.chain(79) == [91, 92]
    assert CORPUS.terminal_successor(79) == 92
    assert CORPUS.terminal_successor(80) == 111


def test_successor_read_from_the_other_side_when_superseded_by_is_missing() -> None:
    dated = _record(42, "accepted", "ADR-005 (2026-05-01)")
    corpus = build_corpus([_record(5, "superseded"), dated])
    assert corpus.chain(5) == [42] and corpus.supersedes[42] == {5}  # the date is not an id


def test_successor_cycle_terminates() -> None:
    corpus = build_corpus(
        [
            _record(1, "superseded", superseded_by="ADR-002"),
            _record(2, "superseded", superseded_by="ADR-001"),
        ]
    )
    assert corpus.chain(1) == [2, 1]


# --------------------------------------------------------------------------
# CLI and ratchet against a real git repository
# --------------------------------------------------------------------------

_ADR_DIR = ".project-toolkit/architecture"


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )


def _adr(
    number: int, status: str, body: str, supersedes: str = "[]", superseded_by: str = "null"
) -> str:
    return (
        f"---\nid: ADR-{number:03d}\nstatus: {status}\ndate: 2026-11-20\n"
        f"supersedes: {supersedes}\nsuperseded-by: {superseded_by}\n---\n\n"
        f"# ADR-{number:03d}: Fixture\n\n{body}"
    )


def _repo(tmp_path: Path, live_body: str) -> Path:
    repo = tmp_path / "repo"
    adr_dir = repo / _ADR_DIR
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-080-old.md").write_text(
        _adr(80, "superseded", "Old pin policy.\n", superseded_by="ADR-111"), encoding="utf-8"
    )
    (adr_dir / "ADR-111-new.md").write_text(
        _adr(111, "accepted", "New pin policy.\n", supersedes="[ADR-080]"), encoding="utf-8"
    )
    (adr_dir / "ADR-107-live.md").write_text(_adr(107, "proposed", live_body), encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    return repo


def _baseline(tmp_path: Path, known: list[str]) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"known": known}), encoding="utf-8")
    return path


_KEY = f"{_ADR_DIR}/ADR-107-live.md::ADR-080"


def test_cli_fails_on_a_new_authority_citation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, ADR_107_AS_IT_STOOD)
    code = main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, []))])
    out = capsys.readouterr()
    assert code == EXIT_REGRESSION
    assert "ADR-107-live.md:" in out.out and "cite ADR-111 instead" in out.out
    assert "across 3 of 3 tracked ADR record(s)" in out.err


def test_cli_passes_when_the_violation_is_known(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, ADR_107_AS_IT_STOOD)
    assert (
        main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, [_KEY]))]) == EXIT_OK
    )
    assert "at baseline: 1 authority violation(s)" in capsys.readouterr().out


def test_cli_fails_on_a_stale_baseline_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, ADR_107_FIXED)
    code = main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, [_KEY]))])
    assert code == EXIT_REGRESSION
    assert "baseline entry no longer produced" in capsys.readouterr().out


def test_cli_passes_on_fixed_wording_with_empty_baseline(tmp_path: Path) -> None:
    repo = _repo(tmp_path, ADR_107_FIXED)
    assert main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, []))]) == EXIT_OK


def test_cli_ignores_a_retired_citing_record(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "Old text.\n")
    (repo / _ADR_DIR / "ADR-050-retired.md").write_text(
        _adr(50, "deprecated", "ADR-080 governs model pins.\n"), encoding="utf-8"
    )
    _git(repo, "add", "-A")
    assert main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, []))]) == EXIT_OK


def test_cli_ignores_an_untracked_record(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "Clean.\n")
    (repo / _ADR_DIR / "ADR-120-draft.md").write_text(
        _adr(120, "proposed", "ADR-080 governs model pins.\n"), encoding="utf-8"
    )
    assert main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, []))]) == EXIT_OK


@pytest.mark.parametrize("opener", ["```text\n", "1. Example:\n\n   ```text\n   "])
def test_cli_fails_on_an_unterminated_fence(
    opener: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, opener + "ADR-080 governs model pins.\n")
    args = ["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, []))]
    assert main(args) == EXIT_REGRESSION
    assert "code fence is never closed" in capsys.readouterr().err


def test_cli_exits_config_without_an_adr_directory(tmp_path: Path) -> None:
    assert (
        main(["--repo-root", str(tmp_path), "--baseline", str(_baseline(tmp_path, []))])
        == EXIT_CONFIG
    )


def test_cli_exits_config_on_an_unreadable_baseline(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "Clean.\n")
    missing = tmp_path / "missing.json"
    assert main(["--repo-root", str(repo), "--baseline", str(missing)]) == EXIT_CONFIG


def test_cli_exits_config_when_no_record_is_tracked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, "Clean.\n")
    _git(repo, "rm", "-q", "--cached", "-r", ".")
    assert (
        main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, []))]) == EXIT_CONFIG
    )
    assert "examined 0 of 0" in capsys.readouterr().err


def test_cli_exits_external_when_git_cannot_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, "Clean.\n")
    monkeypatch.setattr(gate, "tracked_files", lambda root, globs: None)
    code = main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, []))])
    assert code == EXIT_EXTERNAL
    assert "examined 0 record(s)" in capsys.readouterr().err


@pytest.mark.parametrize("break_it", ["directory", "no-status"])
def test_cli_exits_config_on_a_tracked_record_it_cannot_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], break_it: str
) -> None:
    repo, record = _repo(tmp_path, "Clean.\n"), tmp_path / "repo" / _ADR_DIR / "ADR-121-x.md"
    body = _adr(121, "accepted", "") if break_it == "directory" else "---\nid: ADR-121\n---\n"
    record.write_text(body, encoding="utf-8")
    _git(repo, "add", "-A")
    if break_it == "directory":  # still tracked, but no longer a regular file on disk
        record.unlink()
        record.mkdir()
    code = main(["--repo-root", str(repo), "--baseline", str(_baseline(tmp_path, []))])
    assert code == EXIT_CONFIG
    assert "ADR-121-x.md: [adr-supersession-citation] tracked ADR" in capsys.readouterr().err


def test_scan_reports_a_record_whose_read_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path, ADR_107_AS_IT_STOOD)
    records, _ = collect_records(repo / _ADR_DIR, repo)
    real_read = Path.read_text

    def _read(path: Path, encoding: str = "utf-8", errors: str = "strict") -> str:
        if path.name == "ADR-107-live.md":
            raise PermissionError("denied")
        return real_read(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", _read)
    result = gate.scan(repo, records, build_corpus(records))
    assert not isinstance(result, str)
    assert result.absent == [f"{_ADR_DIR}/ADR-107-live.md"]
    assert result.citations == []


def test_script_exits_nonzero_as_a_subprocess(tmp_path: Path) -> None:
    repo = _repo(tmp_path, ADR_107_AS_IT_STOOD)
    script = _VALIDATION_DIR / "check_adr_supersession_citations.py"
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
        check=False,
    )
    assert proc.returncode == EXIT_REGRESSION


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------


def _registered_row():
    from pre_pr_sequence import _SEQUENCE

    wired = [gate for gate in _SEQUENCE if gate.name == "ADR Supersession Citations (ratchet)"]
    assert len(wired) == 1, f"expected exactly one row, found {len(wired)}"
    return wired[0]


def test_the_registered_row_calls_this_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import pre_pr_sequence as sequence

    seen: list[Path] = []

    def _spy(repo_root: Path) -> bool:
        seen.append(repo_root)
        return True

    monkeypatch.setattr(sequence, "validate_adr_supersession_citations", _spy)
    row = _registered_row()
    # _root_only resolves the validator by name at call time, so the spy is seen.
    assert row.run(tmp_path, argparse.Namespace()) is True
    assert seen == [tmp_path]


def test_adapter_returns_false_when_the_gate_cannot_run(tmp_path: Path) -> None:
    assert validate_adr_supersession_citations(tmp_path / "no-such-repo") is False


def test_pre_pr_reexports_the_adapter() -> None:
    from pre_pr import validate_adr_supersession_citations as reexported

    assert reexported is validate_adr_supersession_citations
