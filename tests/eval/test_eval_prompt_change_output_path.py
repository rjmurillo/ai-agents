"""The runner checks `--output` before it spends a model call.

A missing parent folder is created. A path that cannot be written exits 2
with a one-line error, in a full run and in `--dry-run`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
_added = str(EVAL_DIR) not in sys.path
if _added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    _spec = importlib.util.spec_from_file_location(
        "epc_output_path", EVAL_DIR / "eval-prompt-change.py"
    )
    assert _spec and _spec.loader
    ev = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ev)
finally:
    if _added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


class _Calls:
    """Counts the stubbed model, credential, and model-availability calls."""

    def __init__(self) -> None:
        self.api = 0
        self.key = 0
        self.verify = 0

    def spent(self) -> tuple[int, int, int]:
        return (self.api, self.key, self.verify)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> _Calls:
    """Stub the credential and the model call, and count both."""
    counter = _Calls()

    def fake_key(*_a: Any, **_kw: Any) -> str:
        counter.key += 1
        return "test-key"

    def fake_call(*_a: Any, **_kw: Any) -> str:
        counter.api += 1
        return '{"verdict": "ROUTE", "reason": "ok"}'

    def fake_verify(*_a: Any, **_kw: Any) -> None:
        counter.verify += 1

    monkeypatch.setattr(ev, "load_api_key_for_selected_provider", fake_key)
    monkeypatch.setattr(ev, "verify_model_available", fake_verify)
    monkeypatch.setattr(ev, "call_api", fake_call)
    monkeypatch.setattr(ev.time, "sleep", lambda _s: None)
    return counter


@pytest.fixture
def inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Valid before, after, and scenario files; the cwd is `tmp_path`."""
    monkeypatch.chdir(tmp_path)
    scenarios = tmp_path / "s.json"
    scenarios.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "id": "S1",
                        "desc": "d",
                        "input": "i",
                        "expected_verdict": "ROUTE",
                        "verdict_options": ["ROUTE", "DELEGATE"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    before = tmp_path / "a.md"
    before.write_text("p", encoding="utf-8")
    after = tmp_path / "b.md"
    after.write_text("p", encoding="utf-8")
    return ["prog", "--before", str(before), "--after", str(after), "--scenarios", str(scenarios)]


def _symlink_or_skip(link: Path, target: Path) -> None:
    """Create *link*, or skip where the platform refuses symlinks."""
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable here: {exc}")


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        ev.main()
    code = exc.value.code
    assert isinstance(code, int)
    return code


class TestMissingParentIsCreated:
    def test_full_run_creates_nested_parent_and_writes_results(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Calls, inputs: list[str]
    ) -> None:
        out = tmp_path / "evals" / "skill-rewrites" / "new-skill" / "results.json"
        assert not (tmp_path / "evals").exists()

        assert _run(monkeypatch, [*inputs, "--output", str(out)]) == 0

        result = json.loads(out.read_text(encoding="utf-8"))
        assert result["gate"]["verdict"] == "PASS"
        assert calls.api > 0

    def test_relative_nested_output_is_created_under_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Calls, inputs: list[str]
    ) -> None:
        assert not (tmp_path / "nested").exists()

        assert _run(monkeypatch, [*inputs, "--output", "nested/deep/results.json"]) == 0

        assert (tmp_path / "nested" / "deep" / "results.json").is_file()

    def test_dry_run_creates_parent_but_not_the_results_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Calls, inputs: list[str]
    ) -> None:
        out = tmp_path / "evals" / "new-skill" / "results.json"
        assert not (tmp_path / "evals").exists()

        assert _run(monkeypatch, [*inputs, "--dry-run", "--output", str(out)]) == 0

        assert out.parent.is_dir()
        assert not out.exists()
        assert calls.spent() == (0, 0, 0)

    def test_results_shape_matches_a_run_into_an_existing_folder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Calls, inputs: list[str]
    ) -> None:
        existing = tmp_path / "existing.json"
        created = tmp_path / "made" / "here" / "results.json"
        assert not (tmp_path / "made").exists()

        assert _run(monkeypatch, [*inputs, "--output", str(existing)]) == 0
        assert _run(monkeypatch, [*inputs, "--output", str(created)]) == 0

        first = json.loads(existing.read_text(encoding="utf-8"))
        second = json.loads(created.read_text(encoding="utf-8"))
        assert first == second


class TestUnwritableOutputFailsBeforeAnyCall:
    @pytest.mark.parametrize("dry_run", [False, True], ids=["full-run", "dry-run"])
    @pytest.mark.parametrize(
        "relative",
        ["blocker/results.json", "blocker/deeper/results.json"],
        ids=["parent-is-file", "ancestor-is-file"],
    )
    def test_file_in_the_parent_chain_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        calls: _Calls,
        inputs: list[str],
        dry_run: bool,
        relative: str,
    ) -> None:
        blocker = tmp_path / "blocker"
        blocker.write_text("not a folder", encoding="utf-8")
        out = tmp_path / relative
        argv = [*inputs, "--output", str(out), *(["--dry-run"] if dry_run else [])]

        assert _run(monkeypatch, argv) == 2

        captured = capsys.readouterr()
        assert "ERROR:" in captured.err
        assert str(out) in captured.err
        assert "Traceback" not in captured.err
        assert captured.out == ""
        assert calls.spent() == (0, 0, 0)
        assert blocker.read_text(encoding="utf-8") == "not a folder"

    @pytest.mark.parametrize("dry_run", [False, True], ids=["full-run", "dry-run"])
    def test_output_that_is_a_folder_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        calls: _Calls,
        inputs: list[str],
        dry_run: bool,
    ) -> None:
        out = tmp_path / "results"
        out.mkdir()
        argv = [*inputs, "--output", str(out), *(["--dry-run"] if dry_run else [])]

        assert _run(monkeypatch, argv) == 2

        assert "is a folder" in capsys.readouterr().err
        assert calls.spent() == (0, 0, 0)

    @pytest.mark.parametrize("dry_run", [False, True], ids=["full-run", "dry-run"])
    @pytest.mark.parametrize("target_exists", [False, True], ids=["new-file", "existing-file"])
    def test_no_write_permission_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        calls: _Calls,
        inputs: list[str],
        dry_run: bool,
        target_exists: bool,
    ) -> None:
        out = tmp_path / "locked" / "results.json"
        out.parent.mkdir()
        if target_exists:
            out.write_text("{}", encoding="utf-8")
        # The file when it exists, else the folder that would hold it. A chmod
        # would not deny root, so the permission answer is stubbed.
        denied = out if target_exists else out.parent
        real_access = os.access

        def fake_access(path: Any, mode: int, **kw: Any) -> bool:
            if Path(path) == denied and mode & os.W_OK:
                return False
            return real_access(path, mode, **kw)

        monkeypatch.setattr(ev.os, "access", fake_access)
        argv = [*inputs, "--output", str(out), *(["--dry-run"] if dry_run else [])]

        assert _run(monkeypatch, argv) == 2

        assert "not writable" in capsys.readouterr().err
        assert calls.spent() == (0, 0, 0)

    @pytest.mark.parametrize("dry_run", [False, True], ids=["full-run", "dry-run"])
    @pytest.mark.parametrize("target_exists", [False, True], ids=["new-file", "existing-file"])
    def test_folder_without_search_permission_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        calls: _Calls,
        inputs: list[str],
        dry_run: bool,
        target_exists: bool,
    ) -> None:
        out = tmp_path / "nosearch" / "results.json"
        out.parent.mkdir()
        if target_exists:
            out.write_text("{}", encoding="utf-8")
        real_access = os.access

        # Mode 0666 on the folder: writable, but no entry in it can be reached.
        def fake_access(path: Any, mode: int, **kw: Any) -> bool:
            if Path(path) == out.parent and mode & os.X_OK:
                return False
            return real_access(path, mode, **kw)

        monkeypatch.setattr(ev.os, "access", fake_access)
        argv = [*inputs, "--output", str(out), *(["--dry-run"] if dry_run else [])]

        assert _run(monkeypatch, argv) == 2

        assert "no search access" in capsys.readouterr().err
        assert calls.spent() == (0, 0, 0)

    @pytest.mark.parametrize("dry_run", [False, True], ids=["full-run", "dry-run"])
    def test_dangling_symlink_into_a_blocked_folder_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        calls: _Calls,
        inputs: list[str],
        dry_run: bool,
    ) -> None:
        blocker = tmp_path / "blocker"
        blocker.write_text("not a folder", encoding="utf-8")
        link = tmp_path / "results.json"
        _symlink_or_skip(link, blocker / "real.json")
        argv = [*inputs, "--output", str(link), *(["--dry-run"] if dry_run else [])]

        assert _run(monkeypatch, argv) == 2

        assert "cannot create folder" in capsys.readouterr().err
        assert calls.spent() == (0, 0, 0)

    def test_bad_scenarios_file_leaves_no_output_folder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Calls, inputs: list[str]
    ) -> None:
        out = tmp_path / "never" / "results.json"
        argv = [*inputs[:5], "--scenarios", str(tmp_path / "missing.json"), "--output", str(out)]

        assert _run(monkeypatch, argv) == 2

        assert not out.parent.exists()


class TestSymlinkedOutput:
    def test_dangling_symlink_gets_its_destination_folder_and_results(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Calls, inputs: list[str]
    ) -> None:
        destination = tmp_path / "elsewhere" / "deep" / "real.json"
        link = tmp_path / "results.json"
        _symlink_or_skip(link, destination)
        assert not (tmp_path / "elsewhere").exists()

        assert _run(monkeypatch, [*inputs, "--output", str(link)]) == 0

        assert link.is_symlink()
        assert json.loads(destination.read_text(encoding="utf-8"))["gate"]["verdict"] == "PASS"

    def test_symlink_to_an_existing_file_is_written_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Calls, inputs: list[str]
    ) -> None:
        destination = tmp_path / "real.json"
        destination.write_text("stale", encoding="utf-8")
        link = tmp_path / "results.json"
        _symlink_or_skip(link, destination)

        assert _run(monkeypatch, [*inputs, "--output", str(link)]) == 0

        assert link.is_symlink()
        assert json.loads(destination.read_text(encoding="utf-8"))["eval_type"] == "prompt-change"


class TestExistingBehaviorUnchanged:
    def test_bare_filename_writes_into_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Calls, inputs: list[str]
    ) -> None:
        assert _run(monkeypatch, [*inputs, "--output", "results.json"]) == 0

        assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))["gate"]

    def test_existing_results_file_is_overwritten_by_a_full_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Calls, inputs: list[str]
    ) -> None:
        out = tmp_path / "results.json"
        out.write_text("stale", encoding="utf-8")

        assert _run(monkeypatch, [*inputs, "--output", str(out)]) == 0

        assert json.loads(out.read_text(encoding="utf-8"))["eval_type"] == "prompt-change"

    def test_dry_run_leaves_an_existing_results_file_byte_identical(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, calls: _Calls, inputs: list[str]
    ) -> None:
        out = tmp_path / "kept" / "results.json"
        out.parent.mkdir()
        out.write_bytes(b'{"committed": true}\n')

        assert _run(monkeypatch, [*inputs, "--dry-run", "--output", str(out)]) == 0

        assert out.read_bytes() == b'{"committed": true}\n'

    def test_no_output_flag_prints_results_and_creates_nothing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        calls: _Calls,
        inputs: list[str],
    ) -> None:
        before = sorted(p.name for p in tmp_path.iterdir())

        assert _run(monkeypatch, inputs) == 0

        assert json.loads(capsys.readouterr().out)["gate"]["verdict"] == "PASS"
        assert sorted(p.name for p in tmp_path.iterdir()) == before


class TestPrepareOutputPath:
    def test_none_and_empty_are_no_ops(self) -> None:
        ev.prepare_output_path(None)
        ev.prepare_output_path("")

    def test_mkdir_failure_is_reported_as_a_runtime_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(self: Path, *_a: Any, **_kw: Any) -> None:
            raise PermissionError(13, "Permission denied", str(self))

        monkeypatch.setattr(Path, "mkdir", boom)
        out = tmp_path / "nope" / "results.json"

        with pytest.raises(RuntimeError, match="cannot create folder") as exc:
            ev.prepare_output_path(str(out))

        assert str(out) in str(exc.value)
