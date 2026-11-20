"""Tests for bootstrap_adr: rendering and the exclusive write (P16, P17).

Ports tests/adr-writer.test.ts and tests/adr-command.test.ts of align-cli (MIT, Copyright
(c) 2026 Align Tech Ltd, see LICENSE-align): the next number keeps the folder's width, the
ADR carries the title, the stated reason, the source text and a link and invents nothing,
writing never overwrites, and only the accepted decision is written. Each fix from the port
plan, section 3, has a case that fails on upstream's rule.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import adr_commits
import adr_locate
import adr_scan
import bootstrap_adr
import pytest
from adr_helpers import commit, git, new_repo, write
from adr_scan import ConfigError

WHY = "Because the team already runs it in production and a second system needs a second on-call."
ADR_122 = (
    "# ADR-122: Use Postgres\n\n## Status\n\nAccepted\n\n## Context\n\nWhy.\n\n"
    "## Decision\n\nDo it.\n\n## Consequences\n\nSome.\n"
)


def _cand(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "c-1234567",
        "kind": "commit",
        "title": "Replace eo-inference with the per-copy engine",
        "reason": "the per-copy engine resolves each copy once, so inference stops repeating work",
        "excerpt": (
            "Replace eo-inference with the per-copy engine\n\nThe old engine re-read every copy."
        ),
        "date": "2026-11-02",
        "source": {
            "sha": "1234567" + "0" * 33,
            "url": "https://github.com/objectionary/eo/commit/9d90b52",
            "pr_number": None,
            "pr_url": None,
        },
        "signals": [],
    }
    return {**base, **over}


def _scan_file(tmp_path: Path, repo: Path, *candidates: dict[str, Any]) -> str:
    path = tmp_path / f"scan-{len(list(tmp_path.glob('scan-*.json')))}.json"
    path.write_text(
        json.dumps({"repo": str(repo), "candidates": list(candidates)}), encoding="utf-8"
    )
    return str(path)


def _toolkit_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = new_repo(tmp_path / "r")
    folder = repo / ".project-toolkit" / "architecture"
    write(repo, ".project-toolkit/architecture/ADR-122-use-postgres.md", ADR_122)
    commit(repo, "Initial work")
    return repo, folder


def _text(result: dict[str, Any]) -> str:
    return Path(result["path"]).read_text(encoding="utf-8")


def test_the_first_draft_in_a_folder_whose_newest_is_adr_122_is_adr_123(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    scan = _scan_file(tmp_path, repo, _cand())
    result = bootstrap_adr.draft(scan, "c-1234567", str(folder), "Proposed")
    assert Path(result["path"]).name == "ADR-123-replace-eo-inference-with-the-per-copy-engine.md"
    assert (result["number"], result["status"], result["in_repo"]) == (123, "Proposed", True)
    text = _text(result)
    assert text.startswith("# ADR-123: Replace eo-inference with the per-copy engine\n")
    assert "## Status\n\nProposed\n" in text and "Accepted" not in text


def test_the_draft_carries_the_title_reason_source_link_and_invents_nothing(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    result = bootstrap_adr.draft(
        _scan_file(tmp_path, repo, _cand()), "c-1234567", str(folder), "Proposed"
    )
    text = _text(result)
    assert "Date: 2026-11-02" in text
    assert "The reason given at the time: the per-copy engine resolves each copy once" in text
    assert "> The old engine re-read every copy." in text
    assert "Decided in https://github.com/objectionary/eo/commit/9d90b52" in text
    assert "## Consequences\n\nNot recorded in the source.\n" in text
    assert "<!--" not in text and "Drafted by" not in text


def test_a_source_with_no_reason_says_so_and_a_missing_link_falls_back_to_the_sha(
    tmp_path: Path,
) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    sha = "ab" * 20
    cand = _cand(reason=None, excerpt=None, date=None, source={"sha": sha, "url": None})
    text = _text(
        bootstrap_adr.draft(_scan_file(tmp_path, repo, cand), "c-1234567", str(folder), "Proposed")
    )
    assert "The source states no reason." in text
    assert f"Decided in commit {sha}" in text
    assert "Date:" not in text and "From the source" not in text


def test_a_source_with_no_link_at_all_says_where_it_was_decided_was_not_recorded(
    tmp_path: Path,
) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    cand = _cand(source={"url": "http://insecure.example/x"})
    text = _text(
        bootstrap_adr.draft(_scan_file(tmp_path, repo, cand), "c-1234567", str(folder), "Proposed")
    )
    assert "Where it was decided was not recorded." in text


def test_a_pull_request_and_a_log_entry_link_back_to_their_source(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    pull = _cand(
        id="pr-9",
        kind="pr",
        source={"number": 9, "url": "https://github.com/o/r/pull/9", "sha": None},
    )
    entry = _cand(
        id="log-D17", kind="decision-log", source={"file": "DECISIONS.md", "entry_id": "D17"}
    )
    scan = _scan_file(tmp_path, repo, pull, entry)
    first = _text(bootstrap_adr.draft(scan, "pr-9", str(folder), "Proposed"))
    second = _text(bootstrap_adr.draft(scan, "log-D17", str(folder), "Proposed"))
    assert (
        "Decided in https://github.com/o/r/pull/9" in first
        and "From the source pull request:" in first
    )
    assert "Decided in DECISIONS.md (entry D17)" in second
    assert "From the source decision log entry:" in second


def test_two_accepted_ids_get_consecutive_numbers(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    one = _cand(id="c-1", title="Use Redis for sessions")
    two = _cand(id="c-2", title="Use Kafka for events")
    scan = _scan_file(tmp_path, repo, one, two)
    first = bootstrap_adr.draft(scan, "c-1", str(folder), "Proposed")
    second = bootstrap_adr.draft(scan, "c-2", str(folder), "Proposed")
    assert (first["number"], second["number"]) == (123, 124)
    assert Path(second["path"]).name == "ADR-124-use-kafka-for-events.md"
    assert _text(second).startswith("# ADR-124: Use Kafka for events\n")


def test_the_number_keeps_the_folders_width_and_h1_style(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0007-a.md", "# 7. A\n")
    write(repo, "docs/adr/0012-b.md", "# 12. B\n\n## Status\n\nok\n")
    commit(repo, "Initial work")
    result = bootstrap_adr.draft(
        _scan_file(tmp_path, repo, _cand()), "c-1234567", str(repo / "docs" / "adr"), "Proposed"
    )
    assert Path(result["path"]).name.startswith("0013-")
    text = _text(result)
    assert text.startswith("# 13. Replace eo-inference")
    # The newest ADR has only a Status heading. The source text still lands in the draft.
    assert "## Context\n\nThe reason given at the time:" in text
    assert "## Decision\n\nReplace eo-inference" in text


def test_an_outside_scratch_folder_starts_at_one_with_the_nygard_headings(tmp_path: Path) -> None:
    repo, _folder = _toolkit_repo(tmp_path)
    scratch = tmp_path / "scratch" / "adr"
    result = bootstrap_adr.draft(
        _scan_file(tmp_path, repo, _cand()), "c-1234567", str(scratch), "Proposed"
    )
    text = _text(result)
    assert Path(result["path"]).parent == scratch.resolve() and result["in_repo"] is False
    assert Path(result["path"]).name.startswith("0001-")
    assert text.startswith("# 1. Replace eo-inference")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == ["## Status", "## Context", "## Decision", "## Consequences"]


def test_headings_follow_the_newest_adr_and_unfilled_ones_say_so(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    madr = (
        "---\nstatus: accepted\n---\n\n# 0004. Use X\n\n## Context and Problem Statement\n\nc\n\n"
        "## Decision Drivers\n\nd\n\n## Considered Options\n\no\n\n## Decision Outcome\n\nx\n\n"
        "## Consequences\n\nq\n\n## Date\n\n2020-01-01\n"
    )
    write(repo, "docs/decisions/0004-use-x.md", madr)
    commit(repo, "Initial work")
    result = bootstrap_adr.draft(
        _scan_file(tmp_path, repo, _cand()),
        "c-1234567",
        str(repo / "docs" / "decisions"),
        "Proposed",
    )
    text = _text(result)
    sections = {
        part.split("\n", 1)[0]: part.split("\n", 1)[1].strip() for part in text.split("## ")[1:]
    }
    assert list(sections) == [
        "Context and Problem Statement", "Decision Drivers", "Considered Options",
        "Decision Outcome", "Consequences", "Date",
    ]  # fmt: skip
    assert (
        sections["Decision Drivers"] == sections["Considered Options"] == bootstrap_adr.NOT_RECORDED
    )
    assert sections["Consequences"] == bootstrap_adr.NOT_RECORDED
    assert sections["Date"] == "2026-11-02"
    assert sections["Decision Outcome"].startswith("Replace eo-inference with the per-copy engine")
    assert "The reason given at the time:" in sections["Context and Problem Statement"]
    assert "\nDate:" not in text and "\nStatus:" in text  # no Date line; Status has no heading


def test_a_non_ascii_title_falls_back_to_decision_and_the_sha(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    cand = _cand(title="決定を記録する")
    result = bootstrap_adr.draft(
        _scan_file(tmp_path, repo, cand), "c-1234567", str(folder), "Proposed"
    )
    assert Path(result["path"]).name == "ADR-123-decision-1234567.md"


def test_a_non_ascii_title_without_a_sha_falls_back_to_the_id(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    cand = _cand(id="log-D17", kind="decision-log", title="決定", source={"file": "D.md"})
    result = bootstrap_adr.draft(
        _scan_file(tmp_path, repo, cand), "log-D17", str(folder), "Proposed"
    )
    assert Path(result["path"]).name == "ADR-123-decision-log-d17.md"


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("Café policy: use  Shéll!", "cafe-policy-use-shell"),
        ("  --Use X--  ", "use-x"),
        ("a" * 80, "a" * 60),
        ("word " * 20, ("word-" * 12).rstrip("-")),
    ],
)
def test_the_slug_is_ascii_lowercase_hyphenated_and_cut_at_sixty(title: str, slug: str) -> None:
    assert adr_commits.slugify(title) == slug


def test_draft_never_overwrites_a_file_at_the_target(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    mine = write(tmp_path, "mine.txt", "mine")
    target = folder / "ADR-123-replace-eo-inference-with-the-per-copy-engine.md"
    try:
        target.symlink_to(mine)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(bootstrap_adr.ExistsError) as caught:
        bootstrap_adr.draft(
            _scan_file(tmp_path, repo, _cand()), "c-1234567", str(folder), "Proposed"
        )
    assert caught.value.path == target and mine.read_text(encoding="utf-8") == "mine"
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        ["ADR-122-use-postgres.md", target.name]
    )


def test_draft_does_not_retry_with_another_number_when_the_target_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    stale = adr_locate.folder_style(folder)
    write(repo, ".project-toolkit/architecture/ADR-123-use-redis-for-sessions.md", "mine\n")
    monkeypatch.setattr(bootstrap_adr, "folder_style", lambda _dir: stale)
    scan = _scan_file(tmp_path, repo, _cand(title="Use Redis for sessions"))
    with pytest.raises(bootstrap_adr.ExistsError):
        bootstrap_adr.draft(scan, "c-1234567", str(folder), "Proposed")
    assert (folder / "ADR-123-use-redis-for-sessions.md").read_text(encoding="utf-8") == "mine\n"
    assert not list(folder.glob("ADR-124-*"))


def test_two_adrs_with_one_number_are_reported_as_a_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    real = adr_locate.folder_style

    def racing(directory: Path) -> Any:
        style = real(directory)
        (directory / "ADR-123-written-by-someone-else.md").write_text("theirs\n", encoding="utf-8")
        return style

    monkeypatch.setattr(bootstrap_adr, "folder_style", racing)
    with pytest.raises(bootstrap_adr.ExistsError) as caught:
        bootstrap_adr.draft(
            _scan_file(tmp_path, repo, _cand()), "c-1234567", str(folder), "Proposed"
        )
    assert caught.value.others == ["ADR-123-written-by-someone-else.md"]
    assert (folder / "ADR-123-written-by-someone-else.md").read_text(encoding="utf-8") == "theirs\n"


def test_draft_into_a_git_ignored_path_is_refused(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    write(repo, ".gitignore", ".project-toolkit/architecture/ADR-123-*\n")
    with pytest.raises(ConfigError, match="ignored by git"):
        bootstrap_adr.draft(
            _scan_file(tmp_path, repo, _cand()), "c-1234567", str(folder), "Proposed"
        )
    assert not list(folder.glob("ADR-123-*"))


@pytest.mark.parametrize("rel", ["docs/other", ".", ".git", "src"])
def test_a_folder_in_the_repo_that_is_not_an_adr_folder_is_refused(
    tmp_path: Path, rel: str
) -> None:
    repo, _folder = _toolkit_repo(tmp_path)
    (repo / "docs" / "other").mkdir(parents=True)
    (repo / "src").mkdir()
    before = git(repo, "status", "--porcelain", "-uall")
    with pytest.raises(ConfigError, match="not an ADR folder"):
        bootstrap_adr.draft(
            _scan_file(tmp_path, repo, _cand()), "c-1234567", str(repo / rel), "Proposed"
        )
    assert git(repo, "status", "--porcelain", "-uall") == before


@pytest.mark.parametrize("status", ["", "Proposed\n## Evil", "x" * 41, "1st", "Accepted <b>"])
def test_a_status_that_is_not_a_short_plain_phrase_is_refused(tmp_path: Path, status: str) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    with pytest.raises(ConfigError, match="--status"):
        bootstrap_adr.draft(_scan_file(tmp_path, repo, _cand()), "c-1234567", str(folder), status)


def test_status_can_be_set_to_another_word(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    result = bootstrap_adr.draft(
        _scan_file(tmp_path, repo, _cand()), "c-1234567", str(folder), "Draft"
    )
    assert "## Status\n\nDraft\n" in _text(result)


def test_text_from_the_scan_file_is_stripped_of_control_bytes(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    cand = _cand(
        title="Use X\x00 now",
        reason="because\x1b[31m red",
        excerpt="a\x00b\r\nc",
        date="2026-02-30",
    )
    text = _text(
        bootstrap_adr.draft(_scan_file(tmp_path, repo, cand), "c-1234567", str(folder), "Proposed")
    )
    assert "\x00" not in text and "\x1b" not in text and "\r" not in text
    assert "Date:" not in text  # 2026-02-30 is not a real day


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        json.dumps({"repo": "x"}),
        json.dumps({"candidates": []}),
        json.dumps({"repo": "x", "candidates": "no"}),
    ],
)
def test_a_malformed_scan_file_is_refused(tmp_path: Path, body: str) -> None:
    path = write(tmp_path, "bad.json", body)
    with pytest.raises(ConfigError):
        bootstrap_adr.draft(str(path), "c-1", str(tmp_path / "out"), "Proposed")


def test_a_missing_scan_file_an_unknown_id_and_a_bad_candidate_are_refused(tmp_path: Path) -> None:
    repo, folder = _toolkit_repo(tmp_path)
    with pytest.raises(ConfigError, match="cannot read"):
        bootstrap_adr.draft(str(tmp_path / "none.json"), "c-1", str(folder), "Proposed")
    scan = _scan_file(
        tmp_path, repo, _cand(), _cand(id="c-bad", kind="mystery"), _cand(id="c-t", title=3)
    )
    with pytest.raises(ConfigError, match="no candidate"):
        bootstrap_adr.draft(scan, "c-other", str(folder), "Proposed")
    with pytest.raises(ConfigError, match="unknown kind"):
        bootstrap_adr.draft(scan, "c-bad", str(folder), "Proposed")
    with pytest.raises(ConfigError, match="title"):
        bootstrap_adr.draft(scan, "c-t", str(folder), "Proposed")


def test_a_scan_whose_repository_is_gone_is_refused_before_any_write(tmp_path: Path) -> None:
    repo, _folder = _toolkit_repo(tmp_path)
    scan = _scan_file(tmp_path, repo, _cand())
    ghost = json.loads(Path(scan).read_text(encoding="utf-8"))
    ghost["repo"] = str(tmp_path / "gone")
    Path(scan).write_text(json.dumps(ghost), encoding="utf-8")
    out = tmp_path / "scratch"
    with pytest.raises(ConfigError, match="not a directory"):
        bootstrap_adr.draft(scan, "c-1234567", str(out), "Proposed")
    assert not out.exists()


def test_an_out_path_that_is_a_file_is_refused(tmp_path: Path) -> None:
    repo, _folder = _toolkit_repo(tmp_path)
    blocker = write(tmp_path, "blocker", "x")
    with pytest.raises(ConfigError, match="not a directory"):
        bootstrap_adr.draft(
            _scan_file(tmp_path, repo, _cand()), "c-1234567", str(blocker), "Proposed"
        )


def test_a_rerun_after_drafting_proposes_none_of_the_drafted_decisions(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n\n## Status\n\nAccepted\n")
    squash = commit(repo, f"Adopt Postgres instead of MySQL (#12)\n\n{WHY}\n")
    plain = commit(repo, f"Adopt Redis instead of Memcached\n\n{WHY}\n")
    write(repo, "DECISIONS.md", f"## D17 - Use pnpm everywhere\n\nWe use pnpm because {WHY}\n")
    git(repo, "remote", "add", "origin", "https://github.com/o/r.git")
    prs = [
        {
            "number": 12, "title": "Adopt Postgres instead of MySQL", "body": WHY,
            "url": "https://github.com/o/r/pull/12", "merged_at": "2026-03-04T10:00:00Z",
            "author": {"login": "ada"}, "merge_commit_sha": squash,
        }
    ]  # fmt: skip
    first = adr_scan.scan(repo, "HEAD", 300, None, prs)
    assert sorted(item["id"] for item in first["candidates"]) == sorted(
        ["pr-12", f"c-{plain[:7]}", "log-D17"]
    )
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps(first), encoding="utf-8")
    folder = repo / "docs" / "adr"
    numbers = [
        bootstrap_adr.draft(str(scan), item["id"], str(folder), "Proposed")["number"]
        for item in first["candidates"]
    ]
    assert numbers == [2, 3, 4]
    second = adr_scan.scan(repo, "HEAD", 300, None, prs)
    assert second["candidates"] == []
    assert second["dropped"]["already_documented"] == 3 and second["dropped"]["covered_by_pr"] == 1


def test_a_scan_lists_two_and_draft_writes_only_the_accepted_one(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-first.md", "# 1. First\n")
    commit(repo, "Encode TRUE as FF- instead of 01-\n\nBecause FF- is what the runtime emits.\n")
    commit(repo, f"Adopt Redis instead of Memcached\n\n{WHY}\n")
    payload = adr_scan.scan(repo, "HEAD", 300, None, None)
    assert len(payload["candidates"]) == 2
    assert sorted(p.name for p in (repo / "docs" / "adr").iterdir()) == ["0001-first.md"]
    scan = tmp_path / "scan.json"
    scan.write_text(json.dumps(payload), encoding="utf-8")
    accepted = payload["candidates"][0]
    bootstrap_adr.draft(str(scan), accepted["id"], str(repo / "docs" / "adr"), "Proposed")
    assert len(list((repo / "docs" / "adr").iterdir())) == 2


def test_only_the_first_heading_of_a_kind_is_filled(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-a.md", "# 1. A\n\n## Context\n\nc\n\n## Background\n\nb\n")
    commit(repo, "Initial work")
    scan = _scan_file(tmp_path, repo, _cand())
    text = _text(bootstrap_adr.draft(scan, "c-1234567", str(repo / "docs" / "adr"), "Proposed"))
    assert text.count("The reason given at the time:") == 1
    assert "## Background\n\nNot recorded in the source." in text


def test_section_matching_uses_whole_words(tmp_path: Path) -> None:
    repo = new_repo(tmp_path / "r")
    write(
        repo,
        "docs/adr/0001-a.md",
        "# 1. A\n\n## Context and Constraints\n\nc\n\n## Updates\n\nu\n\n## Candidates\n\nk\n"
        "\n## Decision\n\nd\n",
    )
    commit(repo, "Initial work")
    scan = _scan_file(tmp_path, repo, _cand())
    text = _text(bootstrap_adr.draft(scan, "c-1234567", str(repo / "docs" / "adr"), "Proposed"))
    assert "## Context and Constraints\n\nThe reason given at the time:" in text
    assert "## Updates\n\nNot recorded in the source." in text
    assert "## Candidates\n\nNot recorded in the source." in text
    assert "## Decision\n\nReplace eo-inference" in text
    assert "Date: 2026-11-02" in text and "2026-11-02" not in text.split("## Updates")[1]


def test_a_draft_into_another_work_tree_of_the_repository_is_gated_on_that_tree(
    tmp_path: Path,
) -> None:
    repo = new_repo(tmp_path / "r")
    write(repo, "docs/adr/0001-a.md", "# 1. A\n\n## Status\n\nok\n")
    commit(repo, "Initial work")
    side = tmp_path / "side"
    git(repo, "worktree", "add", "-q", str(side), "-b", "side")
    scan = _scan_file(tmp_path, repo, _cand())
    with pytest.raises(ConfigError, match="not an ADR folder"):
        bootstrap_adr.draft(scan, "c-1234567", str(side / "docs"), "Proposed")
    write(side, ".gitignore", "docs/adr/0002-*\n")
    with pytest.raises(ConfigError, match="ignored by git"):
        bootstrap_adr.draft(scan, "c-1234567", str(side / "docs" / "adr"), "Proposed")
    (side / ".gitignore").unlink()
    result = bootstrap_adr.draft(scan, "c-1234567", str(side / "docs" / "adr"), "Proposed")
    assert result["in_repo"] is True
    assert Path(result["path"]).resolve().is_relative_to(side.resolve())
    assert sorted(p.name for p in (repo / "docs" / "adr").iterdir()) == ["0001-a.md"]


def test_a_scratch_folder_inside_an_unrelated_repository_is_not_gated(tmp_path: Path) -> None:
    repo, _folder = _toolkit_repo(tmp_path)
    other = new_repo(tmp_path / "other")
    result = bootstrap_adr.draft(
        _scan_file(tmp_path, repo, _cand()), "c-1234567", str(other / "scratch"), "Proposed"
    )
    assert (
        result["in_repo"] is False and Path(result["path"]).parent == (other / "scratch").resolve()
    )
