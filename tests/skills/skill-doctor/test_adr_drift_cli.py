"""adr_drift.py locate, draft, exit codes, read-only scan, no network, and --help."""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import adr_corpus
import adr_draft
import adr_drift
import pytest
from adr_drift_helpers import (
    ADR_DIR,
    adr_path,
    adr_text,
    commit,
    git,
    init_repo,
    kinds,
    run_cli,
    scan,
    seeded_repo,
)

SCRIPT = Path(__file__).resolve().parents[3] / "src/claude/skills/skill-doctor/scripts/adr_drift.py"
KNOWN = [
    ".project-toolkit/architecture",
    "docs/adr",
    "docs/architecture",
    "docs/decisions",
    "architecture/decisions",
    "doc/adr",
]


def _locate(capsys: pytest.CaptureFixture[str], repo: Path) -> dict[str, Any]:
    code, out, err = run_cli(capsys, "locate", "--repo", str(repo))
    assert code == 0, err
    located: dict[str, Any] = json.loads(out)
    return located


@pytest.mark.parametrize("folder", KNOWN)
def test_locate_finds_each_known_folder(tmp_path, capsys, folder):
    repo = seeded_repo(tmp_path / "repo", {f"{folder}/ADR-001-first.md": adr_text(1)})

    located = _locate(capsys, repo)

    assert [d["path"] for d in located["adr_dirs"]] == [folder]
    assert located["primary"] == folder and located["next_number"] == 2


def test_locate_reads_the_adr_tools_marker_and_it_is_authoritative(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {
            ".adr-dir": "records\n",
            "records/0001-first.md": "# 1. First\n",
            "docs/adr/ADR-001-x.md": adr_text(1),
        },
    )

    located = _locate(capsys, repo)

    assert [d["path"] for d in located["adr_dirs"]] == ["records"]
    assert located["markers"] == [".adr-dir"] and located["primary"] == "records"


def test_locate_ignores_a_marker_that_points_outside_the_repo(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo", {".adr-dir": "../elsewhere\n", "docs/adr/ADR-001-x.md": adr_text(1)}
    )

    assert _locate(capsys, repo)["primary"] == "docs/adr"


def test_locate_reports_adr_tools_naming(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {
            "doc/adr/0001-first.md": "# 1. First\n\n## Status\n\nAccepted\n",
            "doc/adr/0007-last.md": "# 7. Last\n\n## Status\n\nAccepted\n\n## Context\n",
        },
    )

    entry = _locate(capsys, repo)["adr_dirs"][0]

    assert (
        entry["convention"],
        entry["prefix"],
        entry["width"],
        entry["h1_form"],
        entry["count"],
    ) == (
        "NNNN",
        "",
        4,
        "number-dot",
        2,
    )


def test_locate_with_no_folder_has_null_primary_and_next_one(tmp_path, capsys):
    repo = init_repo(tmp_path / "repo")
    commit(repo, {"README.md": "x"}, "docs: readme")

    located = _locate(capsys, repo)

    assert located["adr_dirs"] == [] and located["primary"] is None
    assert located["next_number"] == 1 and located["template_headings"] == []


def test_locate_primary_is_null_with_two_folders(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {"docs/adr/ADR-001-a.md": adr_text(1), "docs/decisions/ADR-002-b.md": adr_text(2)},
    )

    located = _locate(capsys, repo)

    assert len(located["adr_dirs"]) == 2 and located["primary"] is None
    assert located["next_number"] == 3


def test_locate_template_headings_come_from_the_newest_adr(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo", {adr_path(1): adr_text(1), adr_path(2): adr_text(2)})

    assert _locate(capsys, repo)["template_headings"] == ["Status", "Context", "Decision"]


def test_locate_from_a_subdirectory_resolves_the_repo_root(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")
    (repo / "sub").mkdir()

    assert _locate(capsys, repo / "sub")["primary"] == ADR_DIR


def _draft_source(tmp_path: Path, capsys, adrs: dict[str, str], subjects: list[str]):
    repo = seeded_repo(tmp_path / "repo", adrs)
    for index, subject in enumerate(subjects):
        commit(repo, {f"f{index}.txt": "1"}, f"feat: {subject}\n\nBody for {subject}.")
    result = scan(capsys, repo)
    return repo, result, tmp_path / "out" / "scan.json"


def _draft(
    capsys: pytest.CaptureFixture[str],
    scan_file: Path,
    finding: dict[str, Any],
    out: Path,
    *extra: str,
) -> tuple[int, str, str]:
    return run_cli(
        capsys, "draft", "--scan", str(scan_file), "--id", finding["id"], "--out", str(out), *extra
    )


def test_two_drafts_in_one_run_get_consecutive_numbers_after_the_highest(tmp_path, capsys):
    repo, result, scan_file = _draft_source(
        tmp_path,
        capsys,
        {adr_path(n): adr_text(n) for n in (1, 2, 3)},
        ["switch to alpha", "adopt beta"],
    )
    out = tmp_path / "drafts"
    findings = kinds(result, "undocumented-decision")

    codes = [_draft(capsys, scan_file, f, out)[0] for f in findings]

    assert codes == [0, 0]
    assert sorted(p.name[:7] for p in out.iterdir()) == ["ADR-004", "ADR-005"]


def test_draft_number_ignores_the_scan_file_and_counts_repo_adrs_added_later(tmp_path, capsys):
    repo, result, scan_file = _draft_source(
        tmp_path, capsys, {adr_path(1): adr_text(1)}, ["adopt beta"]
    )
    commit(repo, {adr_path(9): adr_text(9)}, "docs: add ADR-009")

    code, out, err = _draft(
        capsys, scan_file, kinds(result, "undocumented-decision")[0], tmp_path / "d"
    )

    assert code == 0, err
    assert json.loads(out)["number"] == 10


def test_adr_nnn_convention_gives_prefix_padding_and_h1(tmp_path, capsys):
    repo, result, scan_file = _draft_source(
        tmp_path, capsys, {adr_path(1): adr_text(1)}, ["adopt structured logging"]
    )
    target = repo / ADR_DIR

    code, out, _ = _draft(capsys, scan_file, kinds(result, "undocumented-decision")[0], target)

    path = Path(json.loads(out)["written"])
    text = path.read_text(encoding="utf-8")
    assert code == 0 and path.name == "ADR-002-adopt-structured-logging.md"
    assert "# ADR-002: Adopt structured logging" in text
    assert text.startswith("---\nid: ADR-002\nstatus: proposed\n")


def test_nnnn_convention_gives_plain_prefix_width_four_and_number_dot_h1(tmp_path, capsys):
    adrs = {"docs/adr/0001-first.md": "# 1. First\n\n## Status\n\nAccepted\n\n## Context\n\nx\n"}
    repo, result, scan_file = _draft_source(tmp_path, capsys, adrs, ["adopt structured logging"])

    code, out, _ = _draft(
        capsys, scan_file, kinds(result, "undocumented-decision")[0], repo / "docs/adr"
    )

    path = Path(json.loads(out)["written"])
    assert code == 0 and path.name == "0002-adopt-structured-logging.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# 2. Adopt structured logging") and "---" not in text


def test_default_status_is_proposed_and_status_can_be_set(tmp_path, capsys):
    repo, result, scan_file = _draft_source(
        tmp_path, capsys, {adr_path(1): adr_text(1)}, ["adopt a", "adopt b"]
    )
    first, second = kinds(result, "undocumented-decision")

    _, out_default, _ = _draft(capsys, scan_file, first, tmp_path / "d")
    _, out_set, _ = _draft(capsys, scan_file, second, tmp_path / "d", "--status", "Accepted")

    default_text = Path(json.loads(out_default)["written"]).read_text(encoding="utf-8")
    set_text = Path(json.loads(out_set)["written"]).read_text(encoding="utf-8")
    assert "## Status\n\nProposed\n" in default_text and "## Status\n\nAccepted\n" in set_text


def test_uncovered_heading_reads_not_recorded_and_sources_are_linked(tmp_path, capsys):
    adrs = {adr_path(1): adr_text(1).replace("## Decision", "## Consequences\n\nx\n\n## Decision")}
    repo, result, scan_file = _draft_source(tmp_path, capsys, adrs, ["adopt structured logging"])
    finding = kinds(result, "undocumented-decision")[0]

    _, out, _ = _draft(capsys, scan_file, finding, tmp_path / "d")

    text = Path(json.loads(out)["written"]).read_text(encoding="utf-8")
    assert "## Consequences\n\nNot recorded in the source.\n" in text
    assert "## Context\n\nBody for adopt structured logging." in text
    assert f"Commit: {finding['evidence']['sha']}" in text


def test_draft_without_a_references_heading_appends_a_source_section(tmp_path, capsys):
    repo, result, scan_file = _draft_source(
        tmp_path, capsys, {adr_path(1): adr_text(1)}, ["adopt a"]
    )

    _, out, _ = _draft(capsys, scan_file, kinds(result, "undocumented-decision")[0], tmp_path / "d")

    assert "## Source\n\n- Commit: " in Path(json.loads(out)["written"]).read_text(encoding="utf-8")


def test_draft_into_a_repo_folder_that_is_not_an_adr_folder_exits_2(tmp_path, capsys):
    repo, result, scan_file = _draft_source(
        tmp_path, capsys, {adr_path(1): adr_text(1)}, ["adopt a"]
    )
    finding = kinds(result, "undocumented-decision")[0]

    code, _, err = _draft(capsys, scan_file, finding, repo / "docs" / "notes")

    assert code == 2 and "not an ADR folder" in err
    assert not (repo / "docs").exists()


def test_draft_into_a_repo_adr_folder_and_outside_the_repo_both_work(tmp_path, capsys):
    repo, result, scan_file = _draft_source(
        tmp_path, capsys, {adr_path(1): adr_text(1)}, ["adopt a"]
    )
    finding = kinds(result, "undocumented-decision")[0]

    inside = _draft(capsys, scan_file, finding, repo / ADR_DIR)[0]
    outside = _draft(capsys, scan_file, finding, tmp_path / "elsewhere")[0]

    assert (inside, outside) == (0, 0)


def test_existing_target_exits_1_and_keeps_its_bytes(tmp_path, capsys, monkeypatch):
    repo, result, scan_file = _draft_source(
        tmp_path, capsys, {adr_path(1): adr_text(1)}, ["adopt a"]
    )
    finding = kinds(result, "undocumented-decision")[0]
    out = tmp_path / "d"
    out.mkdir()
    taken = out / "ADR-002-adopt-a.md"
    taken.write_bytes(b"precious")
    # Simulate the race: another writer took the number between the listing and the open.
    monkeypatch.setattr(adr_draft, "_highest_number", lambda *folders: 1)

    code, _, err = _draft(capsys, scan_file, finding, out)

    assert code == 1 and "already exists" in err
    assert taken.read_bytes() == b"precious"


def test_draft_rejects_unknown_id_unreadable_scan_and_non_draftable_kind(tmp_path, capsys):
    repo, result, scan_file = _draft_source(
        tmp_path, capsys, {adr_path(1): adr_text(1), adr_path(4): adr_text(4)}, ["adopt a"]
    )
    gap = kinds(result, "adr-number-gap")[0]

    unknown = run_cli(
        capsys, "draft", "--scan", str(scan_file), "--id", "nope", "--out", str(tmp_path / "d")
    )
    unreadable = run_cli(
        capsys, "draft", "--scan", str(tmp_path / "x"), "--id", "a", "--out", str(tmp_path / "d")
    )
    not_draftable = _draft(capsys, scan_file, gap, tmp_path / "d")

    assert unknown[0] == unreadable[0] == not_draftable[0] == 2
    assert "not draftable" in not_draftable[2]


def _digest(repo: Path) -> dict[str, str]:
    return {
        str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(repo.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(repo).parts[:1]
    }


def test_scan_is_read_only_even_with_a_dirty_tree(tmp_path, capsys):
    repo, _, _ = _draft_source(tmp_path, capsys, {adr_path(1): adr_text(1)}, ["adopt a"])
    (repo / "dirty.txt").write_text("untracked", encoding="utf-8")
    (repo / adr_path(1)).write_text(adr_text(1, body="edited"), encoding="utf-8")
    before = (_digest(repo), git(repo, "status", "--porcelain"))

    scan(capsys, repo, name="again.json")

    assert (_digest(repo), git(repo, "status", "--porcelain")) == before


def test_scan_refuses_an_output_inside_the_repository(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")

    code, _, err = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(repo / "scan.json"))

    assert code == 2 and "inside the repository" in err
    assert not (repo / "scan.json").exists()


def test_scan_makes_no_network_connection(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")
    commit(repo, {"a.txt": "1"}, "feat: adopt a thing (#3)")

    def refuse(*_args, **_kwargs):
        raise AssertionError("scan opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    result = scan(capsys, repo)

    assert result["examined"] == 2


def test_exit_0_for_a_clean_scan_with_findings(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo", {adr_path(1): adr_text(1), adr_path(4): adr_text(4)})

    code, out, _ = run_cli(capsys, "scan", "--repo", str(repo), "--out", str(tmp_path / "o.json"))

    assert code == 0 and "finding(s)" in out


def test_exit_2_for_a_directory_that_is_not_a_git_repository(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()

    scan_code = run_cli(capsys, "scan", "--repo", str(plain), "--out", str(tmp_path / "o.json"))[0]
    locate_code = run_cli(capsys, "locate", "--repo", str(plain))[0]
    missing_code = run_cli(capsys, "locate", "--repo", str(tmp_path / "absent"))[0]

    assert (scan_code, locate_code, missing_code) == (2, 2, 2)


def test_exit_2_for_bad_max_commits_and_missing_arguments(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo")

    zero = run_cli(
        capsys, "scan", "--repo", str(repo), "--out", str(tmp_path / "o.json"), "--max-commits", "0"
    )
    with pytest.raises(SystemExit) as no_out:
        adr_drift.main(["scan", "--repo", str(repo)])
    with pytest.raises(SystemExit) as no_command:
        adr_drift.main([])

    assert zero[0] == 2 and no_out.value.code == 2 and no_command.value.code == 2


def test_exit_3_when_a_git_command_fails_or_git_is_missing(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")
    args = ["scan", "--repo", str(repo), "--out", str(tmp_path / "o.json")]

    def fail(*_args, **_kwargs):
        raise adr_corpus.GitError("git log exited 128: boom")

    monkeypatch.setattr(adr_drift, "read_commits", fail)
    failed = run_cli(capsys, *args)
    monkeypatch.undo()
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    missing = run_cli(capsys, *args)

    assert failed[0] == 3 and "boom" in failed[2]
    assert missing[0] == 3 and "git is not on PATH" in missing[2]


@pytest.mark.parametrize(
    ("command", "flag"), [("locate", "--repo"), ("scan", "--with-align"), ("draft", "--status")]
)
def test_every_subcommand_has_help(command, flag):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), command, "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert proc.returncode == 0 and "usage:" in proc.stdout and flag in proc.stdout


def _process(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_the_script_runs_as_a_process_and_scan_exit_codes_match_main(tmp_path):
    repo = seeded_repo(tmp_path / "repo")
    located = _process("locate", "--repo", str(repo))
    bad = _process("scan", "--repo", str(tmp_path), "--out", str(tmp_path / "o.json"))

    assert located.returncode == 0 and json.loads(located.stdout)["primary"] == ADR_DIR
    assert bad.returncode == 2 and bad.stderr.startswith("error:")
