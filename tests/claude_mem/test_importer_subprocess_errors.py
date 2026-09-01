"""Which subprocess failures `_run_imports` absorbs, and which it lets through.

A separate module because this is its own seam: everything here is about the
boundary between a per-file import failure the loop reports and continues past,
and a fault that must reach the caller. `tests/claude_mem/test_importer_resolution.py`
owns path resolution and exit codes and is near the 500-line taste-lint ceiling.

The narrowing this pins was made in an earlier round and nothing proved it
mattered. Reverting `except OSError` to `except Exception` left the whole suite
green, so the fix was indistinguishable from the bug it replaced. These tests
close that: the loop must keep absorbing the OSError family, and must NOT absorb
anything else.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Import the module under test by file path since it lives outside scripts/.

_base = os.path.join(os.path.dirname(__file__), "..", "..", ".claude-mem", "scripts")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_base, filename))
    assert spec is not None, f"Failed to find {filename}"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None, f"Module spec for {filename} has no loader"
    # dataclasses resolves a class's module through sys.modules, so a module
    # executed without registration raises AttributeError at class creation.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_import_mem = _load("import_claude_mem_memories", "import_claude_mem_memories.py")


def _stage_one_memory(tmp_path: Path, monkeypatch) -> Path:
    """Create an importer and a single memory file, and point the module at them."""
    importer = tmp_path / "importer.ts"
    importer.write_text("// stub importer", encoding="utf-8")

    memories = tmp_path / "memories"
    memories.mkdir()
    (memories / "shared.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

    return importer


def _stage_two_memories(tmp_path: Path, monkeypatch) -> Path:
    """Same, with two memory files whose glob order is fixed by their names.

    `main` collects with `sorted(_MEMORIES_DIR.glob("*.json"))`, so the numeric
    prefixes decide which file the loop reaches first.
    """
    importer = tmp_path / "importer.ts"
    importer.write_text("// stub importer", encoding="utf-8")

    memories = tmp_path / "memories"
    memories.mkdir()
    (memories / "01-first.json").write_text("{}", encoding="utf-8")
    (memories / "02-second.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

    return importer


def _raise(exc: BaseException):
    def _fake_run(*_args, **_kwargs):
        raise exc

    return _fake_run


class _RecordingRun:
    """Records each argv and raises for the file names in `fail_on`."""

    def __init__(self, fail_on: set[str], exc: BaseException) -> None:
        self._fail_on = fail_on
        self._exc = exc
        self.attempted: list[str] = []

    def __call__(self, argv, **_kwargs):
        name = Path(argv[-1]).name
        self.attempted.append(name)
        if name in self._fail_on:
            raise self._exc
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class TestOnlyOsErrorsAreAbsorbedPerFile:
    """`except OSError` is the contract, and the narrowing has to be observable.

    An OSError from `subprocess.run` means this one file could not be handed to
    the importer: `npx` is missing, the executable bit is wrong, a pipe broke.
    That is a per-file outcome, so the loop records it and moves on, and `main`
    reports exit 1 at the end.

    Anything else is a fault in this process rather than a fact about one file.
    Swallowing it would turn a bug into a warning line, hide the traceback, and
    still exit 1, which reads identically to a missing `npx`. It must propagate.
    """

    @pytest.mark.parametrize(
        "exc",
        [
            FileNotFoundError("npx not on PATH"),
            PermissionError("importer is not executable"),
            BrokenPipeError("pipe closed"),
        ],
        ids=["missing-npx", "not-executable", "broken-pipe"],
    )
    def test_oserror_family_is_absorbed_and_reported_as_exit_1(
        self, exc: OSError, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        importer = _stage_one_memory(tmp_path, monkeypatch)
        monkeypatch.setattr(_import_mem.subprocess, "run", _raise(exc))

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 1
        assert "WARNING" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "exc",
        [
            RuntimeError("interpreter fault"),
            ValueError("bad argument built by this module"),
            TypeError("wrong argv shape"),
            MemoryError(),
        ],
        ids=["runtime", "value", "type", "memory"],
    )
    def test_non_oserror_propagates_uncaught(
        self, exc: Exception, tmp_path: Path, monkeypatch
    ) -> None:
        """The whole point of the narrowing. `except Exception` would fail this."""
        importer = _stage_one_memory(tmp_path, monkeypatch)
        monkeypatch.setattr(_import_mem.subprocess, "run", _raise(exc))

        with pytest.raises(type(exc)):
            _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

    def test_a_failed_file_does_not_stop_the_ones_after_it(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """`continue`, not `break`. Needs two files: with one, the two are identical.

        Every other test in this module stages a single memory file, so nothing
        distinguished absorbing a failure and moving on from absorbing it and
        abandoning the run. Measured before this test existed: changing the
        loop's `continue` to `break` left all 102 tests green.
        """
        importer = _stage_two_memories(tmp_path, monkeypatch)
        run = _RecordingRun({"01-first.json"}, OSError("npx vanished"))
        monkeypatch.setattr(_import_mem.subprocess, "run", run)

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert run.attempted == ["01-first.json", "02-second.json"]
        assert result == 1, "one file failed, so the run is a failure overall"
        out = capsys.readouterr().out
        assert "1 succeeded, 1 failed" in out
        assert "FAIL 01-first.json" in out

    def test_every_file_is_attempted_when_all_of_them_fail(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The loop absorbs each failure independently rather than stopping at the first."""
        importer = _stage_two_memories(tmp_path, monkeypatch)
        run = _RecordingRun(
            {"01-first.json", "02-second.json"}, PermissionError("not executable")
        )
        monkeypatch.setattr(_import_mem.subprocess, "run", run)

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert run.attempted == ["01-first.json", "02-second.json"]
        assert result == 1

    def test_a_propagating_fault_stops_the_run_before_the_next_file(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The mirror of the two above: a non-OSError must NOT continue.

        Absorbing it would let the loop carry on to the second file, which is the
        behavior the narrowing exists to prevent.
        """
        importer = _stage_two_memories(tmp_path, monkeypatch)
        run = _RecordingRun({"01-first.json"}, RuntimeError("interpreter fault"))
        monkeypatch.setattr(_import_mem.subprocess, "run", run)

        with pytest.raises(RuntimeError):
            _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert run.attempted == ["01-first.json"], "must not reach the second file"

    def test_a_propagating_fault_is_not_reported_as_a_per_file_warning(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Pins the observable difference, not just the exception type.

        Absorbing the fault would print a per-file WARNING and return 1, which is
        the same surface a missing `npx` produces. This asserts the loop never got
        that far, so the two cases stay distinguishable to a caller.
        """
        importer = _stage_one_memory(tmp_path, monkeypatch)
        monkeypatch.setattr(_import_mem.subprocess, "run", _raise(RuntimeError("boom")))

        with pytest.raises(RuntimeError):
            _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert "WARNING" not in capsys.readouterr().out
