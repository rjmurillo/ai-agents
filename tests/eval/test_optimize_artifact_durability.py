"""Durability of the atomic write across a host crash (issue #3591).

`os.replace` publishes a new directory entry atomically on both platforms.
Atomicity is not durability: it says no reader sees a half-written entry, not
that the entry survives a power cut. The consultation ledger charges before it
scores so a crash cannot hand back a look for free, so an erasable charge
defeats the ordering it exists to protect.

POSIX closes that with `_fsync_dir`. Windows cannot open a directory as a
descriptor, so the guarantee has to come from the move, which means asking for
`MOVEFILE_WRITE_THROUGH` explicitly because CPython does not.

Most tests here drive the Windows branch through a stand-in so the flag word
is checkable on any host. `TestOnRealWindows` is the one that runs the real
Win32 call, and it is wired into the `test-windows-pwsh` job in
`.github/workflows/pytest.yml` so the ctypes path is not shipped unrun.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.windows_path

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
# Scope the sys.path mutation to the module load and remove it afterward so it
# does not leak into other tests (mirrors tests/eval/test_optimize_artifact_cli.py).
_path_added = str(_EVAL_DIR) not in sys.path
try:
    if _path_added:
        sys.path.insert(0, str(_EVAL_DIR))
    _SCRIPT = _EVAL_DIR / "optimize-artifact.py"
    _spec = importlib.util.spec_from_file_location("optimize_artifact", _SCRIPT)
    assert _spec is not None and _spec.loader is not None
    oa = importlib.util.module_from_spec(_spec)
    sys.modules["optimize_artifact"] = oa
    _spec.loader.exec_module(oa)
finally:
    if _path_added and str(_EVAL_DIR) in sys.path:
        sys.path.remove(str(_EVAL_DIR))


ON_WINDOWS = os.name == "nt"


class Mover:
    """A stand-in for `MoveFileExW` that records how it was called."""

    def __init__(self, *, succeed: bool = True, perform: bool = True) -> None:
        self.succeed = succeed
        self.perform = perform
        self.calls: list[tuple[str, str, int]] = []

    def __call__(self, source: str, destination: str, flags: int) -> int:
        self.calls.append((source, destination, flags))
        if self.perform and self.succeed:
            os.replace(source, destination)
        return 1 if self.succeed else 0


@pytest.fixture
def as_windows(monkeypatch: pytest.MonkeyPatch):
    """Take the Windows branch of `_durable_replace` on any host.

    Patching the module's own platform predicate, never `os.name`. Assigning
    to the real `os` module is not inert: CPython's `ctypes` package reads
    `os.name` at import and pulls Windows-only symbols when it says `nt`, so
    the first draft of this fixture broke `import ctypes` inside the branch it
    was trying to reach and reported it as a product failure.
    """
    monkeypatch.setattr(oa, "_is_windows", lambda: True)


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "src.tmp"
    source.write_text("new", encoding="utf-8")
    destination = tmp_path / "dst.json"
    destination.write_text("old", encoding="utf-8")
    return source, destination


class TestTheFlagsWeAskFor:
    """The whole fix is one bit. These make that bit falsifiable."""

    def test_write_through_is_requested(self, tmp_path, as_windows, monkeypatch):
        mover = Mover()
        monkeypatch.setattr(oa, "_win32_move_file_ex", lambda: mover)
        source, destination = _pair(tmp_path)

        oa._durable_replace(source, destination)

        assert len(mover.calls) == 1
        _, _, flags = mover.calls[0]
        # Spelled as a bit test rather than only an equality so a future edit
        # that keeps the call and drops the durability fails on the reason.
        assert flags & oa._MOVEFILE_WRITE_THROUGH, (
            "MOVEFILE_WRITE_THROUGH is the only thing this call adds over "
            "os.replace; without it the move is atomic but not durable"
        )
        assert flags & oa._MOVEFILE_REPLACE_EXISTING, (
            "without REPLACE_EXISTING the move fails whenever the "
            "destination already exists, which is every rewrite"
        )
        assert flags == 0x9

    def test_the_flag_values_match_winbase(self):
        """Pinned against the Win32 header, not against our own arithmetic.

        A typo here is invisible: MoveFileExW ignores unknown bits, so a wrong
        WRITE_THROUGH value still returns success and still loses the charge.
        """
        assert oa._MOVEFILE_REPLACE_EXISTING == 0x1
        assert oa._MOVEFILE_WRITE_THROUGH == 0x8

    def test_the_paths_are_passed_through_unchanged(self, tmp_path, as_windows, monkeypatch):
        mover = Mover()
        monkeypatch.setattr(oa, "_win32_move_file_ex", lambda: mover)
        source, destination = _pair(tmp_path)

        oa._durable_replace(source, destination)

        assert mover.calls[0][0] == str(source)
        assert mover.calls[0][1] == str(destination)


class TestTheWindowsBranch:
    def test_a_successful_move_publishes_the_new_content(
        self, tmp_path, as_windows, monkeypatch
    ):
        mover = Mover()
        monkeypatch.setattr(oa, "_win32_move_file_ex", lambda: mover)
        source, destination = _pair(tmp_path)

        oa._durable_replace(source, destination)

        assert destination.read_text(encoding="utf-8") == "new"
        assert not source.exists()

    def test_a_failed_move_raises(self, tmp_path, as_windows, monkeypatch):
        """Matching os.replace. This runs before the entry is published, so
        refusing costs the caller nothing, which is why it raises where
        `_fsync_dir` warns."""
        monkeypatch.setattr(oa, "_win32_move_file_ex", lambda: Mover(succeed=False))
        source, destination = _pair(tmp_path)

        with pytest.raises(OSError, match="could not move"):
            oa._durable_replace(source, destination)

        assert destination.read_text(encoding="utf-8") == "old"

    def test_a_failed_move_reaches_the_caller_as_one_config_error(
        self, tmp_path, as_windows, monkeypatch
    ):
        """`_write_atomic` owns the conversion; this proves the new raise
        lands inside its handler rather than escaping as a traceback."""
        monkeypatch.setattr(oa, "_win32_move_file_ex", lambda: Mover(succeed=False))
        destination = tmp_path / "dst.json"
        destination.write_text("old", encoding="utf-8")

        with pytest.raises(oa.ConfigError, match="could not write"):
            oa._write_atomic(destination, "new")

        assert destination.read_text(encoding="utf-8") == "old"
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".dst.json.")]
        assert leftovers == [], f"temp file survived a failed move: {leftovers}"

    def test_an_unavailable_win32_layer_still_writes_and_says_so(
        self, tmp_path, as_windows, monkeypatch, capsys
    ):
        """Availability beats durability when the two conflict.

        Refusing the write would turn a durability gap into an outage, so the
        fallback publishes the entry the old way and reports the weaker
        guarantee on stderr.
        """
        monkeypatch.setattr(oa, "_win32_move_file_ex", lambda: None)
        source, destination = _pair(tmp_path)

        oa._durable_replace(source, destination)

        assert destination.read_text(encoding="utf-8") == "new"
        err = capsys.readouterr()
        assert "durability across a host crash is not guaranteed" in err.err
        assert err.out == "", "a warning must not contaminate the one JSON document on stdout"

    def test_the_fallback_is_not_what_a_healthy_host_takes(
        self, tmp_path, as_windows, monkeypatch, capsys
    ):
        """Isolating control for the test above. If the success path also
        warned, that assertion would pass without the fallback existing."""
        monkeypatch.setattr(oa, "_win32_move_file_ex", lambda: Mover())
        source, destination = _pair(tmp_path)

        oa._durable_replace(source, destination)

        assert capsys.readouterr().err == ""


class TestThePosixBranch:
    def test_posix_replaces_and_fsyncs_the_parent(self, tmp_path, monkeypatch):
        # Force the POSIX arm rather than inferring it from the host. On
        # Windows the real `_is_windows` sends this through the Win32 arm, so
        # the parent fsync never runs and the assertion below reads an empty
        # list; measured as a CI failure on the Windows runner. Pinning the
        # branch tests it on every platform, which skipping would not, and
        # costs nothing here because the one POSIX-only syscall in the arm,
        # the directory fsync, is already replaced by the recorder below.
        monkeypatch.setattr(oa, "_is_windows", lambda: False)
        synced: list[Path] = []
        monkeypatch.setattr(oa, "_fsync_dir", synced.append)
        # If the Windows branch were taken by mistake this stand-in would
        # record the call, so the assertion below is two-sided.
        mover = Mover()
        monkeypatch.setattr(oa, "_win32_move_file_ex", lambda: mover)
        source, destination = _pair(tmp_path)

        oa._durable_replace(source, destination)

        assert destination.read_text(encoding="utf-8") == "new"
        assert synced == [tmp_path]
        assert mover.calls == [], "POSIX must not reach the Win32 mover"

    @pytest.mark.skipif(ON_WINDOWS, reason="asserts the POSIX-only resolver answer")
    def test_the_resolver_reports_no_win32_layer_on_posix(self):
        assert oa._win32_move_file_ex() is None

    def test_write_atomic_round_trips(self, tmp_path):
        target = tmp_path / "ledger.json"
        oa._write_atomic(target, '{"n": 1}')
        assert target.read_text(encoding="utf-8") == '{"n": 1}'
        oa._write_atomic(target, '{"n": 2}')
        assert target.read_text(encoding="utf-8") == '{"n": 2}'
        assert [p.name for p in tmp_path.iterdir()] == ["ledger.json"]


class TestTheResolverFallsBackInsteadOfRaising:
    """The resolver answers None for every reason it cannot produce a mover.

    Two routes reach None and they are not the same. A host with no ``WinDLL``
    at all leaves at the guard, which is the ordinary POSIX answer. A host that
    has ``WinDLL`` but cannot complete the lookup leaves through the handler.
    Both matter: the resolver runs on the write path, so a raise here would
    turn a durability gap into a failed write.

    ``test_a_healthy_lookup_still_produces_a_mover`` is the control. On POSIX
    the guard returns None for its own reason, so without it every assertion
    in this class would pass against a resolver that had been broken to
    return None unconditionally.
    """

    @staticmethod
    def _install(monkeypatch, win_dll):
        monkeypatch.setattr(oa.ctypes, "WinDLL", win_dll, raising=False)

    def test_a_healthy_lookup_still_produces_a_mover(self, monkeypatch):
        def load(name, use_last_error):
            return SimpleNamespace(MoveFileExW=Mover())

        self._install(monkeypatch, load)

        assert oa._win32_move_file_ex() is not None

    def test_an_unloadable_kernel32_is_not_raised_at_the_caller(self, monkeypatch):
        def refuse(name, use_last_error):
            raise OSError("kernel32 not found")

        self._install(monkeypatch, refuse)

        assert oa._win32_move_file_ex() is None

    def test_a_kernel32_without_the_entry_point_is_not_raised_either(self, monkeypatch):
        self._install(monkeypatch, lambda name, use_last_error: SimpleNamespace())

        assert oa._win32_move_file_ex() is None


@pytest.mark.skipif(not ON_WINDOWS, reason="exercises the real Win32 MoveFileExW")
class TestOnRealWindows:
    """The only tests that run the shipped ctypes path.

    Power loss is not injectable here, so these do not prove durability. They
    prove the call is reachable, correctly bound, and correct about the bytes,
    which is the half that a stand-in cannot check. The durability half rests
    on Microsoft's documented meaning of the flag, the same standard the POSIX
    side takes from fsync.
    """

    def test_the_win32_entry_point_resolves(self):
        assert oa._win32_move_file_ex() is not None

    def test_a_real_write_through_move_publishes_the_content(self, tmp_path):
        source, destination = _pair(tmp_path)
        oa._durable_replace(source, destination)
        assert destination.read_text(encoding="utf-8") == "new"
        assert not source.exists()

    def test_write_atomic_round_trips_over_the_real_call(self, tmp_path):
        target = tmp_path / "ledger.json"
        oa._write_atomic(target, '{"n": 1}')
        oa._write_atomic(target, '{"n": 2}')
        assert target.read_text(encoding="utf-8") == '{"n": 2}'
        assert [p.name for p in tmp_path.iterdir()] == ["ledger.json"]
