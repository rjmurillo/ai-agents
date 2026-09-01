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


def _raise(exc: BaseException):
    def _fake_run(*_args, **_kwargs):
        raise exc

    return _fake_run


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
