"""adr_drift.py scan: git-history findings, suppression, PR export, truncation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from adr_drift_helpers import adr_path, adr_text, commit, git, kinds, run_cli, scan, seeded_repo


def _repo(tmp_path: Path, adrs: dict[str, str] | None = None) -> Path:
    return seeded_repo(tmp_path / "repo", adrs)


def _subjects(result: dict[str, Any]) -> list[str]:
    return [f["evidence"]["subject"] for f in kinds(result, "undocumented-decision")]


def test_decision_verb_in_a_subject_is_a_heuristic_finding(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {"a.txt": "1"}, "feat: switch to httpx for requests")

    found = kinds(scan(capsys, repo), "undocumented-decision")

    assert len(found) == 1
    assert found[0]["confidence"] == "heuristic"
    assert "verb: switch to" in found[0]["evidence"]["signals"]
    assert found[0]["fix"][0] == "draft" and "--id" in found[0]["fix"]
    assert "Candidate" in found[0]["suggested_fix"]


def test_plain_fix_commit_is_not_a_decision(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {"a.txt": "1"}, "fix: correct a typo in the readme")

    assert _subjects(scan(capsys, repo)) == []


def test_breaking_change_footer_and_bang_are_signals(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {"a.txt": "1"}, "refactor!: rename the config key")
    commit(repo, {"b.txt": "1"}, "chore: tidy\n\nBREAKING CHANGE: the flag is gone")

    found = kinds(scan(capsys, repo), "undocumented-decision")

    assert len(found) == 2
    assert all("breaking-change" in f["evidence"]["signals"] for f in found)
    assert all(f["severity"] == "medium" for f in found)


def test_dependency_add_and_remove_are_signals_but_a_version_bump_is_not(tmp_path, capsys):
    repo = _repo(tmp_path)
    manifest = '{\n  "dependencies": {\n    "left-pad": "^1.0.0"\n  }\n}\n'
    commit(repo, {"package.json": manifest}, "chore: add a package")
    commit(repo, {"package.json": manifest.replace("^1.0.0", "^1.1.0")}, "chore: bump a package")
    commit(repo, {"package.json": '{\n  "dependencies": {\n  }\n}\n'}, "chore: remove a package")

    found = kinds(scan(capsys, repo), "undocumented-decision")

    signals = sorted(s for f in found for s in f["evidence"]["signals"])
    assert signals == ["dependency-added: left-pad", "dependency-removed: left-pad"]


def test_pyproject_dependency_line_is_a_signal(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(
        repo,
        {"pyproject.toml": '[project]\ndependencies = [\n  "requests>=2",\n]\n'},
        "chore: deps",
    )

    found = kinds(scan(capsys, repo), "undocumented-decision")

    assert found and "dependency-added: requests" in found[0]["evidence"]["signals"]


def test_a_pr_number_alone_is_not_a_signal(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {"a.txt": "1"}, "fix: handle empty input (#41)")

    assert _subjects(scan(capsys, repo)) == []


def test_commit_that_edits_an_adr_folder_is_not_flagged(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {adr_path(2): adr_text(2)}, "docs: adopt a new approach in ADR-002")

    assert _subjects(scan(capsys, repo)) == []


def test_every_decision_finding_is_cited_with_a_sha_and_date(tmp_path, capsys):
    repo = _repo(tmp_path)
    sha = commit(repo, {"a.txt": "1"}, "feat: migrate to the new queue")

    found = kinds(scan(capsys, repo), "undocumented-decision")[0]["evidence"]

    assert found["sha"] == sha and found["date"][:4].isdigit()


def _suppressing_adr(token: str) -> dict[str, str]:
    return {adr_path(1): adr_text(1, body=f"Context mentions {token}.")}


@pytest.mark.parametrize(
    "form", ["full-sha", "short-sha-7", "pr-number", "pr-url", "dependency-name"]
)
def test_an_adr_naming_the_commit_suppresses_its_finding(tmp_path, capsys, form):
    repo = _repo(tmp_path)
    sha = commit(
        repo,
        {"package.json": '{\n  "dependencies": {\n    "left-pad": "^1.0.0"\n  }\n}\n'},
        "feat: switch to left-pad (#77)",
    )
    token = {
        "full-sha": sha,
        "short-sha-7": sha[:7],
        "pr-number": "#77",
        "pr-url": "https://github.com/o/r/pull/77",
        "dependency-name": "left-pad",
    }[form]
    assert kinds(scan(capsys, repo, name="before.json"), "undocumented-decision")
    commit(repo, {adr_path(1): adr_text(1, body=f"Context mentions {token}.")}, "docs: note it")

    result = scan(capsys, repo, name="after.json")

    remaining = kinds(result, "undocumented-decision")
    if form == "dependency-name":
        # The verb signal stays: only the dependency signal is suppressed.
        assert all(
            not s.startswith("dependency") for f in remaining for s in f["evidence"]["signals"]
        )
    else:
        assert remaining == [] and result["suppressed"] >= 1


def test_a_six_character_sha_prefix_does_not_suppress(tmp_path, capsys):
    repo = _repo(tmp_path)
    sha = commit(repo, {"a.txt": "1"}, "feat: switch to httpx")
    commit(repo, {adr_path(1): adr_text(1, body=f"Mentions {sha[:6]}.")}, "docs: note it")

    assert len(kinds(scan(capsys, repo), "undocumented-decision")) == 1


def test_a_draft_written_into_the_repo_suppresses_its_own_finding(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {"a.txt": "1"}, "feat: adopt structured logging")
    first = scan(capsys, repo, name="first.json")
    finding = kinds(first, "undocumented-decision")[0]

    code, _, err = run_cli(
        capsys,
        "draft",
        "--scan",
        str(tmp_path / "out" / "first.json"),
        "--id",
        finding["id"],
        "--out",
        str(repo / ".project-toolkit/architecture"),
    )
    assert code == 0, err
    second = scan(capsys, repo, name="second.json")

    assert kinds(second, "undocumented-decision") == []


def test_prs_json_body_with_a_decision_verb_yields_a_finding_with_the_url(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {"a.txt": "1"}, "feat: add the cache layer (#12)")
    prs = tmp_path / "prs.json"
    prs.write_text(
        json.dumps(
            [
                {
                    "number": 12,
                    "title": "Cache layer",
                    "body": "We decided to use Redis.",
                    "url": "https://github.com/o/r/pull/12",
                    "review_rounds": 2,
                }
            ]
        ),
        encoding="utf-8",
    )

    result = scan(capsys, repo, "--prs-json", str(prs))

    found = kinds(result, "undocumented-decision")
    assert len(found) == 1
    assert found[0]["evidence"]["pr_url"] == "https://github.com/o/r/pull/12"
    assert result["prs_json"] == {"items": 1, "matched": 1}


def test_the_same_commit_without_prs_json_has_no_finding(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {"a.txt": "1"}, "feat: add the cache layer (#12)")

    assert kinds(scan(capsys, repo), "undocumented-decision") == []


@pytest.mark.parametrize(
    "payload",
    ["{not json", '{"number": 1}', '[{"title": "no number"}]', '[{"number": "7"}]', "[3]"],
)
def test_bad_prs_json_exits_2(tmp_path, capsys, payload):
    repo = _repo(tmp_path)
    prs = tmp_path / "prs.json"
    prs.write_text(payload, encoding="utf-8")

    code, _, err = run_cli(
        capsys,
        "scan",
        "--repo",
        str(repo),
        "--out",
        str(tmp_path / "o.json"),
        "--prs-json",
        str(prs),
    )

    assert code == 2 and "--prs-json" in err
    assert not (tmp_path / "o.json").exists()


def test_missing_prs_json_file_exits_2(tmp_path, capsys):
    code, _, err = run_cli(
        capsys,
        "scan",
        "--repo",
        str(_repo(tmp_path)),
        "--out",
        str(tmp_path / "o.json"),
        "--prs-json",
        str(tmp_path / "absent.json"),
    )

    assert code == 2 and "cannot read" in err


def test_truncated_is_true_when_max_commits_stops_the_walk(tmp_path, capsys):
    repo = _repo(tmp_path)
    for index in range(3):
        commit(repo, {f"f{index}.txt": "1"}, f"chore: step {index}")

    short = scan(capsys, repo, "--max-commits", "2", name="short.json")
    full = scan(capsys, repo, "--max-commits", "50", name="full.json")

    assert (short["examined"], short["truncated"]) == (2, True)
    assert (full["examined"], full["truncated"]) == (4, False)
    assert full["head"] == git(repo, "rev-parse", "HEAD")


def test_exactly_max_commits_of_history_is_not_truncated(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {"a.txt": "1"}, "chore: one")

    result = scan(capsys, repo, "--max-commits", "2")

    assert (result["examined"], result["truncated"]) == (2, False)


def test_since_limits_the_window(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {"a.txt": "1"}, "chore: old", date="2020-01-01T00:00:00")
    commit(repo, {"b.txt": "1"}, "chore: new", date="2024-06-01T00:00:00")

    everything = scan(capsys, repo, "--since", "2000-01-01", name="all.json")
    recent = scan(capsys, repo, "--since", "2022-01-01", name="recent.json")

    assert everything["examined"] == 3
    assert recent["examined"] == 1 and recent["truncated"] is False


def test_empty_repository_scans_with_no_head(tmp_path, capsys):
    from adr_drift_helpers import init_repo

    repo = init_repo(tmp_path / "repo")

    result = scan(capsys, repo)

    assert result["head"] is None and result["examined"] == 0


def test_commit_replacing_an_accepted_adr_is_a_candidate(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {"a.txt": "1"}, "refactor: replace the approach in ADR-001 with a queue")

    found = kinds(scan(capsys, repo), "adr-superseded-by-commit")

    assert len(found) == 1 and found[0]["confidence"] == "heuristic"
    assert found[0]["evidence"]["number"] == 1 and "Candidate" in found[0]["suggested_fix"]


def test_superseded_adr_or_unrelated_adr_mention_is_not_a_candidate(tmp_path, capsys):
    repo = _repo(tmp_path, {adr_path(1): adr_text(1, status="superseded")})
    commit(repo, {"a.txt": "1"}, "refactor: replace the approach in ADR-001 with a queue")
    commit(repo, {"b.txt": "1"}, "docs: link ADR-001 from the readme")

    assert kinds(scan(capsys, repo), "adr-superseded-by-commit") == []


def test_commit_that_touches_the_adr_itself_is_not_a_candidate(tmp_path, capsys):
    repo = _repo(tmp_path)
    commit(repo, {adr_path(1): adr_text(1, body="edited")}, "docs: ADR-001 replaced wording")

    assert kinds(scan(capsys, repo), "adr-superseded-by-commit") == []


def _cited(tmp_path: Path, date: str = "2025-01-01") -> Path:
    text = adr_text(1, body="Lives in `src/old/module.py`.").replace("2025-01-01", date)
    return _repo(tmp_path, {adr_path(1): text, "src/old/module.py": "x"})


def test_deleting_a_cited_path_after_the_adr_date_is_a_candidate(tmp_path, capsys):
    repo = _cited(tmp_path)
    commit(repo, {"src/old/module.py": None}, "refactor: remove the old module")

    found = kinds(scan(capsys, repo), "adr-contradiction-candidate")

    assert len(found) == 1 and found[0]["evidence"]["cited"] == ["src/old/module.py"]
    assert "Candidate" in found[0]["suggested_fix"]


def test_renaming_a_cited_path_counts_as_removal(tmp_path, capsys):
    repo = _cited(tmp_path)
    git(repo, "mv", "src/old/module.py", "src/old/renamed.py")
    git(repo, "commit", "-q", "-m", "refactor: rename the module")

    assert len(kinds(scan(capsys, repo), "adr-contradiction-candidate")) == 1


def test_unrelated_deletion_or_an_older_commit_is_not_a_candidate(tmp_path, capsys):
    repo = _cited(tmp_path, date="2099-01-01")
    commit(repo, {"src/old/module.py": None}, "refactor: remove the old module")
    other = _cited(tmp_path / "other")
    commit(other, {"src/unrelated.py": "x"}, "feat: add a file")
    commit(other, {"src/unrelated.py": None}, "chore: drop it")

    assert kinds(scan(capsys, repo, name="a.json"), "adr-contradiction-candidate") == []
    assert kinds(scan(capsys, other, name="b.json"), "adr-contradiction-candidate") == []
