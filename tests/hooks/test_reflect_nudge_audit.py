"""AC-22: the hook opens only its allowed inputs and reads only its allowed env vars.

REQ-048 TASK-004. Both branches run through ``run()`` under a ``sys.addaudithook``
probe on ``open`` and a recording mapping installed as ``os.environ``.

Audit hooks cannot be removed once added, so the probe installs once per process
and records only while ``_collector`` is set. Integer file descriptors are
skipped: each comes from an ``os.open`` call that is audited on its own path.
"""

from __future__ import annotations

import io
import json
import os
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from tests.hooks.friction_nudge_support import THRESHOLD_ENV, friction_records
from tests.hooks.reflect_nudge_safety_support import (
    STATE_SUBDIR,
    correction_records,
    isolated_home,  # noqa: F401  (pytest fixture)
    write_transcript,
)
from tests.hooks.reflect_nudge_support import HOOK_PATH, PLUGIN_LIB, nudge

pytestmark = pytest.mark.usefixtures("isolated_home")

ALLOWED_ENV = frozenset(
    {
        THRESHOLD_ENV,
        "XDG_STATE_HOME",
        "LOCALAPPDATA",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
    }
)
_collector: list[str] | None = None


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if event != "open" or _collector is None:
        return
    target = args[0]
    if isinstance(target, (str, bytes, os.PathLike)):
        _collector.append(os.fsdecode(target))


sys.addaudithook(_audit)


class RecordingEnviron(Mapping[str, str]):
    """Read-only mapping that records every key looked up."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)
        self.touched: set[str] = set()

    def __getitem__(self, key: str) -> str:
        self.touched.add(key)
        return self._values[key]

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self.touched.add(key)
        return key in self._values

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


def _interpreter_roots() -> tuple[str, ...]:
    roots = {sys.base_prefix, sys.prefix, sys.exec_prefix, sys.base_exec_prefix}
    return tuple(os.path.realpath(r) for r in roots)


def _is_allowed(opened: str, inputs: tuple[Path, ...]) -> bool:
    real = os.path.realpath(opened)
    allowed = (*(str(p.resolve()) for p in inputs), *_interpreter_roots())
    return any(real == a or real.startswith(a + os.sep) for a in allowed)


def _run_recorded(
    stdin_text: str, env: RecordingEnviron, state_root: Path | None
) -> tuple[int, str, list[str]]:
    """Run the hook once with the audit probe on and ``os.environ`` replaced by ``env``."""
    global _collector
    out, err = io.StringIO(), io.StringIO()
    opened: list[str] = []
    _collector = opened
    try:
        with mock.patch.object(os, "environ", env):
            code = nudge.run(io.StringIO(stdin_text), out, err, env, state_root=state_root)
    finally:
        _collector = None
    return code, out.getvalue(), opened


@pytest.fixture
def both_branches(tmp_path: Path) -> Path:
    """A transcript that earns a correction nudge and a friction nudge (score 11, tier 1)."""
    work = tmp_path / "work"
    work.mkdir()
    records = [*correction_records(), *friction_records(denials=4, feedback=1)]
    return write_transcript(work / "t.jsonl", records)


def _payload(transcript: Path) -> str:
    body = {
        "session_id": "sess-1",
        "transcript_path": str(transcript),
        "cwd": str(transcript.parent),
    }
    return json.dumps(body)


# POSIX derives the state root from XDG_STATE_HOME and HOME; Windows uses LOCALAPPDATA.
POSIX_STATE = pytest.mark.skipif(os.name == "nt", reason="POSIX state-root derivation")


class TestProbesHaveTeeth:
    """Negative controls: each probe must see a read it is meant to catch."""

    def test_audit_probe_sees_an_unlisted_open(self, tmp_path: Path) -> None:
        planted = tmp_path / "planted.txt"
        planted.write_text("x", encoding="utf-8")
        global _collector
        seen: list[str] = []
        _collector = seen
        try:
            planted.read_text(encoding="utf-8")
        finally:
            _collector = None
        assert str(planted) in seen
        assert not _is_allowed(str(planted), ())

    def test_environ_recorder_sees_an_unlisted_read(self) -> None:
        recorder = RecordingEnviron({"SECRET_TOKEN": "t"})
        assert recorder.get("SECRET_TOKEN") == "t"
        assert recorder.touched - ALLOWED_ENV == {"SECRET_TOKEN"}


class TestOpenAudit:
    def test_no_file_outside_the_allowed_inputs_is_opened(
        self, both_branches: Path, tmp_path: Path
    ) -> None:
        planted = both_branches.parent / "planted.txt"
        planted.write_text("do not read", encoding="utf-8")
        state_root = tmp_path / "state"
        env = RecordingEnviron({THRESHOLD_ENV: "10", "HOME": str(tmp_path / "home")})

        code, out, opened = _run_recorded(_payload(both_branches), env, state_root)

        assert code == 0
        assert out.count("/reflect") == 1 and "/retrospective" in out  # both branches ran
        assert str(planted) not in opened
        inputs = (both_branches, state_root, PLUGIN_LIB, HOOK_PATH.parent)
        stray = [p for p in opened if not _is_allowed(p, inputs)]
        assert stray == []
        assert any(Path(p).resolve() == both_branches.resolve() for p in opened)

    @POSIX_STATE
    def test_default_state_root_under_home_is_the_only_other_write_target(
        self, both_branches: Path, tmp_path: Path
    ) -> None:
        home = tmp_path / "home"
        env = RecordingEnviron({"HOME": str(home)})
        code, out, opened = _run_recorded(_payload(both_branches), env, None)
        state_dir = home / ".local" / "state" / STATE_SUBDIR
        assert code == 0 and "systemMessage" in out
        inputs = (both_branches, state_dir, PLUGIN_LIB, HOOK_PATH.parent)
        assert [p for p in opened if not _is_allowed(p, inputs)] == []
        assert any(Path(p).parent == state_dir for p in opened)


class TestEnvironAudit:
    def test_only_listed_variables_are_read_through_env_and_path_home(
        self, both_branches: Path, tmp_path: Path
    ) -> None:
        env = RecordingEnviron({"HOME": str(tmp_path / "home"), "SECRET_TOKEN": "t"})
        code, out, _ = _run_recorded(_payload(both_branches), env, None)
        assert code == 0 and "systemMessage" in out
        assert env.touched - ALLOWED_ENV == set()
        assert "HOME" in env.touched  # Path.home() reached the patched os.environ
        assert "SECRET_TOKEN" not in env.touched

    @POSIX_STATE
    def test_threshold_and_state_variables_are_read_when_set(
        self, both_branches: Path, tmp_path: Path
    ) -> None:
        env = RecordingEnviron(
            {THRESHOLD_ENV: "10", "XDG_STATE_HOME": str(tmp_path / "xdg"), "HOME": str(tmp_path)}
        )
        code, _, _ = _run_recorded(_payload(both_branches), env, None)
        assert code == 0
        assert {THRESHOLD_ENV, "XDG_STATE_HOME"} <= env.touched
        assert env.touched - ALLOWED_ENV == set()

    def test_off_run_reads_only_the_threshold_variable(
        self, both_branches: Path, tmp_path: Path
    ) -> None:
        env = RecordingEnviron({THRESHOLD_ENV: "off"})
        code, out, opened = _run_recorded(_payload(both_branches), env, tmp_path / "state")
        assert (code, out) == (0, "")
        assert env.touched == {THRESHOLD_ENV}
        assert not [p for p in opened if not _is_allowed(p, ())]
