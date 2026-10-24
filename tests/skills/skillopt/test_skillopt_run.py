"""Tests for `skillopt.py run` results and verdicts (issue 6655 gap 1)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

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
)

pytestmark = pytest.mark.usefixtures("python_on_path")


class TestRunResults:
    def test_writes_booleans_for_pass_and_fail(self, tmp_path: Path, capsys: Capture) -> None:
        bundle = bundle_of(tmp_path)
        eval_path = make_eval(
            tmp_path,
            {
                "ok": task(py("pass")),
                "bad": task(py("import sys; sys.exit(3)")),
            },
        )
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle, out)) == 0
        assert results_of(out) == {"ok": True, "bad": False}
        summary = json.loads(capsys.readouterr().out)
        assert (summary["passed"], summary["failed"], summary["unverified"]) == (1, 1, [])
        assert summary["tasks"]["bad"]["reason"] == "exit 3, expected 0"

    @pytest.mark.parametrize("role", ["incumbent", "candidate", "null"])
    def test_role_names_the_results_file(self, tmp_path: Path, role: str) -> None:
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out, role)) == 0
        assert results_of(out, role) == {"a": True}
        assert [p.name for p in out.iterdir()] == [f"{role}_results.json"]

    def test_unknown_role_is_a_usage_error(self, tmp_path: Path) -> None:
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        with pytest.raises(SystemExit) as exc:
            skillopt.main(run_argv(eval_path, bundle_of(tmp_path), tmp_path / "o", "winner"))
        assert exc.value.code == 2

    def test_expect_exit_nonzero_passes_on_match(self, tmp_path: Path) -> None:
        eval_path = make_eval(tmp_path, {"a": task(py("import sys; sys.exit(4)"), expect_exit=4)})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": True}

    def test_expect_stdout_match_and_trailing_newline_ignored(self, tmp_path: Path) -> None:
        eval_path = make_eval(
            tmp_path,
            {
                "a": task(py("print('hello')"), expect_stdout="hello"),
                "b": task(py("print('hello')"), expect_stdout="hello\n"),
                "c": task(py("print('hello')"), expect_stdout="hell"),
                "d": task(py("print(' hello')"), expect_stdout="hello"),
            },
        )
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": True, "b": True, "c": False, "d": False}

    def test_expect_stdout_alone_still_checks_exit_zero(self, tmp_path: Path) -> None:
        code = "import sys; print('hello'); sys.exit(1)"
        eval_path = make_eval(tmp_path, {"a": task(py(code), expect_stdout="hello")})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": False}

    def test_both_expectations_must_hold(self, tmp_path: Path) -> None:
        eval_path = make_eval(
            tmp_path,
            {"a": task(py("print('x')"), expect_exit=0, expect_stdout="y")},
        )
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": False}

    def test_cwd_is_the_bundle_root(self, tmp_path: Path) -> None:
        bundle = bundle_of(tmp_path)
        code = "import os; print(os.path.realpath(os.getcwd()))"
        eval_path = make_eval(tmp_path, {"a": task(py(code), expect_stdout=str(bundle.resolve()))})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle, out)) == 0
        assert results_of(out) == {"a": True}

    def test_relative_script_runs_from_the_bundle(self, tmp_path: Path) -> None:
        bundle = bundle_of(tmp_path)
        (bundle / "scripts").mkdir()
        (bundle / "scripts" / "audit.py").write_text("print('audited')\n", encoding="utf-8")
        eval_path = make_eval(
            tmp_path, {"a": task([PY, "scripts/audit.py"], expect_stdout="audited")}
        )
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle, out)) == 0
        assert results_of(out) == {"a": True}

    def test_program_inside_bundle_resolved_by_relative_path(self, tmp_path: Path) -> None:
        if os.name != "posix":
            pytest.skip("shebang scripts")
        bundle = bundle_of(tmp_path)
        tool = bundle / "tool.sh"
        tool.write_text(f"#!{sys.executable}\nprint('tool ran')\n", encoding="utf-8")
        tool.chmod(0o755)
        eval_path = make_eval(tmp_path, {"a": task(["./tool.sh"], expect_stdout="tool ran")})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle, out)) == 0
        assert results_of(out) == {"a": True}

    def test_summary_carries_the_bundle_digest(self, tmp_path: Path, capsys: Capture) -> None:
        bundle = bundle_of(tmp_path)
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        assert skillopt.main(run_argv(eval_path, bundle, tmp_path / "o")) == 0
        summary = json.loads(capsys.readouterr().out)
        assert summary["bundle_sha256"] == skillopt.bundle_sha256(bundle)

    def test_split_flag_limits_the_run(self, tmp_path: Path) -> None:
        eval_path = make_eval(
            tmp_path,
            {"t1": task(py("pass")), "s1": task(py("pass"))},
            train=["t1"],
            sel=["s1"],
        )
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out, "incumbent")) == 0
        assert results_of(out) == {"t1": True, "s1": True}
        out2 = tmp_path / "out2"
        argv = run_argv(eval_path, bundle_of(tmp_path, "b2"), out2, "incumbent", "--split", "sel")
        assert skillopt.main(argv) == 0
        assert results_of(out2) == {"s1": True}

    def test_unknown_split_exits_two(self, tmp_path: Path) -> None:
        eval_path = make_eval(tmp_path, {"a": task(py("pass"))})
        argv = run_argv(eval_path, bundle_of(tmp_path), tmp_path / "o", "incumbent", "--split", "x")
        assert skillopt.main(argv) == 2

    def test_task_without_command_is_skipped_not_passed(
        self, tmp_path: Path, capsys: Capture
    ) -> None:
        eval_path = make_eval(
            tmp_path,
            {"a": task(py("pass")), "sem": {"prompt": "p", "verifier": "v", "kind": "semantic"}},
        )
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": True}
        assert json.loads(capsys.readouterr().out)["skipped_no_command"] == ["sem"]

    def test_no_command_in_scope_exits_two(self, tmp_path: Path) -> None:
        eval_path = make_eval(tmp_path, {"sem": {"prompt": "p", "verifier": "v"}})
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), tmp_path / "o")) == 2

    def test_verifier_fields_without_command_exit_two(self, tmp_path: Path) -> None:
        eval_path = make_eval(tmp_path, {"a": task(py("pass")), "b": {"expect_exit": 0}})
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), tmp_path / "o")) == 2

    def test_results_feed_pair_gate_end_to_end(self, tmp_path: Path, capsys: Capture) -> None:
        old = bundle_of(tmp_path, "old")
        new = bundle_of(tmp_path, "new")
        (old / "check.py").write_text("print('old')\n", encoding="utf-8")
        (new / "check.py").write_text("print('new')\n", encoding="utf-8")
        eval_path = make_eval(
            tmp_path,
            {
                "s1": task([PY, "check.py"], expect_stdout="new"),
                "s2": task(py("pass")),
            },
        )
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, old, out, "incumbent")) == 0
        assert skillopt.main(run_argv(eval_path, new, out, "candidate")) == 0
        capsys.readouterr()
        gate = [
            "pair-gate",
            "--eval",
            str(eval_path),
            "--incumbent-results",
            str(out / "incumbent_results.json"),
            "--candidate-results",
            str(out / "candidate_results.json"),
        ]
        assert skillopt.main(gate) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["verdict"] == "ACCEPT_PARETO"
        assert report["gains"] == ["s1"]


class TestRunUnverified:
    def test_timeout_is_unverified_and_exit_one(self, tmp_path: Path, capsys: Capture) -> None:
        eval_path = make_eval(
            tmp_path,
            {"slow": task(py("import time; time.sleep(30)"), timeout=0.5), "ok": task(py("pass"))},
        )
        out = tmp_path / "out"
        started = time.monotonic()
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 1
        assert time.monotonic() - started < 20
        assert results_of(out) == {"slow": "UNVERIFIED", "ok": True}
        summary = json.loads(capsys.readouterr().out)
        assert summary["unverified"] == ["slow"]
        assert "timed out" in summary["tasks"]["slow"]["reason"]

    def test_missing_binary_is_unverified(self, tmp_path: Path) -> None:
        eval_path = make_eval(tmp_path, {"a": task(["definitely-not-a-real-binary-6655"])})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 1
        assert results_of(out) == {"a": "UNVERIFIED"}

    def test_slow_grandchild_is_killed_when_the_task_times_out(self, tmp_path: Path) -> None:
        if os.name != "posix":
            pytest.skip("process groups")
        marker = tmp_path / "grandchild-survived.txt"
        child = f"import time; time.sleep(3); open({str(marker)!r}, 'w').write('x')"
        code = (
            "import subprocess, sys, time; "
            f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(60)"
        )
        eval_path = make_eval(tmp_path, {"a": task(py(code), timeout=1)})
        out = tmp_path / "out"
        started = time.monotonic()
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 1
        assert time.monotonic() - started < 30
        assert results_of(out) == {"a": "UNVERIFIED"}
        time.sleep(4)
        assert not marker.exists()

    def test_orphan_left_by_a_finished_task_is_killed(self, tmp_path: Path) -> None:
        if os.name != "posix":
            pytest.skip("process groups")
        marker = tmp_path / "orphan-survived.txt"
        child = f"import time; time.sleep(3); open({str(marker)!r}, 'w').write('x')"
        code = f"import subprocess, sys; subprocess.Popen([sys.executable, '-c', {child!r}])"
        eval_path = make_eval(tmp_path, {"a": task(py(code))})
        out = tmp_path / "out"
        assert skillopt.main(run_argv(eval_path, bundle_of(tmp_path), out)) == 0
        assert results_of(out) == {"a": True}
        time.sleep(4)
        assert not marker.exists()
