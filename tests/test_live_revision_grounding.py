"""Tests for live_revision_grounding.py (issue #5634).

Every scenario runs against real git repositories: a bare "remote", a local
clone under analysis, and a second clone that advances the remote. Mocking git
would test the mock, not the SHA comparison.

Covers:
- Status: equal, behind, ahead, diverged
- Fetch/API failure: unreachable remote -> exit 3, unverified record
- Default branch change during analysis (--since)
- Citation revalidation: unchanged, changed, line range, absent path
- --require-current gate
- Configuration errors: bad --cite, not a git repo, unknown branch
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "validation" / "live_revision_grounding.py"
)


def _import_script():
    spec = importlib.util.spec_from_file_location("live_revision_grounding_test", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["live_revision_grounding_test"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script()
main = _mod.main

_IDENTITY = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
_BODY = "\n".join(f"line {n}" for n in range(1, 11)) + "\n"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *_IDENTITY, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, name: str, text: str) -> str:
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"edit {name}")
    return _git(repo, "rev-parse", "HEAD")


def make_repos(tmp_path: Path) -> dict[str, Path]:
    """A bare remote, the clone under analysis, and a second clone."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    local = tmp_path / "local"
    local.mkdir()
    _git(local, "init", "-q", "-b", "main")
    _git(local, "remote", "add", "origin", str(remote))
    _commit(local, "a.txt", _BODY)
    _commit(local, "b.txt", "stable\n")
    _git(local, "push", "-q", "origin", "main")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
    return {"remote": remote, "local": local, "other": other}


@pytest.fixture
def repos(tmp_path: Path) -> dict[str, Path]:
    return make_repos(tmp_path)


def _advance_remote(repos: dict[str, Path], name: str = "a.txt", text: str | None = None) -> str:
    """Push a new commit to the remote from the second clone."""
    other = repos["other"]
    _git(other, "pull", "-q", "origin", "main")
    body = text if text is not None else _BODY.replace("line 8", "line 8 changed")
    sha = _commit(other, name, body)
    _git(other, "push", "-q", "origin", "main")
    return sha


def _run(repos: dict[str, Path], capsys, *extra: str) -> tuple[int, dict]:
    code = main(["--repo", str(repos["local"]), *extra])
    out = capsys.readouterr().out
    return code, json.loads(out)


class TestStatus:
    def test_equal_is_current(self, repos, capsys):
        code, rec = _run(repos, capsys)
        head = _git(repos["local"], "rev-parse", "HEAD")
        assert code == 0
        assert rec["status"] == "equal"
        assert rec["finding_status"] == "CURRENT"
        assert rec["live_sha"] == rec["local_head"] == rec["grounded_sha"] == head
        assert rec["branch"] == "main"
        assert rec["live_changed"] is None

    def test_record_carries_retrieval_time(self, repos, capsys):
        _code, rec = _run(repos, capsys)
        assert rec["retrieved_at"].endswith("Z")
        assert len(rec["retrieved_at"]) == 20

    def test_behind_without_citation_is_unverified(self, repos, capsys):
        new_live = _advance_remote(repos)
        code, rec = _run(repos, capsys)
        assert code == 0
        assert rec["status"] == "behind"
        assert rec["live_sha"] == new_live
        assert rec["finding_status"] == "UNVERIFIED"
        assert "no --cite" in rec["reason"]

    def test_behind_does_not_move_local_refs(self, repos, capsys):
        _advance_remote(repos)
        before = _git(repos["local"], "rev-parse", "HEAD", "origin/main")
        _run(repos, capsys)
        assert _git(repos["local"], "rev-parse", "HEAD", "origin/main") == before

    def test_ahead_is_not_current_without_revalidation(self, repos, capsys):
        _commit(repos["local"], "a.txt", _BODY + "extra\n")
        code, rec = _run(repos, capsys)
        assert code == 0
        assert rec["status"] == "ahead"
        assert rec["finding_status"] == "UNVERIFIED"

    def test_diverged(self, repos, capsys):
        _advance_remote(repos)
        _commit(repos["local"], "c.txt", "local only\n")
        code, rec = _run(repos, capsys)
        assert code == 0
        assert rec["status"] == "diverged"
        assert rec["finding_status"] == "UNVERIFIED"

    def test_named_branch(self, repos, capsys):
        _git(repos["local"], "push", "-q", "origin", "main:release")
        code, rec = _run(repos, capsys, "--branch", "release")
        assert code == 0
        assert rec["branch"] == "release"
        assert rec["status"] == "equal"


class TestCitationRevalidation:
    def test_unchanged_file_revalidates_current(self, repos, capsys):
        _advance_remote(repos)
        code, rec = _run(repos, capsys, "--cite", "b.txt")
        assert code == 0
        assert rec["status"] == "behind"
        assert rec["finding_status"] == "CURRENT"
        assert rec["citations"] == [
            {
                "citation": "b.txt",
                "revision": rec["local_head"],
                "status": "CURRENT",
                "detail": "cited content identical at both revisions",
            }
        ]

    def test_changed_file_is_stale(self, repos, capsys):
        _advance_remote(repos)
        code, rec = _run(repos, capsys, "--cite", "a.txt")
        assert code == 0
        assert rec["finding_status"] == "STALE"
        assert rec["citations"][0]["status"] == "STALE"

    def test_changed_line_inside_range_is_stale(self, repos, capsys):
        _advance_remote(repos)
        _code, rec = _run(repos, capsys, "--cite", "a.txt:7-9")
        assert rec["finding_status"] == "STALE"
        assert rec["citations"][0]["citation"] == "a.txt:7-9"

    def test_changed_line_outside_range_stays_current(self, repos, capsys):
        _advance_remote(repos)
        _code, rec = _run(repos, capsys, "--cite", "a.txt:1-3")
        assert rec["finding_status"] == "CURRENT"

    def test_single_line_citation(self, repos, capsys):
        _advance_remote(repos)
        _code, rec = _run(repos, capsys, "--cite", "a.txt:8")
        assert rec["finding_status"] == "STALE"
        assert rec["citations"][0]["citation"] == "a.txt:8"

    def test_one_stale_citation_outweighs_current_ones(self, repos, capsys):
        _advance_remote(repos)
        _code, rec = _run(repos, capsys, "--cite", "b.txt", "--cite", "a.txt:8")
        assert rec["finding_status"] == "STALE"
        assert [row["status"] for row in rec["citations"]] == ["CURRENT", "STALE"]

    def test_file_deleted_on_live_is_stale(self, repos, capsys):
        other = repos["other"]
        _git(other, "rm", "-q", "b.txt")
        _git(other, "commit", "-q", "-m", "drop b")
        _git(other, "push", "-q", "origin", "main")
        _code, rec = _run(repos, capsys, "--cite", "b.txt")
        assert rec["finding_status"] == "STALE"
        assert "absent at live" in rec["citations"][0]["detail"]

    def test_path_absent_everywhere_is_unverified(self, repos, capsys):
        _advance_remote(repos)
        _code, rec = _run(repos, capsys, "--cite", "missing.txt")
        assert rec["finding_status"] == "UNVERIFIED"

    def test_equal_revisions_skip_revalidation(self, repos, capsys):
        _code, rec = _run(repos, capsys, "--cite", "a.txt:8")
        assert rec["finding_status"] == "CURRENT"
        assert rec["citations"] == []


class TestDefaultBranchChangeDuringAnalysis:
    def test_since_equal_to_live_is_unchanged(self, repos, capsys):
        _code, first = _run(repos, capsys)
        code, second = _run(repos, capsys, "--since", first["live_sha"])
        assert code == 0
        assert second["live_changed"] is False
        assert second["finding_status"] == "CURRENT"

    def test_live_moved_after_local_pull_is_not_current(self, repos, capsys):
        _code, first = _run(repos, capsys)
        _advance_remote(repos)
        _git(repos["local"], "pull", "-q", "origin", "main")
        code, second = _run(repos, capsys, "--since", first["live_sha"])
        assert code == 0
        assert second["status"] == "equal"
        assert second["live_changed"] is True
        assert second["grounded_sha"] == first["live_sha"]
        assert second["finding_status"] == "UNVERIFIED"

    def test_live_moved_marks_changed_citation_stale(self, repos, capsys):
        _code, first = _run(repos, capsys)
        _advance_remote(repos)
        _git(repos["local"], "pull", "-q", "origin", "main")
        _code, second = _run(repos, capsys, "--since", first["live_sha"], "--cite", "a.txt:8")
        assert second["finding_status"] == "STALE"

    def test_live_moved_keeps_unchanged_citation_current(self, repos, capsys):
        _code, first = _run(repos, capsys)
        _advance_remote(repos)
        _code, second = _run(repos, capsys, "--since", first["live_sha"], "--cite", "b.txt")
        assert second["live_changed"] is True
        assert second["finding_status"] == "CURRENT"


class TestRequireCurrent:
    def test_current_exits_zero(self, repos, capsys):
        code, _rec = _run(repos, capsys, "--require-current")
        assert code == 0

    def test_stale_exits_one(self, repos, capsys):
        _advance_remote(repos)
        code, rec = _run(repos, capsys, "--require-current", "--cite", "a.txt")
        assert code == 1
        assert rec["finding_status"] == "STALE"

    def test_stale_reports_reason_on_stderr(self, repos, capsys):
        _advance_remote(repos)
        main(["--repo", str(repos["local"]), "--require-current", "--cite", "a.txt"])
        assert "finding_status is STALE" in capsys.readouterr().err

    def test_unverified_exits_one(self, repos, capsys):
        _advance_remote(repos)
        code, rec = _run(repos, capsys, "--require-current")
        assert code == 1
        assert rec["finding_status"] == "UNVERIFIED"

    def test_revalidated_current_exits_zero(self, repos, capsys):
        _advance_remote(repos)
        code, rec = _run(repos, capsys, "--require-current", "--cite", "b.txt")
        assert code == 0
        assert rec["finding_status"] == "CURRENT"


class TestFailures:
    def test_unreachable_remote_exits_three_with_unverified_record(self, repos, tmp_path, capsys):
        _git(repos["local"], "remote", "set-url", "origin", str(tmp_path / "gone.git"))
        code, rec = _run(repos, capsys)
        assert code == 3
        assert rec["status"] == "unverified"
        assert rec["finding_status"] == "UNVERIFIED"
        assert "Remote read failed" in rec["reason"]
        assert rec["live_sha"] is None

    def test_unreachable_remote_never_reports_current(self, repos, tmp_path, capsys):
        _git(repos["local"], "remote", "set-url", "origin", str(tmp_path / "gone.git"))
        code, rec = _run(repos, capsys, "--require-current")
        assert code == 3
        assert rec["finding_status"] != "CURRENT"

    def test_auth_failure_maps_to_exit_four(self):
        error = _mod._remote_failure("fatal: Authentication failed for 'https://x'")
        assert error.exit_code == 4

    def test_other_remote_failure_maps_to_exit_three(self):
        error = _mod._remote_failure("fatal: unable to access: timeout")
        assert error.exit_code == 3

    def test_empty_stderr_still_maps_to_exit_three(self):
        assert _mod._remote_failure("").exit_code == 3

    def test_unknown_branch_exits_two(self, repos, capsys):
        code, rec = _run(repos, capsys, "--branch", "nope")
        assert code == 2
        assert rec["finding_status"] == "UNVERIFIED"

    def test_not_a_git_repo_exits_two(self, tmp_path, capsys):
        plain = tmp_path / "plain"
        plain.mkdir()
        code = main(["--repo", str(plain)])
        rec = json.loads(capsys.readouterr().out)
        assert code == 2
        assert rec["finding_status"] == "UNVERIFIED"

    @pytest.mark.parametrize("bad", ["", ":5", "a.txt:0", "a.txt:9-3"])
    def test_invalid_cite_exits_two(self, repos, capsys, bad):
        code, _rec = _run(repos, capsys, "--cite", bad)
        assert code == 2

    def test_live_commit_fetch_failure_exits_three(self, repos, capsys, monkeypatch):
        _advance_remote(repos)

        def refuse(repo, remote, sha):
            raise _mod.GroundingError("Remote read failed: boom", 3)

        monkeypatch.setattr(_mod, "ensure_commit", refuse)
        code, rec = _run(repos, capsys)
        assert code == 3
        assert rec["status"] == "unverified"
        assert rec["live_sha"] is not None

    def test_named_branch_remote_failure_exits_three(self, repos, tmp_path, capsys):
        _git(repos["local"], "remote", "set-url", "origin", str(tmp_path / "gone.git"))
        code, rec = _run(repos, capsys, "--branch", "main")
        assert code == 3
        assert rec["finding_status"] == "UNVERIFIED"

    def test_ensure_commit_fetch_failure_exits_three(self, repos, capsys):
        missing = "0" * 40
        with pytest.raises(_mod.GroundingError) as raised:
            _mod.ensure_commit(repos["local"], "origin", missing)
        assert raised.value.exit_code == 3

    def test_script_runs_as_a_command(self, repos):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--repo", str(repos["local"])],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert result.returncode == 0
        assert json.loads(result.stdout)["finding_status"] == "CURRENT"


class TestParsing:
    def test_path_only(self):
        assert _mod.parse_citation("a/b.py") == _mod.Citation("a/b.py", None, None)

    def test_single_line(self):
        cite = _mod.parse_citation("a/b:12")
        assert (cite.start, cite.end, cite.label) == (12, 12, "a/b:12")

    def test_range(self):
        cite = _mod.parse_citation("a/b:12-20")
        assert (cite.start, cite.end, cite.label) == (12, 20, "a/b:12-20")

    def test_colon_in_path_without_digits_stays_in_path(self):
        assert _mod.parse_citation("dir/a:b.md").path == "dir/a:b.md"

    def test_ls_remote_parser_handles_missing_symref(self):
        assert _mod._parse_ls_remote("abc\tHEAD\n") == (None, "abc")

    def test_ls_remote_parser_reads_symref_and_sha(self):
        out = "ref: refs/heads/trunk\tHEAD\n" + "f" * 40 + "\tHEAD\n"
        assert _mod._parse_ls_remote(out) == ("trunk", "f" * 40)

    def test_ls_remote_parser_ignores_other_refs(self):
        assert _mod._parse_ls_remote("abc\trefs/heads/x\n") == (None, None)

    def test_empty_remote_output_exits_three(self, repos, capsys, monkeypatch):
        def fake_git(repo, args):
            if args[0] == "rev-parse":
                return 0, "a" * 40 + "\n", ""
            return 0, "", ""

        monkeypatch.setattr(_mod, "_git", fake_git)
        code = main(["--repo", str(repos["local"])])
        rec = json.loads(capsys.readouterr().out)
        assert code == 3
        assert "no default branch" in rec["reason"]
