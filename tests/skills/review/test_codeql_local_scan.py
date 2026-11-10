"""Tests for codeql_local_scan.py: every guard and every outcome of the local fallback.

The wrapper is a real Python script the test writes, so exit codes, stderr, the
environment, session leadership, and the timeout kill are observed, not assumed.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import codeql_local_scan as scan
import pytest
from codeql_repo_fixture import git, make_repo

HEAD = "a" * 40


def sarif(*results: dict) -> str:
    return json.dumps({"version": "2.1.0", "runs": [{"results": list(results)}]})


RESULT = {
    "ruleId": "py/path-injection",
    "locations": [
        {"physicalLocation": {"artifactLocation": {"uri": "src/a.py"}, "region": {"startLine": 4}}}
    ],
}


def install_codeql(root: Path, head: str = HEAD, cli: bool = True, cache: bool = True) -> None:
    (root / ".codeql" / "scripts").mkdir(parents=True, exist_ok=True)
    if cli:
        (root / ".codeql" / "cli").mkdir(parents=True, exist_ok=True)
        (root / ".codeql" / "cli" / "codeql").write_text("#!/bin/sh\n", encoding="utf-8")
    if cache:
        (root / ".codeql" / "db").mkdir(parents=True, exist_ok=True)
        meta = root / ".codeql" / "db" / ".cache-metadata.json"
        meta.write_text(json.dumps({"git_head": head}), encoding="utf-8")


def make_wrapper(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "wrapper.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def writing_wrapper(
    tmp_path: Path, exit_code: int, languages=("python",), doc=None, err=""
) -> Path:
    content = doc if doc is not None else sarif()
    return make_wrapper(
        tmp_path,
        f"""
        import pathlib, sys
        out = pathlib.Path(".codeql/results")
        out.mkdir(parents=True, exist_ok=True)
        for lang in {list(languages)!r}:
            (out / (lang + ".sarif")).write_text({content!r}, encoding="utf-8")
        sys.stderr.write({err!r})
        sys.exit({exit_code})
        """,
    )


@pytest.fixture
def root(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    install_codeql(work)
    return work


class TestEnvironment:
    def test_only_the_four_allowlisted_names_pass(self):
        source = {
            "PATH": "/bin",
            "HOME": "/h",
            "LANG": "C",
            "TMPDIR": "/t",
            "GH_TOKEN": "secret",
            "GITHUB_TOKEN": "secret",
            "CODEQL_RESULTS_PATH": "/elsewhere",
            "PYTHONPATH": "/evil",
        }
        assert scan.scan_environment(source) == {
            "PATH": "/bin",
            "HOME": "/h",
            "LANG": "C",
            "TMPDIR": "/t",
        }

    def test_an_unset_name_is_absent_not_empty(self):
        assert scan.scan_environment({"PATH": "/bin"}) == {"PATH": "/bin"}

    def test_the_child_process_sees_nothing_else(self, root, tmp_path, monkeypatch):
        monkeypatch.setenv("GH_TOKEN", "must-not-leak")
        monkeypatch.setenv("CODEQL_DATABASE_PATH", "/elsewhere")
        wrapper = make_wrapper(
            tmp_path,
            """
            import json, os, pathlib
            pathlib.Path("seen_env.json").write_text(json.dumps(sorted(os.environ)))
            """,
        )
        scan.run_wrapper(root, wrapper, ("python",))
        seen = set(json.loads((root / "seen_env.json").read_text(encoding="utf-8")))
        assert "GH_TOKEN" not in seen
        assert "CODEQL_DATABASE_PATH" not in seen
        assert seen <= set(scan.ENV_ALLOWLIST) | {"LC_CTYPE", "PWD", "SHLVL", "_"}


class TestRunWrapper:
    def test_passes_the_documented_arguments_in_order(self, root, tmp_path):
        wrapper = make_wrapper(
            tmp_path,
            """
            import json, pathlib, sys
            pathlib.Path("argv.json").write_text(json.dumps(sys.argv[1:]))
            """,
        )
        scan.run_wrapper(root, wrapper, ("actions", "python"))
        argv = json.loads((root / "argv.json").read_text(encoding="utf-8"))
        assert argv == ["--operation", "quick", "--ci", "--languages", "actions", "python"]

    def test_runs_from_the_repository_root(self, root, tmp_path):
        wrapper = make_wrapper(
            tmp_path, "import os, pathlib; pathlib.Path('cwd.txt').write_text(os.getcwd())"
        )
        scan.run_wrapper(root, wrapper, ("python",))
        assert Path((root / "cwd.txt").read_text(encoding="utf-8")).resolve() == root.resolve()

    def test_runs_in_its_own_session(self, root, tmp_path):
        wrapper = make_wrapper(
            tmp_path,
            "import os, pathlib\n"
            "pathlib.Path('sid.txt').write_text(f'{os.getsid(0)} {os.getpid()}')",
        )
        scan.run_wrapper(root, wrapper, ("python",))
        sid, pid = (root / "sid.txt").read_text(encoding="utf-8").split()
        assert sid == pid

    def test_returns_exit_code_and_stderr(self, root, tmp_path):
        wrapper = make_wrapper(tmp_path, "import sys; sys.stderr.write('[SKIP] x'); sys.exit(1)")
        assert scan.run_wrapper(root, wrapper, ("python",)) == (1, "[SKIP] x")

    def test_a_signal_death_is_a_negative_code(self, root, tmp_path):
        wrapper = make_wrapper(tmp_path, "import os, signal; os.kill(os.getpid(), signal.SIGTERM)")
        code, _ = scan.run_wrapper(root, wrapper, ("python",))
        assert code == -signal.SIGTERM

    def test_a_timeout_kills_the_whole_process_group(self, root, tmp_path, monkeypatch):
        monkeypatch.setattr(scan, "LOCAL_TIMEOUT_SECONDS", 4)
        wrapper = make_wrapper(
            tmp_path,
            """
            import pathlib, subprocess, sys, time
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            pathlib.Path("grandchild.pid").write_text(str(child.pid))
            time.sleep(60)
            """,
        )
        started = time.monotonic()
        assert scan.run_wrapper(root, wrapper, ("python",)) == (None, "")
        assert time.monotonic() - started < 30
        pid = int((root / "grandchild.pid").read_text(encoding="utf-8"))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and _alive(pid):
            time.sleep(0.05)
        assert not _alive(pid), "grandchild survived the group kill"

    def test_a_launch_failure_is_reported_as_no_exit_code(self, root, tmp_path, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("no exec")

        monkeypatch.setattr(scan.subprocess, "Popen", boom)
        assert scan.run_wrapper(root, tmp_path / "w.py", ("python",)) == (None, "")

    def test_kill_group_falls_back_to_kill_when_the_group_is_gone(self, monkeypatch):
        calls = []

        class Proc:
            pid = 999999

            def kill(self):
                calls.append("kill")

            def communicate(self):
                calls.append("communicate")
                return "", ""

        def gone(pid, sig):
            raise ProcessLookupError

        monkeypatch.setattr(scan.os, "killpg", gone)
        scan._kill_group(Proc())
        assert calls == ["kill", "communicate"]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as stat:
            return stat.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


class TestPrecheck:
    def test_all_guards_hold(self, root, tmp_path):
        assert scan.precheck(root, writing_wrapper(tmp_path, 0), HEAD) is None

    def test_missing_codeql_directory(self, tmp_path):
        bare = tmp_path / "bare"
        bare.mkdir()
        assert scan.precheck(bare, tmp_path / "w.py", HEAD) == ".codeql directory missing"

    def test_missing_cli(self, tmp_path):
        work = tmp_path / "r"
        work.mkdir()
        install_codeql(work, cli=False)
        assert scan.precheck(work, tmp_path / "w.py", HEAD) == "CodeQL CLI not installed"

    def test_missing_wrapper(self, root, tmp_path):
        assert scan.precheck(root, tmp_path / "gone.py", HEAD) == "codeql-scan wrapper not found"

    @pytest.mark.parametrize("cache", ["missing", "other-head", "bad-json", "not-object"])
    def test_cache_must_be_built_at_head(self, root, tmp_path, cache):
        meta = root / ".codeql" / "db" / ".cache-metadata.json"
        if cache == "missing":
            meta.unlink()
        elif cache == "other-head":
            meta.write_text(json.dumps({"git_head": "b" * 40}), encoding="utf-8")
        elif cache == "bad-json":
            meta.write_text("{", encoding="utf-8")
        else:
            meta.write_text("[]", encoding="utf-8")
        failed = scan.precheck(root, writing_wrapper(tmp_path, 0), HEAD)
        assert failed == "database cache not built at HEAD"

    def test_windows_is_refused_because_there_is_no_group_kill(self, root, tmp_path, monkeypatch):
        monkeypatch.setattr(scan.platform, "system", lambda: "Windows")
        assert scan.precheck(root, writing_wrapper(tmp_path, 0), HEAD).startswith("platform")


class TestFreshSarif:
    def test_a_file_written_after_the_start_counts(self, root):
        started = time.time_ns()
        (root / ".codeql" / "results").mkdir()
        (root / ".codeql" / "results" / "python.sarif").write_text(sarif(RESULT), encoding="utf-8")
        assert scan.read_fresh_sarif(root, ("python",), started) == [[RESULT]]

    def test_a_file_from_before_the_run_is_stale(self, root):
        path = root / ".codeql" / "results" / "python.sarif"
        path.parent.mkdir()
        path.write_text(sarif(), encoding="utf-8")
        assert scan.read_fresh_sarif(root, ("python",), time.time_ns() + 10**10) is None

    def test_one_missing_language_voids_the_evidence(self, root):
        started = time.time_ns()
        (root / ".codeql" / "results").mkdir()
        (root / ".codeql" / "results" / "python.sarif").write_text(sarif(), encoding="utf-8")
        assert scan.read_fresh_sarif(root, ("python", "actions"), started) is None

    @pytest.mark.parametrize("text", ["{", "[]", '{"runs": "x"}', '{"version": "2.1.0"}'])
    def test_unparseable_or_shapeless_sarif_is_no_evidence(self, root, text):
        started = time.time_ns()
        (root / ".codeql" / "results").mkdir()
        (root / ".codeql" / "results" / "python.sarif").write_text(text, encoding="utf-8")
        assert scan.read_fresh_sarif(root, ("python",), started) is None

    def test_results_from_every_run_are_counted(self, root):
        started = time.time_ns()
        (root / ".codeql" / "results").mkdir()
        doc = {"runs": [{"results": [RESULT]}, {"results": [RESULT, RESULT]}, {}, None]}
        (root / ".codeql" / "results" / "python.sarif").write_text(
            json.dumps(doc), encoding="utf-8"
        )
        assert len(scan.read_fresh_sarif(root, ("python",), started)[0]) == 3


class TestClassify:
    L = ("python",)

    def test_exit_zero_and_no_results_is_clean(self):
        assert scan.classify(0, "", self.L, [[]]).outcome == "CLEAN"

    def test_exit_one_and_results_is_findings(self):
        out = scan.classify(1, "", self.L, [[RESULT]])
        assert out.outcome == "FINDINGS"
        assert out.results == [RESULT]

    def test_exit_one_with_empty_sarif_is_skipped_not_findings(self):
        out = scan.classify(1, "", self.L, [[]])
        assert (out.outcome, out.reason) == ("SKIPPED", "exit and results disagree")

    def test_exit_zero_with_results_is_skipped_not_clean(self):
        out = scan.classify(0, "", self.L, [[RESULT]])
        assert (out.outcome, out.reason) == ("SKIPPED", "exit and results disagree")

    def test_exit_zero_with_a_skip_marker_is_skipped_even_with_sarif(self):
        out = scan.classify(0, "[SKIP] .codeql/ not found", self.L, [[]])
        assert (out.outcome, out.reason) == ("SKIPPED", "wrapper skipped the scan")

    @pytest.mark.parametrize("code", [2, 3, 4, 7, 127, 255])
    def test_other_exit_codes_are_skipped(self, code):
        out = scan.classify(code, "", self.L, [[RESULT]])
        assert (out.outcome, out.reason) == ("SKIPPED", f"scan exited {code}")

    def test_a_signal_is_skipped(self):
        assert scan.classify(-9, "", self.L, [[]]).reason == "scan ended by a signal"

    def test_a_timeout_is_skipped(self):
        assert scan.classify(None, "", self.L, None).reason == "scan timed out or did not start"

    @pytest.mark.parametrize("code", [0, 1])
    def test_no_fresh_sarif_is_skipped_for_both_success_codes(self, code):
        out = scan.classify(code, "", self.L, None)
        assert (out.outcome, out.reason) == ("SKIPPED", "no fresh SARIF for every language")

    def test_results_from_two_languages_are_pooled(self):
        out = scan.classify(1, "", ("python", "actions"), [[RESULT], [RESULT]])
        assert len(out.results) == 2


class TestRunLocalScan:
    def run(self, root, wrapper, languages=("python",), clean=True, head=HEAD):
        return scan.run_local_scan(root, wrapper, head, clean, list(languages))

    def test_clean(self, root, tmp_path):
        out = self.run(root, writing_wrapper(tmp_path, 0))
        assert out.outcome == "CLEAN"
        assert out.languages == ("python",)

    def test_findings(self, root, tmp_path):
        out = self.run(root, writing_wrapper(tmp_path, 1, doc=sarif(RESULT)))
        assert (out.outcome, len(out.results)) == ("FINDINGS", 1)

    def test_exit_one_with_empty_sarif(self, root, tmp_path):
        out = self.run(root, writing_wrapper(tmp_path, 1, doc=sarif()))
        assert (out.outcome, out.reason) == ("SKIPPED", "exit and results disagree")

    def test_a_dirty_tree_runs_nothing(self, root, tmp_path):
        wrapper = make_wrapper(tmp_path, "import pathlib; pathlib.Path('ran').write_text('1')")
        out = self.run(root, wrapper, clean=False)
        assert (out.outcome, out.reason) == ("SKIPPED", "working tree not clean")
        assert not (root / "ran").exists()

    def test_an_empty_language_set_runs_nothing(self, root, tmp_path):
        wrapper = make_wrapper(tmp_path, "import pathlib; pathlib.Path('ran').write_text('1')")
        out = self.run(root, wrapper, languages=())
        assert (out.outcome, out.reason) == ("SKIPPED", "no scannable languages")
        assert not (root / "ran").exists()

    def test_a_failed_precheck_runs_nothing(self, root, tmp_path):
        wrapper = make_wrapper(tmp_path, "import pathlib; pathlib.Path('ran').write_text('1')")
        out = self.run(root, wrapper, head="c" * 40)
        assert out.reason == "database cache not built at HEAD"
        assert not (root / "ran").exists()

    def test_old_sarif_does_not_pass_as_a_fresh_scan(self, root, tmp_path):
        old = root / ".codeql" / "results" / "python.sarif"
        old.parent.mkdir(parents=True)
        old.write_text(sarif(), encoding="utf-8")
        past = time.time() - 3600
        os.utime(old, (past, past))
        wrapper = make_wrapper(tmp_path, "pass")
        out = self.run(root, wrapper)
        assert (out.outcome, out.reason) == ("SKIPPED", "no fresh SARIF for every language")

    def test_a_timeout_is_skipped(self, root, tmp_path, monkeypatch):
        monkeypatch.setattr(scan, "LOCAL_TIMEOUT_SECONDS", 1)
        out = self.run(root, make_wrapper(tmp_path, "import time; time.sleep(60)"))
        assert (out.outcome, out.reason) == ("SKIPPED", "scan timed out or did not start")

    def test_the_skip_marker_with_exit_zero_is_skipped(self, root, tmp_path):
        out = self.run(root, writing_wrapper(tmp_path, 0, err="[SKIP] .codeql/ not found"))
        assert (out.outcome, out.reason) == ("SKIPPED", "wrapper skipped the scan")

    def test_works_on_a_real_clean_repository_checkout(self, tmp_path):
        repo = make_repo(tmp_path)
        install_codeql(repo, head=git(repo, "rev-parse", "HEAD"))
        out = scan.run_local_scan(
            repo, writing_wrapper(tmp_path, 0), git(repo, "rev-parse", "HEAD"), True, ["python"]
        )
        assert out.outcome == "CLEAN"


def test_the_module_launches_the_wrapper_with_the_running_interpreter(root, tmp_path):
    wrapper = make_wrapper(
        tmp_path, "import pathlib, sys; pathlib.Path('exe.txt').write_text(sys.executable)"
    )
    scan.run_wrapper(root, wrapper, ("python",))
    assert (root / "exe.txt").read_text(encoding="utf-8") == sys.executable


def test_subprocess_module_is_not_shelled_out_with_a_string(root, tmp_path, monkeypatch):
    seen = {}
    real = subprocess.Popen

    def spy(command, **kwargs):
        seen["command"] = command
        seen["shell"] = kwargs.get("shell", False)
        seen["stdin"] = kwargs.get("stdin")
        return real(command, **kwargs)  # subprocess-encoding: strict-ok

    monkeypatch.setattr(scan.subprocess, "Popen", spy)
    scan.run_wrapper(root, make_wrapper(tmp_path, "pass"), ("python",))
    assert isinstance(seen["command"], list)
    assert seen["shell"] is False
    assert seen["stdin"] == subprocess.DEVNULL
