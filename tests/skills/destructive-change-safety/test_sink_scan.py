"""Sink identification and path tracing for sink_scan.py."""

from __future__ import annotations

from pathlib import Path

import pytest
import sink_scan

REPO_ROOT = Path(__file__).resolve().parents[3]


def scan_dir(root: Path, changed: list[str] | None = None) -> dict:
    return sink_scan.scan([root], root, changed or [])


def sink_labels(report: dict) -> set[str]:
    return {s["label"] for s in report["sinks"]}


def scan_source(tmp_path: Path, source: str) -> dict:
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")
    return scan_dir(tmp_path)


def test_indirect_path_traces_from_cli_flag_to_delete(indirect_repo: Path) -> None:
    report = scan_dir(indirect_repo)
    (sink,) = report["sinks"]
    assert report["decision"] == "activate"
    assert sink["location"] == "adapter.py:6"
    assert sink["kind"] == "delete"
    assert sink["chains"] == ["main -> run -> purge_files"]
    assert sink["flags"] == ["--purge-stale"]
    assert sink["callers_unknown"] is False


def test_forward_trace_from_changed_config_reaches_the_sink(indirect_repo: Path) -> None:
    report = scan_dir(indirect_repo, changed=["run"])
    assert report["sinks"][0]["reached_from_changed"] == "run -> purge_files"


def test_changed_function_that_cannot_reach_the_sink_reports_nothing(indirect_repo: Path) -> None:
    report = scan_dir(indirect_repo, changed=["load_config"])
    assert report["sinks"][0]["reached_from_changed"] == ""


def test_read_only_code_skips(read_only_repo: Path) -> None:
    report = scan_dir(read_only_repo)
    assert report == {"decision": "skip", "unparsed": [], "sinks": []}


def test_sink_with_no_scanned_caller_is_marked_unknown(tmp_path: Path) -> None:
    report = scan_source(tmp_path, "import os\n\ndef wipe(p):\n    os.remove(p)\n")
    assert report["sinks"][0]["callers_unknown"] is True
    assert report["sinks"][0]["chains"] == ["wipe"]


def test_module_level_sink_has_unknown_callers(
    tmp_path: Path,
) -> None:
    report = scan_source(tmp_path, "import os\nos.remove('x')\n")
    assert report["sinks"][0]["function"] == "<module>"
    assert report["sinks"][0]["callers_unknown"] is True


@pytest.mark.parametrize(
    ("source", "label"),
    [
        ("import shutil\ndef f(p):\n    shutil.move(p, 'b')\n", "shutil.move"),
        ("from pathlib import Path\ndef f(p):\n    Path(p).unlink()\n", ".unlink()"),
        ("def f(p):\n    p.write_text('x')\n", ".write_text()"),
        ("def f(p):\n    open(p, 'w')\n", "open(..., 'w')"),
        ("def f(p):\n    open(p, mode='wb')\n", "open(..., 'w')"),
        (
            "import subprocess\ndef f():\n    subprocess.run(['git', 'clean', '-fdx'])\n",
            "git clean -fdx",
        ),
        (
            "import os\ndef f():\n    os.system('rm -rf build')\n",
            "rm -rf build",
        ),
        (
            "def f(path, run_git):\n    run_git(['worktree', 'remove', path])\n",
            "worktree remove",
        ),
        (
            "def f(git):\n    git(('branch', '-D', 'old'))\n",
            "branch -D old",
        ),
        (
            "def f(git):\n    git(['push', 'origin', '--force', 'main'])\n",
            "push origin --force main",
        ),
        (
            "def f(cur):\n    cur.execute('DELETE FROM users WHERE id = 1')\n",
            "DELETE FROM users WHERE id = 1",
        ),
        (
            "def f(cur):\n    cur.execute('drop   table users')\n",
            "drop table users",
        ),
        (
            "def f(cur):\n    cur.execute('UPDATE users SET name = 1')\n",
            "UPDATE users SET name = 1",
        ),
    ],
)
def test_detects_each_sink_family(tmp_path: Path, source: str, label: str) -> None:
    assert label in sink_labels(scan_source(tmp_path, source))


@pytest.mark.parametrize(
    "source",
    [
        "def f(items):\n    items.remove(1)\n    return 'a'.replace('a', 'b')\n",
        "def f():\n    open('x')\n    open('x', 'r')\n",
        "import subprocess\ndef f():\n    subprocess.run(['git', 'status'])\n",
        "import subprocess\ndef f():\n    subprocess.run()\n",
        "def f(c):\n    c.execute('SELECT * FROM users')\n",
        'def f():\n    """Run DELETE FROM users to purge."""\n',
        "def f(x):\n    return x()()\n",
        "def f(run_git):\n    run_git(['worktree', 'list'])\n    run_git(['status'])\n",
        "def f(run_git):\n    run_git(['clean'])\n    run_git([])\n",
        "def f(run_git):\n    run_git('worktree remove x')\n",
    ],
)
def test_benign_code_is_not_a_sink(tmp_path: Path, source: str) -> None:
    assert scan_source(tmp_path, source)["decision"] == "skip"


def test_unparsable_python_makes_the_decision_unknown(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def (:\n", encoding="utf-8")
    report = scan_dir(tmp_path)
    assert report["decision"] == "unknown"
    assert report["unparsed"] == ["broken.py"]


def test_non_utf8_text_file_makes_the_decision_unknown(tmp_path: Path) -> None:
    (tmp_path / "bad.sql").write_bytes(b"\xff\xfe\x00")
    assert scan_dir(tmp_path)["unparsed"] == ["bad.sql"]


def test_sql_and_shell_files_are_scanned_by_line(tmp_path: Path) -> None:
    (tmp_path / "m.sql").write_text("-- DELETE FROM old\nDELETE FROM users;\n", encoding="utf-8")
    (tmp_path / "c.sh").write_text("# rm -rf /\necho hi\nrm -rf build\n", encoding="utf-8")
    report = scan_dir(tmp_path)
    assert {(s["location"], s["kind"]) for s in report["sinks"]} == {
        ("m.sql:2", "sql"),
        ("c.sh:3", "command"),
    }
    assert all(s["callers_unknown"] for s in report["sinks"])


def test_skipped_directories_and_other_suffixes_are_ignored(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hook.sh").write_text("rm -rf x\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("DELETE FROM users\n", encoding="utf-8")
    assert scan_dir(tmp_path)["decision"] == "skip"


def test_scanning_a_single_file_and_a_path_outside_base(tmp_path: Path) -> None:
    target = tmp_path / "one.py"
    target.write_text("import os\ndef f():\n    os.remove('x')\n", encoding="utf-8")
    elsewhere = tmp_path / "base"
    elsewhere.mkdir()
    report = sink_scan.scan([target], elsewhere, [])
    assert report["sinks"][0]["location"] == f"{target.as_posix()}:3"


def test_recursive_calls_terminate(tmp_path: Path) -> None:
    source = "import os\ndef a():\n    b()\ndef b():\n    a()\n    os.remove('x')\n"
    report = scan_source(tmp_path, source)
    assert report["sinks"][0]["chains"] == ["a -> b"]


def test_chain_depth_is_capped(tmp_path: Path) -> None:
    lines = ["import os", "def f0():", "    os.remove('x')"]
    for index in range(1, 20):
        lines += [f"def f{index}():", f"    f{index - 1}()"]
    report = scan_source(tmp_path, "\n".join(lines) + "\n")
    (chain,) = report["sinks"][0]["chains"]
    assert chain.count("->") == sink_scan.MAX_DEPTH - 1


def test_chain_count_is_capped(tmp_path: Path) -> None:
    lines = ["import os", "def sink():", "    os.remove('x')"]
    for index in range(sink_scan.MAX_CHAINS + 5):
        lines += [f"def caller{index}():", "    sink()"]
    report = scan_source(tmp_path, "\n".join(lines) + "\n")
    assert len(report["sinks"][0]["chains"]) == sink_scan.MAX_CHAINS


def test_async_functions_own_their_sinks(tmp_path: Path) -> None:
    source = "import os\nasync def go():\n    os.remove('x')\n"
    assert scan_source(tmp_path, source)["sinks"][0]["function"] == "go"


def test_add_argument_ignores_positional_arguments(tmp_path: Path) -> None:
    source = (
        "import os\n"
        "def main(p):\n"
        "    p.add_argument('name')\n"
        "    p.add_argument('-x')\n"
        "    os.remove('f')\n"
    )
    assert scan_source(tmp_path, source)["sinks"][0]["flags"] == ["-x"]


def test_flags_declared_in_a_called_parse_args_gate_the_sink(tmp_path: Path) -> None:
    source = (
        "import argparse, os\n"
        "def parse_args():\n"
        "    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--apply')\n"
        "    return p.parse_args()\n"
        "def unrelated():\n"
        "    p.add_argument('--other')\n"
        "def main():\n"
        "    if parse_args().apply:\n"
        "        purge()\n"
        "def purge():\n"
        "    os.remove('f')\n"
    )
    assert scan_source(tmp_path, source)["sinks"][0]["flags"] == ["--apply"]


def test_mutation_control_path_tracing_is_load_bearing(
    indirect_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With caller tracing stubbed out, the CLI entry and flag vanish from the report."""
    before = scan_dir(indirect_repo)["sinks"][0]
    assert "main" in before["chains"][0] and before["flags"] == ["--purge-stale"]
    monkeypatch.setattr(sink_scan, "caller_chains", lambda graph, function: [[function]])
    after = scan_dir(indirect_repo)["sinks"][0]
    assert "main" not in after["chains"][0]
    assert after["flags"] == []


def test_forward_trace_survives_a_call_cycle(tmp_path: Path) -> None:
    source = "import os\ndef a():\n    b()\ndef b():\n    a()\n    os.remove('x')\n"
    (tmp_path / "mod.py").write_text(source, encoding="utf-8")
    report = scan_dir(tmp_path, changed=["a"])
    assert report["sinks"][0]["reached_from_changed"] == "a -> b"


def test_real_repository_gc_path_traces_from_apply_flag() -> None:
    """The #4790 cleanup path: the --apply flag reaches `git worktree remove`."""
    maintenance = REPO_ROOT / "scripts" / "maintenance"
    report = sink_scan.scan([maintenance], REPO_ROOT, ["apply_removals"])
    removal = [s for s in report["sinks"] if s["label"] == "worktree remove"]
    assert removal, "git worktree remove sink in scripts/maintenance went undetected"
    assert removal[0]["function"] == "remove_worktree"
    assert "--apply" in removal[0]["flags"]
