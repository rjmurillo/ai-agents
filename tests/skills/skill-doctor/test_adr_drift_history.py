"""adr_drift.py scan: git-history findings and truncation."""

from __future__ import annotations

from pathlib import Path

from adr_drift_helpers import adr_path, adr_text, commit, git, kinds, scan, seeded_repo


def _repo(tmp_path: Path, adrs: dict[str, str] | None = None) -> Path:
    return seeded_repo(tmp_path / "repo", adrs)


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
    assert (found[0]["severity"], found[0]["confidence"]) == ("low", "heuristic")


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


def test_deleting_a_file_under_a_cited_folder_is_not_a_candidate(tmp_path, capsys):
    text = adr_text(1, body="Modules live in `src/old/`.")
    repo = _repo(tmp_path, {adr_path(1): text, "src/old/module.py": "x", "src/old/keep.py": "x"})
    commit(repo, {"src/old/module.py": None}, "refactor: remove one module")

    assert kinds(scan(capsys, repo), "adr-contradiction-candidate") == []
