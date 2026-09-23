"""A byte-identical root move must not count as authoring a session log (#5420)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1] / ".github" / "scripts" / "validate_investigation_claims.py"
)
_spec = importlib.util.spec_from_file_location("validate_investigation_claims_root_move", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


class TestGetCommitForSession:
    """A byte-identical root move is not authorship of the session log."""

    @staticmethod
    def _git(repo: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    def _commit(self, repo: Path, message: str) -> str:
        self._git(repo, "add", "-A")
        self._git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message)
        return self._git(repo, "rev-parse", "HEAD")

    def test_identical_move_reports_authoring_commit(self, tmp_path: Path, monkeypatch) -> None:
        repo = tmp_path / "repo"
        (repo / ".agents/sessions").mkdir(parents=True)
        self._git(repo.parent, "init", "-q", str(repo))
        (repo / ".agents/sessions/s.json").write_bytes(b'{"claim": "investigation only"}\n')
        authored = self._commit(repo, "add session")
        (repo / ".project-toolkit").mkdir()
        self._git(repo, "mv", ".agents/sessions", ".project-toolkit/sessions")
        self._commit(repo, "move root")
        monkeypatch.chdir(repo)

        moved = Path(".project-toolkit/sessions/s.json")
        assert _mod.get_commit_for_session(moved) == authored

        moved.write_bytes(b'{"claim": "investigation only", "edited": true}\n')
        edited = self._commit(repo, "edit session")
        assert _mod.get_commit_for_session(moved) == edited
