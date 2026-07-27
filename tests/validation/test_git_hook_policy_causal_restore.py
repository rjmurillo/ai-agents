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

import io
import json
import subprocess
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
        err = capsys.readouterr().err.replace("\\", "/")
        assert _GRAPH in err
        # The word "rebuild" is not the repair. An operator staring at a blocked
        # commit needs the command, and a command missing any of these flags
        # rebuilds the wrong file or from the wrong source (issue #3370).
        assert "python3" in err, f"no runnable command in stderr: {err!r}"
        repair = err[err.index("python3") :]
        for flag in ("--reset-graph", "--episode-path", "--graph-path"):
            assert flag in repair, f"repair command omits {flag}: {repair!r}"
        assert _GRAPH in repair, f"repair command does not name the graph: {repair!r}"

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

    def test_a_successful_restore_puts_the_bytes_back(self, repo, monkeypatch):
        """The mutation has to happen after the snapshot, or the test is vacuous.

        ``update_causal_graph`` snapshots at entry. Mutating the file before the
        call puts the mutation *into* the snapshot, so the end state matches
        whether restore ran or not. Writing it from inside the failing updater
        is the only ordering that makes the assertion discriminate.
        """
        graph = _write_graph(repo, '{"nodes": ["original"]}')

        def _mutate_then_fail(*_a, **_k) -> int:
            graph.write_text('{"nodes": ["mutated"]}', encoding="utf-8")
            return 1

        monkeypatch.setattr(policy, "_apply_causal_graph_updates", _mutate_then_fail)
        assert policy.update_causal_graph(repo) == 0
        assert json.loads(graph.read_text(encoding="utf-8"))["nodes"] == ["original"]

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


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], returncode, stdout, "")


def _run_suppression_push(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
    diff_text: str,
    changed_paths: tuple[str, ...] = ("pkg/module.py",),
) -> int:
    head = "a" * 40
    remote = "b" * 40
    base = "c" * 40
    expected_range = f"{base}..{head}"
    monkeypatch.setattr(policy, "_check_history_integrity", lambda root: 0)
    monkeypatch.setattr(policy, "_merge_base", lambda root, base_ref, head_ref: base)

    def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[:4] == ["diff", "--name-only", "--diff-filter=ACMRT", "-z"]:
            assert args[4] == expected_range
            return _completed("\0".join(changed_paths) + "\0")
        if args[:4] == ["diff", "--unified=0", "--no-color", expected_range]:
            assert args[4] == "--"
            assert tuple(args[5:]) == changed_paths
            return _completed(diff_text)
        raise AssertionError(f"unexpected git call: {args!r}")

    monkeypatch.setattr(policy, "_run_git", _run_git)
    stdin = io.StringIO(f"refs/heads/topic {head} refs/heads/topic {remote}\n")
    return policy.check_pushed_suppressions(stdin, repo_root)


class TestPushedSuppressionPolicy:
    def test_newly_added_type_ignore_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# type" ": ignore[arg-type]"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -1,0 +2 @@
+value = call()  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 1
        err = capsys.readouterr().err
        assert "security suppression comments detected" in err
        assert "pkg/module.py:2" in err

    def test_pre_existing_type_ignore_touched_elsewhere_is_allowed(self, tmp_path, monkeypatch):
        diff = """diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -2 +2 @@
-old = 1
+new = 1
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_added_file_with_type_ignore_is_blocked(self, tmp_path, monkeypatch, capsys):
        suppression = "# type" ": ignore[assignment]"
        diff = f"""diff --git a/pkg/new.py b/pkg/new.py
new file mode 100644
--- /dev/null
+++ b/pkg/new.py
@@ -0,0 +1,2 @@
+from pkg import value
+result = value  {suppression}
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff, ("pkg/new.py",)) == 1
        assert "pkg/new.py:2" in capsys.readouterr().err

    def test_type_ignore_on_context_line_adjacent_to_edit_is_allowed(self, tmp_path, monkeypatch):
        suppression = "# type" ": ignore[arg-type]"
        diff = f"""diff --git a/pkg/module.py b/pkg/module.py
--- a/pkg/module.py
+++ b/pkg/module.py
@@ -1,2 +1,2 @@
 value = call()  {suppression}
-old = 1
+new = 1
"""

        assert _run_suppression_push(monkeypatch, tmp_path, diff) == 0

    def test_no_base_range_spec_fails_open(self, tmp_path, monkeypatch):
        """When resolve_push_update cannot compute a base, range_spec has no '..'."""
        head = "a" * 40
        remote = "0" * 40  # zero SHA = new branch
        monkeypatch.setattr(policy, "_check_history_integrity", lambda root: 0)
        monkeypatch.setattr(policy, "_merge_base", lambda root, base_ref, head_ref: None)

        def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            if args[:4] == ["ls-tree", "-r", "-z", "--name-only"]:
                return _completed("pkg/module.py\0")
            if args[:4] == ["diff", "--unified=0", "--no-color", head]:
                raise AssertionError("should not reach diff with bare SHA")
            return _completed("")

        monkeypatch.setattr(policy, "_run_git", _run_git)
        stdin = io.StringIO(f"refs/heads/new-branch {head} refs/heads/new-branch {remote}\n")
        # Fails open: no violations reported because diff is unreliable
        assert policy.check_pushed_suppressions(stdin, tmp_path) == 0


class TestAdrReviewPolicyMergeScope:
    def test_non_merge_adr_without_review_evidence_is_blocked(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: False)
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)

        result = policy.check_adr_review_policy(
            [".agents/architecture/ADR-999-test.md"],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err

    def test_merge_in_progress_with_staged_adr_from_main_is_allowed(self, tmp_path, monkeypatch):
        adr_path = ".agents/architecture/ADR-120-reviewed-on-main.md"
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(
            policy, "_paths_on_merge_head", lambda paths, root: {adr_path}
        )

        result = policy.check_adr_review_policy([adr_path], tmp_path)

        assert result == 0

    def test_merge_in_progress_with_branch_authored_adr_is_still_gated(
        self,
        tmp_path,
        monkeypatch,
        capsys,
    ):
        monkeypatch.setattr(policy, "_gated_adr_review_paths", lambda paths, root: list(paths))
        monkeypatch.setattr(policy, "_merge_in_progress", lambda root: True)
        monkeypatch.setattr(policy, "_paths_on_merge_head", lambda paths, root: set())
        monkeypatch.setattr(policy, "_today_session_log", lambda sessions_dir: None)

        result = policy.check_adr_review_policy(
            [".agents/architecture/ADR-999-branch-authored-during-merge.md"],
            tmp_path,
        )

        assert result == 1
        assert "ADR changes require adr-review evidence" in capsys.readouterr().err


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
