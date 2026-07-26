"""Snapshot restoration must fail closed, not traceback (Issue #3389).

``update_causal_graph`` snapshots the generated causal graph, runs the updater,
and restores the snapshot when the updater fails. The restore itself was
unguarded: an ``OSError`` from ``Path.write_bytes`` or ``Path.unlink`` escaped
the function, so the operator got a traceback naming neither failure, and the
graph could be left partially written.

Two failures are in play whenever this path runs, and the operator needs both:
the updater failed, and the attempt to undo it also failed. A message naming
only one of them sends the reader to the wrong repair.

The success-shaped line matters as much as the exit code. ``original graph
restored`` printed after a failed restore is worse than silence, because it
tells the reader the thing they most need to doubt.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validation import git_hook_policy as policy  # noqa: E402

_GRAPH = ".agents/memory/causality/causal-graph.json"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo whose staged set is nonempty and whose updater always fails."""
    monkeypatch.setattr(
        policy, "_staged_episode_paths", lambda root, flt: ["ep.md"] if flt == "ACMR" else []
    )
    monkeypatch.setattr(policy, "_apply_causal_graph_updates", lambda *a, **k: 1)
    return tmp_path


def _write_graph(repo_root: Path, text: str = '{"nodes": []}') -> Path:
    path = repo_root / _GRAPH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestARestoreFailureBlocks:
    def test_a_write_failure_returns_two(self, repo, monkeypatch, capsys):
        """The graph existed, so restoration writes the snapshot back."""
        _write_graph(repo)
        monkeypatch.setattr(
            Path, "write_bytes", lambda self, data: (_ for _ in ()).throw(OSError("disk full"))
        )
        assert policy.update_causal_graph(repo) == 2
        assert "disk full" in capsys.readouterr().err

    def test_an_unlink_failure_returns_two(self, repo, monkeypatch, capsys):
        """The graph did not exist, so restoration removes what the updater made.

        The snapshot is None on this path, which is the branch that reaches
        Path.unlink rather than Path.write_bytes.
        """
        monkeypatch.setattr(
            Path, "unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(OSError("EPERM"))
        )
        assert policy.update_causal_graph(repo) == 2
        assert "EPERM" in capsys.readouterr().err

    def test_it_never_claims_the_graph_was_restored(self, repo, monkeypatch, capsys):
        """The line that must not print. It is the one the reader trusts."""
        _write_graph(repo)
        monkeypatch.setattr(
            Path, "write_bytes", lambda self, data: (_ for _ in ()).throw(OSError("nope"))
        )
        policy.update_causal_graph(repo)
        assert "original graph restored" not in capsys.readouterr().err

    def test_it_names_both_failures(self, repo, monkeypatch, capsys):
        """One failure caused the other; a message naming one misdirects."""
        _write_graph(repo)
        monkeypatch.setattr(
            Path, "write_bytes", lambda self, data: (_ for _ in ()).throw(OSError("nope"))
        )
        policy.update_causal_graph(repo)
        err = capsys.readouterr().err
        assert "causal graph update failed" in err
        assert "restoring the original causal graph also failed" in err

    def test_it_names_the_graph_and_the_repair(self, repo, monkeypatch, capsys):
        """A blocked commit with no next step is a blocked commit twice."""
        _write_graph(repo)
        monkeypatch.setattr(
            Path, "write_bytes", lambda self, data: (_ for _ in ()).throw(OSError("nope"))
        )
        policy.update_causal_graph(repo)
        err = capsys.readouterr().err
        assert _GRAPH in err.replace("\\", "/")
        assert "update_causal_graph" in err or "rebuild" in err.lower()

    def test_it_does_not_raise(self, repo, monkeypatch):
        """The point of the change: an exit code, not a traceback."""
        _write_graph(repo)
        monkeypatch.setattr(
            Path, "write_bytes", lambda self, data: (_ for _ in ()).throw(OSError("nope"))
        )
        policy.update_causal_graph(repo)


class TestTheOrdinaryPathsAreUnchanged:
    """Negative controls. A guard that swallows the success path is not a guard."""

    def test_a_successful_restore_still_warns_and_passes(self, repo, capsys):
        _write_graph(repo, '{"nodes": ["original"]}')
        assert policy.update_causal_graph(repo) == 0
        err = capsys.readouterr().err
        assert "original graph restored" in err

    def test_a_successful_restore_puts_the_bytes_back(self, repo):
        graph = _write_graph(repo, '{"nodes": ["original"]}')
        graph.write_text('{"nodes": ["mutated"]}', encoding="utf-8")
        # Re-snapshot by re-reading: update_causal_graph snapshots at entry, so
        # write the mutation first and let the failing updater trigger restore.
        assert policy.update_causal_graph(repo) == 0
        assert json.loads(graph.read_text(encoding="utf-8"))["nodes"] == ["mutated"]

    def test_no_staged_episodes_is_a_no_op(self, tmp_path, monkeypatch):
        monkeypatch.setattr(policy, "_staged_episode_paths", lambda root, flt: [])
        assert policy.update_causal_graph(tmp_path) == 0

    def test_a_successful_update_never_reaches_the_restore(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            policy, "_staged_episode_paths", lambda root, flt: ["ep.md"] if flt == "ACMR" else []
        )
        monkeypatch.setattr(policy, "_apply_causal_graph_updates", lambda *a, **k: 0)
        monkeypatch.setattr(policy, "_stage_causal_graph", lambda *a, **k: 0)

        def _boom(*_a, **_k):
            raise AssertionError("restore ran on the success path")

        monkeypatch.setattr(policy, "_restore_file", _boom)
        assert policy.update_causal_graph(tmp_path) == 0


class TestTheHarnessActuallyExercisesRestore:
    """Vacuity control: these tests are worthless if restore never runs."""

    def test_the_failing_updater_reaches_restore(self, repo, monkeypatch):
        seen: list[bytes | None] = []

        def _record(path: Path, snapshot: bytes | None) -> None:
            seen.append(snapshot)

        monkeypatch.setattr(policy, "_restore_file", _record)
        policy.update_causal_graph(repo)
        assert len(seen) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
