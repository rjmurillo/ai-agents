"""Tests for the reflect nudge marker, dedupe, and registered path (issue #5817).

The registered-path tests run the command string registered in
``.claude/settings.json`` through a shell, so a payload field the event does
not send cannot hide behind helper-level tests (the #3184 failure).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from tests.hooks.reflect_nudge_support import (
    HOOK_PATH,
    REPO_ROOT,
    human,
    nudge,
    payload,
    run_hook,
    write_transcript,
)


@pytest.fixture
def corrected(tmp_path: Path) -> Path:
    return write_transcript(
        tmp_path / "t.jsonl",
        [human("No, use the skill script"), human("fine"), human("that's wrong")],
    )


class TestDedupe:
    def test_second_stop_with_same_signals_is_silent(self, corrected: Path, tmp_path: Path) -> None:
        state = tmp_path / "state"
        _, first, _ = run_hook(payload(corrected), state)
        code, second, err = run_hook(payload(corrected), state)
        assert "systemMessage" in first
        assert (code, second) == (0, "")
        assert "already nudged" in err

    def test_new_correction_earns_a_new_nudge(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        path = write_transcript(tmp_path / "t.jsonl", [human("no, x")])
        run_hook(payload(path), state)
        write_transcript(path, [human("no, x"), human("wrong again")])
        _, out, _ = run_hook(payload(path), state)
        assert "2 correction" in out

    def test_sessions_do_not_share_markers(self, corrected: Path, tmp_path: Path) -> None:
        state = tmp_path / "state"
        run_hook(payload(corrected, "a"), state)
        _, out, _ = run_hook(payload(corrected, "b"), state)
        assert "systemMessage" in out

    def test_marker_holds_counts_only_with_owner_permissions(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        run_hook(payload(corrected), state)
        directory = state / nudge.STATE_SUBDIR
        (marker,) = list(directory.iterdir())
        text = marker.read_text(encoding="utf-8")
        assert set(json.loads(text)) == {"v", "high", "med"}
        assert "skill script" not in text
        assert marker.name.startswith("sess-1.") and marker.suffix == ".json"
        if os.name == "posix":
            assert (directory.stat().st_mode & 0o777) == 0o700
            assert (marker.stat().st_mode & 0o777) == 0o600

    @pytest.mark.parametrize("content", ["", "{torn", "[]", "garbage"])
    def test_marker_content_is_irrelevant_only_existence_counts(
        self, content: str, corrected: Path, tmp_path: Path
    ) -> None:
        """A torn or empty marker for this signal set still means already nudged."""
        state = tmp_path / "state"
        run_hook(payload(corrected), state)
        (marker,) = list((state / nudge.STATE_SUBDIR).iterdir())
        marker.write_text(content, encoding="utf-8")
        code, out, err = run_hook(payload(corrected), state)
        assert (code, out) == (0, "")
        assert "already nudged" in err

    def test_overlapping_stops_produce_exactly_one_nudge(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        stdin = payload(corrected)
        with ThreadPoolExecutor(max_workers=16) as pool:
            runs = list(pool.map(lambda _: run_hook(stdin, state), range(32)))
        nudges = [out for _, out, _ in runs if "systemMessage" in out]
        assert len(nudges) == 1
        assert all(code == 0 for code, _, _ in runs)

    @pytest.mark.skipif(os.name != "posix", reason="symlink semantics")
    def test_symlink_planted_at_the_marker_leaf_is_not_followed(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        run_hook(payload(corrected), state)
        directory = state / nudge.STATE_SUBDIR
        (marker,) = list(directory.iterdir())
        victim = tmp_path / "victim"
        victim.write_text("keep", encoding="utf-8")
        marker.unlink()
        marker.symlink_to(victim)
        code, out, _ = run_hook(payload(corrected), state)
        assert (code, out) == (0, "")
        assert victim.read_text(encoding="utf-8") == "keep"

    @pytest.mark.skipif(os.name != "posix", reason="symlink semantics")
    def test_symlinked_state_root_is_resolved_and_used(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real)
        _, out, _ = run_hook(payload(corrected), link)
        assert "systemMessage" in out
        assert (real / nudge.STATE_SUBDIR).is_dir()

    @pytest.mark.skipif(os.name != "posix", reason="mode bits")
    def test_group_writable_state_root_is_accepted(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        """A 0o002 umask makes this normal; the 0o700 child carries the safety."""
        state = tmp_path / "state"
        state.mkdir()
        state.chmod(0o775)
        _, out, _ = run_hook(payload(corrected), state)
        assert "systemMessage" in out

    def test_marker_path_that_is_a_directory_means_already_nudged(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        run_hook(payload(corrected), state)
        (marker,) = list((state / nudge.STATE_SUBDIR).iterdir())
        marker.unlink()
        marker.mkdir()
        code, out, _ = run_hook(payload(corrected), state)
        assert (code, out) == (0, "")

    @pytest.mark.skipif(os.name != "posix", reason="symlink semantics")
    def test_symlinked_marker_directory_is_refused(self, corrected: Path, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        (state / nudge.STATE_SUBDIR).symlink_to(elsewhere)
        code, out, err = run_hook(payload(corrected), state)
        assert (code, out) == (0, "")
        assert "marker directory unsafe" in err
        assert list(elsewhere.iterdir()) == []

    @pytest.mark.skipif(os.name != "posix", reason="uid semantics")
    def test_directory_owned_by_another_user_is_refused(
        self, corrected: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        other_uid = os.getuid() + 1
        monkeypatch.setattr(nudge.os, "getuid", lambda: other_uid)
        code, out, err = run_hook(payload(corrected), tmp_path / "state")
        assert (code, out) == (0, "")
        assert "unsafe" in err

    @pytest.mark.skipif(
        os.name != "posix" or os.geteuid() == 0, reason="needs a non-root POSIX user"
    )
    def test_unwritable_marker_directory_propagates_for_main_to_fail_open(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        path = write_transcript(tmp_path / "t.jsonl", [human("no, x")])
        run_hook(payload(path), state)
        directory = state / nudge.STATE_SUBDIR
        write_transcript(path, [human("no, x"), human("wrong again")])
        directory.chmod(0o500)
        try:
            with pytest.raises(PermissionError):
                run_hook(payload(path), state)
        finally:
            directory.chmod(0o700)

    def test_old_markers_are_pruned_and_fresh_ones_kept(self, tmp_path: Path) -> None:
        old, fresh = tmp_path / "old.json", tmp_path / "fresh.json"
        old.write_text("{}", encoding="utf-8")
        fresh.write_text("{}", encoding="utf-8")
        os.utime(old, (1, 1))
        just_inside_window = fresh.stat().st_mtime + nudge.MARKER_MAX_AGE_SECONDS - 1
        nudge.prune_markers(tmp_path, just_inside_window)
        assert not old.exists()
        assert fresh.exists()

    def test_prune_stops_at_the_per_run_limit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for i in range(4):
            (tmp_path / f"{i}.json").write_text("{}", encoding="utf-8")
            os.utime(tmp_path / f"{i}.json", (1, 1))
        monkeypatch.setattr(nudge, "MARKER_PRUNE_LIMIT", 2)
        nudge.prune_markers(tmp_path, 10**12)
        assert len(list(tmp_path.iterdir())) == 2

    def test_prune_skips_an_entry_it_cannot_remove(self, tmp_path: Path) -> None:
        stuck = tmp_path / "stuck"
        stuck.mkdir()
        (stuck / "child").write_text("x", encoding="utf-8")
        os.utime(stuck, (1, 1))
        nudge.prune_markers(tmp_path, 10**12)
        assert stuck.exists()

    def test_prune_failure_does_not_lose_the_nudge(
        self, corrected: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_a: Any, **_k: Any) -> None:
            raise OSError("listing failed")

        monkeypatch.setattr(nudge, "prune_markers", boom)
        code, out, err = run_hook(payload(corrected), tmp_path / "state")
        assert code == 0
        assert "systemMessage" in out
        assert "prune failed" in err

    @pytest.mark.skipif(os.name != "posix", reason="mode bits")
    def test_marker_directory_open_to_group_or_other_is_refused(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        directory = tmp_path / "state" / nudge.STATE_SUBDIR
        directory.mkdir(parents=True)
        directory.chmod(0o755)
        code, out, err = run_hook(payload(corrected), tmp_path / "state")
        assert (code, out) == (0, "")
        assert "marker directory unsafe" in err


class TestRegisteredPath:
    """Drive the command registered in .claude/settings.json, assert exit status."""

    @staticmethod
    def _command() -> str:
        settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        entries = settings["hooks"]["Stop"]
        assert len(entries) == 1 and len(entries[0]["hooks"]) == 1
        hook = entries[0]["hooks"][0]
        assert hook["type"] == "command" and hook["timeout"] <= 10
        return str(hook["command"])

    def _invoke(self, stdin_text: str, state: Path) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(REPO_ROOT), "XDG_STATE_HOME": str(state)}
        return subprocess.run(
            ["sh", "-c", self._command()],
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
            check=False,
        )

    @pytest.mark.skipif(os.name != "posix", reason="registered command is a POSIX shell string")
    def test_registered_command_nudges_and_exits_zero(
        self, corrected: Path, tmp_path: Path
    ) -> None:
        stop_dir = REPO_ROOT / ".claude" / "hooks" / "Stop"
        before = sorted(p.name for p in stop_dir.iterdir())
        done = self._invoke(payload(corrected), tmp_path / "state")
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout)["systemMessage"].startswith("reflect-trigger:")
        assert sorted(p.name for p in stop_dir.iterdir()) == before

    @pytest.mark.skipif(os.name != "posix", reason="registered command is a POSIX shell string")
    def test_registered_command_fails_open_without_transcript_path(self, tmp_path: Path) -> None:
        done = self._invoke(payload(None), tmp_path / "state")
        assert done.returncode == 0
        assert done.stdout == ""
        assert "fail-open" in done.stderr

    @pytest.mark.skipif(os.name != "posix", reason="registered command is a POSIX shell string")
    def test_registered_command_exits_zero_when_the_script_is_missing(
        self, tmp_path: Path
    ) -> None:
        """python exits 2 on a missing script and exit 2 blocks Stop; `|| true` prevents it."""
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
        command = self._command()
        assert command.endswith("|| true")
        guarded = subprocess.run(
            ["sh", "-c", command], capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=30, check=False,
        )  # fmt: skip
        bare = subprocess.run(
            ["sh", "-c", command.removesuffix(" || true")], capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=30, check=False,
        )  # fmt: skip
        assert guarded.returncode == 0
        assert bare.returncode == 2

    def test_source_cannot_emit_a_block_decision(self) -> None:
        tree = ast.parse(HOOK_PATH.read_text(encoding="utf-8"))
        docstring = ast.get_docstring(tree, clean=False)
        strings = {
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value != docstring
        }
        assert not strings & {"decision", "block", "continue", "reason"}

    def test_rendered_hook_matches_template(self) -> None:
        rendered = REPO_ROOT / ".claude" / "hooks" / "Stop" / "invoke_reflect_nudge.py"
        assert rendered.read_bytes() == HOOK_PATH.read_bytes()
