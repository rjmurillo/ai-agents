"""Tests for the commit-range files-changed tier (issue #4416).

The extractor derives ``metrics.files_changed`` from three sources in order:
the staged diff, then the commit range the log names, then work-log prose. The
middle tier is the one this module covers. Without it, any run where nothing is
staged fell straight through to prose, and ``_FILES_RE`` matches the first
"N files" phrase anywhere in the log, including a linter's own summary line.
Nothing is staged on a ``--preserve`` re-extraction, a backfill, or any
post-commit invocation, so the fallback was not a rare path.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import extract_session_episode as ese

_SHA_A = "a" * 40
_SHA_B = "b" * 40


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=""
    )


class TestRangeFilesChanged:
    def test_counts_name_only_lines(self) -> None:
        names = "a.py\nb.md\nc.txt\n"
        with patch.object(ese.subprocess, "run", return_value=_completed(names)):
            assert ese._range_files_changed(_SHA_A, _SHA_B) == 3

    def test_zero_when_range_is_empty(self) -> None:
        with patch.object(ese.subprocess, "run", return_value=_completed("")):
            assert ese._range_files_changed(_SHA_A, _SHA_B) == 0

    def test_zero_on_nonzero_returncode(self) -> None:
        with patch.object(ese.subprocess, "run", return_value=_completed("x\n", returncode=128)):
            assert ese._range_files_changed(_SHA_A, _SHA_B) == 0

    def test_zero_when_git_missing(self) -> None:
        with patch.object(ese.subprocess, "run", side_effect=OSError):
            assert ese._range_files_changed(_SHA_A, _SHA_B) == 0

    def test_zero_on_timeout(self) -> None:
        with patch.object(
            ese.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)
        ):
            assert ese._range_files_changed(_SHA_A, _SHA_B) == 0

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            ("", _SHA_B),
            (_SHA_A, ""),
            ("zzzzzzz", _SHA_B),
            (_SHA_A, "not-a-sha"),
            ("--output=/etc/passwd", _SHA_B),
            (_SHA_A, "-1"),
            ("abc", _SHA_B),
        ],
    )
    def test_malformed_sha_never_reaches_git(self, start: str, end: str) -> None:
        """A value that is not a SHA must be refused before it becomes argv.

        Both fields come out of a JSON file, so a value like ``--output=...``
        would otherwise be handed to git as a flag rather than a revision.
        """
        with patch.object(ese.subprocess, "run") as run:
            assert ese._range_files_changed(start, end) == 0
        run.assert_not_called()

    def test_zero_when_start_equals_end(self) -> None:
        """A log whose base is also its tip names an empty range. Asking git is
        wasted work, and the answer would be 0 regardless (issue #4415)."""
        with patch.object(ese.subprocess, "run") as run:
            assert ese._range_files_changed(_SHA_A, _SHA_A) == 0
        run.assert_not_called()

    def test_equality_is_case_insensitive(self) -> None:
        with patch.object(ese.subprocess, "run") as run:
            assert ese._range_files_changed(_SHA_A.upper(), _SHA_A) == 0
        run.assert_not_called()

    def test_passes_cwd_via_git_c(self) -> None:
        with patch.object(ese.subprocess, "run", return_value=_completed("")) as run:
            ese._range_files_changed(_SHA_A, _SHA_B, "/some/where")
        argv = run.call_args[0][0]
        assert argv[:3] == ["git", "-C", "/some/where"]
        assert f"{_SHA_A}..{_SHA_B}" in argv

    def test_runs_git_with_clean_env_and_c_locale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Inherited git env vars would point the command at another repo, and
        a localized git would break line counting on some locales.

        The vars are set here first. Asserting their absence without setting
        them measures the ambient environment rather than the scrub: they are
        normally unset, so the assertion holds whether or not the code runs.
        """
        for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
            monkeypatch.setenv(var, "/elsewhere")
        monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
        with patch.object(ese.subprocess, "run", return_value=_completed("")) as run:
            ese._range_files_changed(_SHA_A, _SHA_B)
        env = run.call_args.kwargs["env"]
        for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
            assert var not in env
        assert env["LC_ALL"] == "C"


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git("init", "-q", "-b", "main", cwd=root)
    _git("config", "user.email", "t@example.com", cwd=root)
    _git("config", "user.name", "T", cwd=root)
    _git("config", "commit.gpgsign", "false", cwd=root)
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git("add", "seed.txt", cwd=root)
    _git("commit", "-q", "-m", "seed", cwd=root)
    return root


class TestExtractorUsesTheCommitRange:
    """End-to-end proof of the tier, against a real repository.

    The unit tests above prove the helper. This proves it is wired in, which is
    the part a shape-matching review cannot confirm.
    """

    def _build(self, repo: Path, tmp_path: Path, changed: int) -> tuple[Path, str, str]:
        start = _git("rev-parse", "HEAD", cwd=repo)
        for index in range(changed):
            (repo / f"f{index}.txt").write_text(f"{index}\n", encoding="utf-8")
        _git("add", "-A", cwd=repo)
        _git("commit", "-q", "-m", "work", cwd=repo)
        end = _git("rev-parse", "HEAD", cwd=repo)
        sessions = repo / ".agents" / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        log = sessions / "2026-08-03-session-1.json"
        log.write_text(
            json.dumps(
                {
                    "schemaVersion": "1.0",
                    "session": {
                        "id": "2026-08-03-session-1",
                        "date": "2026-08-03",
                        "branch": "main",
                        "startingCommit": start,
                        "objectives": ["probe"],
                    },
                    "endingCommit": end,
                    "protocolCompliance": {
                        "sessionStart": {},
                        "sessionEnd": {
                            "changesCommitted": {"Complete": True, "Evidence": "committed"}
                        },
                    },
                    "workLog": [
                        {
                            "time": "2026-08-03T00:00:00Z",
                            "action": "markdownlint reported Linting: 99 files, 0 issues",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return log, start, end

    def test_range_count_beats_the_prose_number(self, repo: Path, tmp_path: Path) -> None:
        log, _start, _end = self._build(repo, tmp_path, changed=3)
        out = tmp_path / "episodes"
        rc = ese.main([str(log), "--output-path", str(out), "--force"])
        assert rc == 0
        episode = json.loads((out / "episode-2026-08-03-session-1.json").read_text())
        # The prose says 99. The range says 3. The range wins.
        assert episode["metrics"]["files_changed"] == 3

    def test_prose_still_answers_when_the_range_is_unusable(
        self, repo: Path, tmp_path: Path
    ) -> None:
        """Negative control. With no usable range the prose fallback must still
        run, or this change would trade a wrong number for a missing one."""
        log, _start, _end = self._build(repo, tmp_path, changed=3)
        data = json.loads(log.read_text())
        data["session"]["startingCommit"] = ""
        log.write_text(json.dumps(data), encoding="utf-8")
        out = tmp_path / "episodes"
        rc = ese.main([str(log), "--output-path", str(out), "--force"])
        assert rc == 0
        episode = json.loads((out / "episode-2026-08-03-session-1.json").read_text())
        assert episode["metrics"]["files_changed"] == 99
