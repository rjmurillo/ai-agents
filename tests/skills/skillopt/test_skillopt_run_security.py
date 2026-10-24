"""Tests for `skillopt.py run` refusals and isolation (issue 6655 gap 1 security)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest
import skillopt
from skillopt_helpers import (
    PY,
    Capture,
    bundle_of,
    make_eval,
    py,
    results_of,
    run_argv,
    task,
    write_json,
)

pytestmark = pytest.mark.usefixtures("python_on_path")


class TestRunRefusals:
    """Every refusal exits 2 before any command runs and writes no results."""

    @staticmethod
    def refused(tmp_path: Path, tasks: dict[str, Any], capsys: Capture) -> str:
        sentinel = tmp_path / "ran.txt"
        tasks = {"first": task(py(f"open({str(sentinel)!r}, 'w').write('x')")), **tasks}
        eval_path = make_eval(tmp_path, tasks)
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 2
        assert not sentinel.exists(), "a valid task ran before validation finished"
        assert not out.exists()
        return capsys.readouterr().err

    @pytest.mark.parametrize(
        "command",
        ["python3 -c 'print(1)'", "echo hi; touch pwned", None, 7, {"argv": ["a"]}],
    )
    def test_non_list_command(self, tmp_path: Path, capsys: Capture, command: object) -> None:
        err = self.refused(tmp_path, {"bad": task(command)}, capsys)
        assert "command must be an argv list" in err

    def test_empty_list_command(self, tmp_path: Path, capsys: Capture) -> None:
        assert "command is empty" in self.refused(tmp_path, {"bad": task([])}, capsys)

    @pytest.mark.parametrize("part", [1, None, ["nested"], True])
    def test_non_string_argv_entry(self, tmp_path: Path, capsys: Capture, part: object) -> None:
        err = self.refused(tmp_path, {"bad": task([PY, part])}, capsys)
        assert "command[1] must be a string" in err

    def test_empty_program(self, tmp_path: Path, capsys: Capture) -> None:
        assert "command[0] is empty" in self.refused(tmp_path, {"bad": task([""])}, capsys)

    def test_nul_byte(self, tmp_path: Path, capsys: Capture) -> None:
        err = self.refused(tmp_path, {"bad": task([PY, "a\0b"])}, capsys)
        assert "NUL" in err

    def test_missing_timeout(self, tmp_path: Path, capsys: Capture) -> None:
        bad = {"command": py("pass"), "expect_exit": 0}
        assert "timeout is required" in self.refused(tmp_path, {"bad": bad}, capsys)

    @pytest.mark.parametrize("value", [0, -1, 601, 1e9, "30", True, None])
    def test_bad_timeout(self, tmp_path: Path, capsys: Capture, value: object) -> None:
        err = self.refused(tmp_path, {"bad": task(py("pass"), timeout=value)}, capsys)
        assert "timeout must be" in err

    def test_timeout_at_the_limit_is_accepted(self, tmp_path: Path) -> None:
        eval_path = make_eval(tmp_path, {"a": task(py("pass"), timeout=600)})
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), tmp_path / "o")) == 0

    def test_no_expectation(self, tmp_path: Path, capsys: Capture) -> None:
        bad = {"command": py("pass"), "timeout": 5}
        assert "needs expect_exit or expect_stdout" in self.refused(tmp_path, {"bad": bad}, capsys)

    @pytest.mark.parametrize("value", ["0", 0.5, True, None])
    def test_bad_expect_exit(self, tmp_path: Path, capsys: Capture, value: object) -> None:
        err = self.refused(tmp_path, {"bad": task(py("pass"), expect_exit=value)}, capsys)
        assert "expect_exit must be an integer" in err

    @pytest.mark.parametrize("value", [1, None, ["x"]])
    def test_bad_expect_stdout(self, tmp_path: Path, capsys: Capture, value: object) -> None:
        err = self.refused(tmp_path, {"bad": task(py("pass"), expect_stdout=value)}, capsys)
        assert "expect_stdout must be a string" in err

    @pytest.mark.parametrize(
        "argument",
        [
            "/etc/passwd",
            "\\windows\\system32",
            "C:\\Users\\x",
            "C:/Users/x",
            "../secret",
            "a/../../secret",
            "a\\..\\secret",
            "..",
            "--config=/etc/passwd",
            "--config=../secret",
            "-I/etc",
            "-L../lib",
            "of=/home/u/.ssh/x",
            "key=a=/etc",
        ],
    )
    def test_path_escape_in_argument(self, tmp_path: Path, capsys: Capture, argument: str) -> None:
        err = self.refused(tmp_path, {"bad": task([PY, argument])}, capsys)
        assert "command[1]" in err
        assert "absolute path" in err or "'..'" in err

    @pytest.mark.parametrize("program", ["../tool", "/bin/sh", "sub/../../tool", "C:\\tool.exe"])
    def test_path_escape_in_program(self, tmp_path: Path, capsys: Capture, program: str) -> None:
        err = self.refused(tmp_path, {"bad": task([program])}, capsys)
        assert "command[0]" in err

    def test_program_symlink_leaving_the_bundle(self, tmp_path: Path) -> None:
        bundle = bundle_of(tmp_path)
        outside = tmp_path / "outside-tool"
        outside.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        try:
            (bundle / "tool").symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
        eval_path = make_eval(tmp_path, {"a": task(["./tool"])})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle, out)) == 2

    def test_bundle_must_be_a_real_directory(self, tmp_path: Path) -> None:
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        assert skillopt.main(run_argv(eval_path, tmp_path / "nope", tmp_path / "o")) == 2
        a_file = tmp_path / "file"
        a_file.write_text("x", encoding="utf-8")
        assert skillopt.main(run_argv(eval_path, a_file, tmp_path / "o")) == 2

    def test_symlinked_bundle_root_is_refused(self, tmp_path: Path) -> None:
        real = bundle_of(tmp_path, "real")
        link = tmp_path / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        assert skillopt.main(run_argv(eval_path, link, tmp_path / "o")) == 2

    def test_out_dir_may_contain_the_bundle(self, tmp_path: Path) -> None:
        bundle = bundle_of(tmp_path)
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        assert skillopt.main(run_argv(eval_path, bundle, tmp_path)) == 0
        assert results_of(tmp_path) == {"a": True}

    def test_out_dir_equal_to_bundle_is_refused(self, tmp_path: Path) -> None:
        bundle = bundle_of(tmp_path)
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        assert skillopt.main(run_argv(eval_path, bundle, bundle)) == 2
        assert not (bundle / "incumbent_results.json").exists()

    def test_out_dir_inside_bundle(self, tmp_path: Path, capsys: Capture) -> None:
        bundle = bundle_of(tmp_path)
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        assert skillopt.main(run_argv(eval_path, bundle, bundle / "results")) == 2
        assert "--out-dir" in capsys.readouterr().err
        assert not (bundle / "results").exists()

    def test_bundle_with_symlink_is_refused(self, tmp_path: Path) -> None:
        bundle = bundle_of(tmp_path)
        outside = tmp_path / "outside.txt"
        outside.write_text("x", encoding="utf-8")
        try:
            (bundle / "link.txt").symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        assert skillopt.main(run_argv(eval_path, bundle, tmp_path / "o")) == 2

    def test_task_that_edits_the_bundle_fails_the_run(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        bundle = bundle_of(tmp_path)
        eval_path = make_eval(tmp_path, {"a": task(py("open('added.txt', 'w').write('x')"))})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle, out)) == 2
        assert "bundle changed" in capsys.readouterr().err
        assert not out.exists()

    def test_mutation_is_attributed_to_the_task_that_made_it(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        bundle = bundle_of(tmp_path)
        eval_path = make_eval(
            tmp_path,
            {
                "clean": task(py("pass")),
                "dirty": task(py("open('added.txt', 'w').write('x')")),
                "later": task(py("pass")),
            },
        )
        assert skillopt.main(run_argv(eval_path, bundle, tmp_path / "out")) == 2
        assert "task dirty" in capsys.readouterr().err

    def test_eval_must_be_an_object(self, tmp_path: Path) -> None:
        eval_path = write_json(tmp_path / "eval.json", [1])
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), tmp_path / "o")) == 2

    def test_task_entry_must_be_an_object(self, tmp_path: Path) -> None:
        eval_path = make_eval(tmp_path, {"a": "echo hi"})
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), tmp_path / "o")) == 2


class TestRunIsolation:
    def test_no_shell_interpretation_of_arguments(self, tmp_path: Path) -> None:
        bundle = bundle_of(tmp_path)
        payload = "$HOME; touch pwned.txt `touch pwned2.txt` | cat *"
        eval_path = make_eval(
            tmp_path,
            {"a": task(py("import sys; print(sys.argv[1])", payload), expect_stdout=payload)},
        )
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle, out)) == 0
        assert results_of(out) == {"a": True}
        assert not (bundle / "pwned.txt").exists()
        assert not (bundle / "pwned2.txt").exists()

    def test_environment_is_reduced_to_the_allowlist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SKILLOPT_TEST_TOKEN", "hunter2")
        code = "import os; print(os.environ.get('SKILLOPT_TEST_TOKEN', 'absent'))"
        eval_path = make_eval(tmp_path, {"a": task(py(code), expect_stdout="absent")})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": True}

    def test_stale_bytecode_in_the_bundle_is_not_loaded(self, tmp_path: Path) -> None:
        import importlib.util
        import py_compile

        bundle = bundle_of(tmp_path)
        module = bundle / "mod.py"
        module.write_text("VALUE = 'stale'\n", encoding="utf-8")
        pyc = Path(importlib.util.cache_from_source(str(module)))
        py_compile.compile(
            str(module),
            cfile=str(pyc),
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
        )
        module.write_text("VALUE = 'fresh'\n", encoding="utf-8")
        (bundle / "main.py").write_text("import mod\nprint(mod.VALUE)\n", encoding="utf-8")
        eval_path = make_eval(tmp_path, {"a": task([PY, "main.py"], expect_stdout="fresh")})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle, out)) == 0
        assert results_of(out) == {"a": True}

    def test_oversized_stdout_fails_the_task_without_buffering_it(self, tmp_path: Path) -> None:
        code = "import sys; sys.stdout.write('x' * (2 * 1024 * 1024))"
        eval_path = make_eval(tmp_path, {"a": task(py(code), expect_stdout="x")})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": False}

    def test_runaway_writer_is_killed_at_the_output_cap(self, tmp_path: Path) -> None:
        code = "import sys\nwhile True:\n    sys.stdout.write('x' * 65536)\n    sys.stdout.flush()"
        eval_path = make_eval(tmp_path, {"a": task(py(code), timeout=60)})
        out = tmp_path / "out"
        started = time.monotonic()
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert time.monotonic() - started < 30
        assert results_of(out) == {"a": False}

    def test_fast_writer_that_exits_before_the_next_poll_still_fails(self, tmp_path: Path) -> None:
        code = "import sys; sys.stdout.write('x' * (4 * 1024 * 1024))"
        tasks = {f"a{i}": task(py(code)) for i in range(5)}
        eval_path = make_eval(tmp_path, tasks)
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {f"a{i}": False for i in range(5)}

    def test_output_at_the_cap_is_accepted(self, tmp_path: Path) -> None:
        code = "import sys; sys.stdout.write('x' * 1024 * 1024)"
        eval_path = make_eval(tmp_path, {"a": task(py(code))})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": True}

    def test_relative_and_empty_path_entries_do_not_reach_the_task(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        if os.name != "posix":
            pytest.skip("POSIX PATH search")
        bundle = bundle_of(tmp_path)
        planted = bundle / "bundletool"
        planted.write_text(f"#!{sys.executable}\nprint('planted ran')\n", encoding="utf-8")
        planted.chmod(0o755)
        path = os.environ["PATH"]
        for prefix in (".", "", "bin"):
            monkeypatch.setenv("PATH", prefix + os.pathsep + path)
            eval_path = make_eval(
                tmp_path, {"a": task(["bundletool"], expect_stdout="planted ran")}
            )
            out = tmp_path / f"out-{prefix or 'empty'}"
            assert skillopt.main(run_argv(eval_path, bundle, out)) == 1
            assert results_of(out) == {"a": "UNVERIFIED"}

    def test_written_results_file_is_replaced_atomically(self, tmp_path: Path) -> None:
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        out = tmp_path / "out"
        out.mkdir()
        stale = out / "incumbent_results.json"
        stale.write_text('{"a": false}', encoding="utf-8")
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": True}
        assert [p.name for p in out.iterdir()] == ["incumbent_results.json"]

    def test_python_does_not_write_bytecode_into_the_bundle(self, tmp_path: Path) -> None:
        bundle = bundle_of(tmp_path)
        (bundle / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
        (bundle / "main.py").write_text("import mod\nprint(mod.VALUE)\n", encoding="utf-8")
        eval_path = make_eval(tmp_path, {"a": task([PY, "main.py"], expect_stdout="1")})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle, out)) == 0
        assert not (bundle / "__pycache__").exists()

    def test_stdin_is_closed(self, tmp_path: Path) -> None:
        code = "import sys; print(repr(sys.stdin.read()))"
        eval_path = make_eval(tmp_path, {"a": task(py(code), expect_stdout="''")})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": True}
