"""Resume check for a per-issue handoff (issue #5766).

Every test drives a real temporary git repository. No network is used: the
origin remote is a URL string that is never fetched.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_handoff_resume as checker

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / ".agents" / "templates" / "HANDOFF.md"
REMOTE_URL = "https://github.com/rjmurillo/ai-agents.git"
BRANCH = "feat/login-redirect"
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=ENV,
    )
    return result.stdout.strip()


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", name)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    root.mkdir()
    _git(root, "init", "-q", "-b", BRANCH)
    _git(root, "remote", "add", "origin", REMOTE_URL)
    _commit(root, "first.txt")
    return root.resolve()


def _record(repo: Path, **overrides: str | None) -> dict[str, str | None]:
    values: dict[str, str | None] = {
        "Remote": "rjmurillo/ai-agents",
        "Branch": BRANCH,
        "Worktree": str(repo),
        "Head SHA": _git(repo, "rev-parse", "HEAD"),
        "Timestamp": "2026-09-30T14:02Z",
        "Objective": "expired sessions redirect to /login",
        "Risk tier": "shared-repository",
        "Acceptance": "an expired cookie gets a 302 with Location /login",
        "Phase": "implementing",
        "Next action": "run qa on the patch",
        "Validation run": "unit tests pass",
    }
    values.update(overrides)
    return values


DECISION = (
    "- **Patch the session middleware**: smallest change\n"
    "  - Provenance: analyst finding, issue comment 3\n"
)


def _write(path: Path, record: dict[str, str | None], decisions: str = DECISION) -> Path:
    lines = [f"- **{k}**: {v}" for k, v in record.items() if v is not None]
    body = "\n".join(lines)
    text = f"# Handoff\n\n## State Record\n\n{body}\n\n## Decisions Made\n\n{decisions}\n"
    path.write_text(text, encoding="utf-8")
    return path


def _run(handoff: Path, repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = checker.main([str(handoff), "--repo", str(repo)])
    return code, capsys.readouterr().out


def test_matching_record_resumes(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo))

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_OK
    assert "[RESUME]" in out


def test_abbreviated_sha_and_ssh_remote_match(repo: Path, tmp_path: Path, capsys) -> None:
    _git(repo, "remote", "set-url", "origin", "git@github.com:rjmurillo/ai-agents.git")
    sha = _git(repo, "rev-parse", "--short=7", "HEAD")
    handoff = _write(tmp_path / "h.md", _record(repo, **{"Head SHA": sha}))

    code, _ = _run(handoff, repo, capsys)

    assert code == checker.EXIT_OK


def test_duplicate_resume_is_idempotent(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo))
    before = (_git(repo, "rev-parse", "HEAD"), _git(repo, "status", "--porcelain"))
    text_before = handoff.read_text(encoding="utf-8")

    first = _run(handoff, repo, capsys)
    second = _run(handoff, repo, capsys)

    assert first == second == (checker.EXIT_OK, first[1])
    assert (_git(repo, "rev-parse", "HEAD"), _git(repo, "status", "--porcelain")) == before
    assert handoff.read_text(encoding="utf-8") == text_before


def test_dirty_tree_is_not_a_mismatch(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo))
    (repo / "wip.txt").write_text("uncommitted", encoding="utf-8")

    code, _ = _run(handoff, repo, capsys)

    assert code == checker.EXIT_OK


def test_stale_sha_holds_and_reports_commits_ahead(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo))
    _commit(repo, "second.txt")

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "head SHA mismatch" in out
    assert "1 commit(s) ahead" in out


def test_rewritten_history_holds_without_ancestry_claim(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo, **{"Head SHA": "deadbee"}))

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "not an ancestor" in out


def test_wrong_branch_holds(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo))
    _git(repo, "checkout", "-q", "-b", "other")

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert f"branch mismatch: recorded {BRANCH}, live other" in out


def test_wrong_remote_holds(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo, Remote="someone/else"))

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "remote mismatch" in out


def test_wrong_worktree_holds(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo, Worktree=str(tmp_path / "elsewhere")))

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "worktree mismatch" in out


def test_missing_origin_remote_holds(repo: Path, tmp_path: Path, capsys) -> None:
    _git(repo, "remote", "remove", "origin")
    handoff = _write(tmp_path / "h.md", _record(repo))

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "no origin remote" in out


def test_missing_provenance_holds(repo: Path, tmp_path: Path, capsys) -> None:
    decisions = DECISION + "- **Skip the retry**: not needed\n  - Alternatives considered: none\n"
    handoff = _write(tmp_path / "h.md", _record(repo), decisions)

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "decision without provenance: **Skip the retry**" in out
    assert "Patch the session middleware" not in out


def test_empty_provenance_holds(repo: Path, tmp_path: Path, capsys) -> None:
    decisions = "- **Patch it**: why\n  - Provenance:   \n"
    handoff = _write(tmp_path / "h.md", _record(repo), decisions)

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "decision without provenance" in out


@pytest.mark.parametrize(
    "name",
    [
        "Remote",
        "Branch",
        "Worktree",
        "Head SHA",
        "Timestamp",
        "Objective",
        "Risk tier",
        "Acceptance",
        "Phase",
        "Next action",
        "Validation run",
    ],
)
def test_each_missing_required_field_holds(repo: Path, tmp_path: Path, capsys, name: str) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo, **{name: None}))

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert f"missing field: {name}" in out


@pytest.mark.parametrize("value", ["", "   ", "{risk tier}"])
def test_blank_and_placeholder_values_count_as_missing(
    repo: Path, tmp_path: Path, capsys, value: str
) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo, **{"Risk tier": value}))

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "missing field: Risk tier" in out


def test_unparseable_timestamp_holds(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo, Timestamp="yesterday"))

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "timestamp is not ISO 8601" in out


def test_non_hex_sha_holds(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo, **{"Head SHA": "HEAD"}))

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "not a hex SHA" in out


def test_short_sha_holds(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo, **{"Head SHA": "abc"}))

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD


@pytest.mark.parametrize(
    "content",
    [
        "",
        "just prose, no sections\n",
        "## State Record\n\nnot a bullet list\n",
        "## State Record\n\n- Remote: missing bold markers\n",
    ],
)
def test_malformed_file_holds_on_every_required_field(
    repo: Path, tmp_path: Path, capsys, content: str
) -> None:
    handoff = tmp_path / "h.md"
    handoff.write_text(content, encoding="utf-8")

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    for name in checker.REQUIRED_FIELDS:
        assert f"missing field: {name}" in out


def test_binary_file_holds(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = tmp_path / "h.md"
    handoff.write_bytes(b"\xff\xfe\x00bad")

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "not valid UTF-8" in out


def test_fields_inside_html_comments_are_ignored(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = tmp_path / "h.md"
    handoff.write_text(
        "## State Record\n\n<!--\n- **Remote**: rjmurillo/ai-agents\n-->\n", encoding="utf-8"
    )

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "missing field: Remote" in out


def test_missing_handoff_file_is_a_config_error(repo: Path, tmp_path: Path, capsys) -> None:
    code = checker.main([str(tmp_path / "nope.md"), "--repo", str(repo)])

    assert code == checker.EXIT_CONFIG
    assert "not found" in capsys.readouterr().err


def test_bad_repo_path_is_a_config_error(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo))

    code = checker.main([str(handoff), "--repo", str(tmp_path / "nope")])

    assert code == checker.EXIT_CONFIG


def test_directory_that_is_not_a_repository_is_an_external_failure(
    repo: Path, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo))
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))

    code = checker.main([str(handoff), "--repo", str(plain)])

    assert code == checker.EXIT_EXTERNAL
    assert "[ERROR]" in capsys.readouterr().err


def test_missing_git_binary_is_an_external_failure(
    repo: Path, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo))

    def boom(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(checker.subprocess, "run", boom)

    code = checker.main([str(handoff), "--repo", str(repo)])

    assert code == checker.EXIT_EXTERNAL
    assert "git unavailable" in capsys.readouterr().err


def test_shipped_template_parses_to_every_required_field() -> None:
    record = checker.parse_state_record(TEMPLATE.read_text(encoding="utf-8"))

    assert set(checker.REQUIRED_FIELDS) <= set(record)


def test_unfilled_template_holds_on_every_field(repo: Path, capsys) -> None:
    code, out = _run(TEMPLATE, repo, capsys)

    assert code == checker.EXIT_HOLD
    for name in checker.REQUIRED_FIELDS:
        assert f"missing field: {name}" in out


def test_plain_bullet_decision_without_provenance_holds(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo), "- Use the retry\n")

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "decision without provenance: Use the retry" in out


def test_none_decision_needs_no_provenance(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo), "- None\n")

    code, _ = _run(handoff, repo, capsys)

    assert code == checker.EXIT_OK


def test_conflicting_duplicate_field_holds(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo))
    stale = _git(repo, "rev-parse", "HEAD")[::-1]
    with handoff.open("a", encoding="utf-8") as stream:
        stream.write("\n")
    text = handoff.read_text(encoding="utf-8").replace(
        "## Decisions Made", f"- **Head SHA**: {stale}\n\n## Decisions Made"
    )
    handoff.write_text(text, encoding="utf-8")

    code, out = _run(handoff, repo, capsys)

    assert code == checker.EXIT_HOLD
    assert "missing field: Head SHA" in out


def test_remote_owner_comparison_ignores_case(repo: Path, tmp_path: Path, capsys) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo, Remote="RJMurillo/AI-Agents"))

    code, _ = _run(handoff, repo, capsys)

    assert code == checker.EXIT_OK


def test_unreadable_handoff_is_a_config_error(
    repo: Path, tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = _write(tmp_path / "h.md", _record(repo))

    def deny(*_a, **_k):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", deny)

    code = checker.main([str(handoff), "--repo", str(repo)])

    assert code == checker.EXIT_CONFIG
    assert "cannot read handoff" in capsys.readouterr().err
