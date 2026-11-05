"""Tests for scripts/validation/check_dead_code.py.

The gate compares ruff's ARG findings with a shrink-only baseline. These tests
drive ``main(argv)`` against small fixture repositories and assert on the exit
code, then check the real baseline: it is sorted, matches the live tree, and
holds exactly the pinned number of lines.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

import check_dead_code
from check_dead_code import (
    BASELINE_RELPATH,
    REPO_ROOT,
    SCAN_ROOTS,
    GateConfigError,
    compare,
    load_baseline,
    main,
    parse_baseline,
    scan,
    validate_dead_code,
)

BASELINE = REPO_ROOT / BASELINE_RELPATH

# Shrink-only pin. Lower it when you delete a baseline line; never raise it to
# make a new finding fit. A new line fails the length test until this moves.
EXPECTED_DEAD_CODE_BASELINE_ENTRIES = 82

SCRIPT = "scripts/validation/check_dead_code.py"
UNUSED = "def f(path):\n    return 1\n"
UNUSED_KEY = "scripts/mod.py: ARG001 path"
BASELINE_LINE = re.compile(r"^\S[^:]*\.py: ARG00[1-5] \S+$")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo(tmp_path: Path, *, source: str = UNUSED) -> Path:
    """Build a fixture git repo. Its files are staged; the gate reads the index."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "mod.py").write_text(source, encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    return tmp_path


def _add(repo: Path, relpath: str, source: str) -> Path:
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    _git(repo, "add", "-A")
    return path


def _baseline(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "baseline.txt"
    path.write_text("# comment\n\n" + "".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def _run(repo: Path, baseline: Path) -> int:
    return main(["--repo-root", str(repo), "--baseline", str(baseline)])


def _keys(repo: Path) -> list[str]:
    return scan(repo).keys


def test_parse_baseline_skips_comments_and_blank_lines() -> None:
    assert parse_baseline("# note\n\n a.py: ARG001 x \n") == ["a.py: ARG001 x"]


@pytest.mark.parametrize("line", ["no separator here", ": ARG001 x", "a.py: "])
def test_parse_baseline_rejects_malformed_line(line: str) -> None:
    with pytest.raises(GateConfigError, match="line 1"):
        parse_baseline(line)


def test_compare_equal_multisets_is_clean() -> None:
    outcome = compare(["a: x", "b: y"], ["b: y", "a: x"])

    assert (outcome.new, outcome.stale) == ([], [])


def test_compare_reports_new_and_stale() -> None:
    outcome = compare(["a: x", "c: z"], ["a: x", "b: y"])

    assert (outcome.new, outcome.stale) == (["c: z"], ["b: y"])


def test_compare_counts_duplicates() -> None:
    assert compare(["a: x", "a: x"], ["a: x"]).new == ["a: x"]
    assert compare(["a: x"], ["a: x", "a: x"]).stale == ["a: x"]


def test_main_passes_when_findings_equal_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 0
    assert "Scanned 1 Python file(s); 1 finding(s)" in capsys.readouterr().out


def test_main_passes_on_clean_tree_with_empty_baseline(tmp_path: Path) -> None:
    repo = _repo(tmp_path, source="def f(path):\n    return path\n")

    assert _run(repo, _baseline(tmp_path)) == 0


def test_main_fails_on_new_finding(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)

    assert _run(repo, _baseline(tmp_path)) == 1
    assert f"new unused argument: {UNUSED_KEY}" in capsys.readouterr().err


def test_main_fails_on_stale_baseline_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    stale = "scripts/mod.py: ARG001 gone"

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY, stale)) == 1
    assert f"stale baseline entry: {stale}" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["path", "args"])
def test_common_name_is_reported_even_when_another_function_reads_it(
    tmp_path: Path, name: str
) -> None:
    # vulture matched names across the whole tree, so a name any function read
    # hid every unused parameter of that name. ruff resolves per function.
    source = f"def reads({name}):\n    return {name}\n\n\ndef ignores({name}):\n    return 1\n"
    repo = _repo(tmp_path, source=source)

    assert _keys(repo) == [f"scripts/mod.py: ARG001 {name}"]
    assert _run(repo, _baseline(tmp_path)) == 1


def test_scan_reports_method_and_lambda_arguments(tmp_path: Path) -> None:
    source = (
        "class C:\n    def m(self, unused):\n        return 1\n\n\ng = lambda x: 1  # noqa: E731\n"
    )
    repo = _repo(tmp_path, source=source)

    assert _keys(repo) == ["scripts/mod.py: ARG002 unused", "scripts/mod.py: ARG005 x"]


def test_scan_ignores_used_and_underscore_prefixed_arguments(tmp_path: Path) -> None:
    repo = _repo(tmp_path, source="def f(_unused, used):\n    return used\n")

    assert _keys(repo) == []


def test_key_has_no_line_number_so_unrelated_edits_keep_it_valid(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    baseline = _baseline(tmp_path, UNUSED_KEY)
    _add(repo, "scripts/mod.py", "# header\n\n\n" + UNUSED)

    assert _run(repo, baseline) == 0


def test_duplicate_names_in_one_file_need_one_baseline_line_each(tmp_path: Path) -> None:
    source = UNUSED + "\n\ndef h(path):\n    return 2\n"
    repo = _repo(tmp_path, source=source)

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 1
    assert _run(repo, _baseline(tmp_path, UNUSED_KEY, UNUSED_KEY)) == 0


@pytest.mark.parametrize(
    "relpath",
    [
        "scripts/tests/test_mod.py",
        "src/claude/hooks/hook.py",
        "src/claude/lib/github_core/core.py",
        ".claude/lib/paths.py",
    ],
)
def test_main_skips_excluded_paths(tmp_path: Path, relpath: str) -> None:
    repo = _repo(tmp_path)
    _add(repo, relpath, UNUSED)

    assert _keys(repo) == [UNUSED_KEY]


def test_main_scans_every_root(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    for root in SCAN_ROOTS[1:]:
        _add(repo, f"{root}/extra.py", UNUSED)

    assert len(_keys(repo)) == len(SCAN_ROOTS)


def test_main_ignores_python_files_outside_the_roots(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _add(repo, "other/mod.py", UNUSED)

    assert scan(repo).scanned_files == 1


def test_main_ignores_untracked_python_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    (repo / "scripts" / "draft.py").write_text(UNUSED, encoding="utf-8")

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 0
    assert "Scanned 1 Python file(s); 1 finding(s)" in capsys.readouterr().out


def test_main_reports_the_same_file_once_it_is_tracked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    _add(repo, "scripts/draft.py", "def g(args):\n    return 1\n")

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 1
    assert "new unused argument: scripts/draft.py: ARG001 args" in capsys.readouterr().err


def test_main_skips_a_tracked_file_deleted_from_the_work_tree(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    gone = _add(repo, "scripts/gone.py", "def g(args):\n    return 1\n")
    gone.unlink()

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 0


def test_main_skips_tracked_symlinks(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    try:
        (repo / "scripts" / "link.py").symlink_to("mod.py")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks are not available here: {exc}")
    _git(repo, "add", "scripts/link.py")

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 0


def test_main_strips_leaked_git_env_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "nowhere"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "nowhere"))

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 0


def test_main_config_error_outside_a_git_work_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    (repo / ".git").rename(repo / "not-git")

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 2
    assert "git ls-files failed" in capsys.readouterr().err


def test_main_config_error_when_git_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)

    def no_git(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(check_dead_code.subprocess, "run", no_git)

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 2
    assert "cannot run git" in capsys.readouterr().err


def test_main_config_error_when_ruff_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(check_dead_code.shutil, "which", lambda _name: None)

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 2
    assert "ruff is not installed" in capsys.readouterr().err


def test_main_config_error_when_ruff_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(check_dead_code.shutil, "which", lambda _name: str(tmp_path / "no-ruff"))

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 2
    assert "cannot run ruff" in capsys.readouterr().err


def _fake_run(real_run: object, *, git: object = None, ruff: object = None) -> object:
    """Return a ``subprocess.run`` stand-in that replaces git and/or ruff calls."""

    def run(argv: list[str], *args: object, **kwargs: object) -> object:
        override = git if argv[0] == "git" else ruff
        if override is None:
            return real_run(argv, *args, **kwargs)  # type: ignore[operator]
        if isinstance(override, BaseException):
            raise override
        return override

    return run


@pytest.mark.parametrize("tool", ["git", "ruff"])
def test_main_external_error_when_a_tool_times_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool: str,
) -> None:
    repo = _repo(tmp_path)
    expired = subprocess.TimeoutExpired(cmd=tool, timeout=1)
    monkeypatch.setattr(
        check_dead_code.subprocess,
        "run",
        _fake_run(subprocess.run, **{tool: expired}),
    )

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 3
    err = capsys.readouterr().err
    assert "dead-code gate" in err
    assert "timed out" in err
    assert tool in err


def test_every_subprocess_call_sets_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    seen: dict[str, object] = {}
    real_run = subprocess.run

    def spy(argv: list[str], *args: object, **kwargs: object) -> object:
        seen[Path(argv[0]).name] = kwargs.get("timeout")
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(check_dead_code.subprocess, "run", spy)

    scan(repo)

    assert set(seen) == {"git", "ruff"}
    assert all(isinstance(value, int) and value > 0 for value in seen.values())


def test_main_config_error_when_ruff_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    failed = subprocess.CompletedProcess(["ruff"], 2, stdout="", stderr="bad config")
    monkeypatch.setattr(check_dead_code.subprocess, "run", _fake_run(subprocess.run, ruff=failed))

    assert _run(repo, _baseline(tmp_path, UNUSED_KEY)) == 2
    assert "ruff exited 2: bad config" in capsys.readouterr().err


def test_main_config_error_when_ruff_prints_no_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    garbled = subprocess.CompletedProcess(["ruff"], 0, stdout="not json", stderr="")
    monkeypatch.setattr(check_dead_code.subprocess, "run", _fake_run(subprocess.run, ruff=garbled))

    assert _run(repo, _baseline(tmp_path)) == 2
    assert "did not print JSON" in capsys.readouterr().err


def test_main_config_error_when_a_finding_names_no_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    odd = subprocess.CompletedProcess(
        ["ruff"],
        1,
        stdout='[{"code": "ARG001", "filename": "x.py", "message": "Unused argument"}]',
        stderr="",
    )
    monkeypatch.setattr(check_dead_code.subprocess, "run", _fake_run(subprocess.run, ruff=odd))

    assert _run(repo, _baseline(tmp_path)) == 2
    assert "names no argument" in capsys.readouterr().err


def test_main_config_error_on_syntax_error_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, source="def broken(:\n")

    assert _run(repo, _baseline(tmp_path)) == 2
    assert "could not parse" in capsys.readouterr().err


def test_scan_merges_findings_across_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    _add(repo, "scripts/b.py", "def g(args):\n    return 1\n")
    _add(repo, "scripts/c.py", "def h(data):\n    return 1\n")
    monkeypatch.setattr(check_dead_code, "RUFF_BATCH_SIZE", 1)

    result = scan(repo)

    assert result.scanned_files == 3
    assert result.keys == [
        "scripts/b.py: ARG001 args",
        "scripts/c.py: ARG001 data",
        UNUSED_KEY,
    ]


def test_main_config_error_when_nothing_scanned(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")

    assert _run(tmp_path, _baseline(tmp_path)) == 2


def test_main_config_error_when_baseline_missing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert _run(repo, tmp_path / "absent.txt") == 2


def test_main_config_error_when_baseline_is_not_utf8(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    baseline = tmp_path / "baseline.txt"
    baseline.write_bytes(b"scripts/mod.py: ARG001 \xff\n")

    assert _run(repo, baseline) == 2
    assert "cannot read baseline" in capsys.readouterr().err


def test_main_config_error_when_baseline_malformed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert _run(repo, _baseline(tmp_path, "not a key")) == 2


def test_repository_findings_equal_the_committed_baseline() -> None:
    assert main([]) == 0


def test_repository_scan_reads_a_nonzero_number_of_files() -> None:
    result = scan(REPO_ROOT)

    assert result.scanned_files > 0
    assert result.keys


def test_main_defaults_baseline_to_the_repo_root(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(f"{UNUSED_KEY}\n", encoding="utf-8")

    assert main(["--repo-root", str(repo)]) == 0


def test_validate_dead_code_returns_true_when_baseline_matches(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(f"{UNUSED_KEY}\n", encoding="utf-8")

    assert validate_dead_code(repo) is True


def test_validate_dead_code_fails_closed_without_baseline(tmp_path: Path) -> None:
    assert validate_dead_code(_repo(tmp_path)) is False


def test_validate_dead_code_fails_closed_without_ruff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(f"{UNUSED_KEY}\n", encoding="utf-8")
    monkeypatch.setattr(check_dead_code.shutil, "which", lambda _name: None)

    assert validate_dead_code(repo) is False


def test_validate_dead_code_fails_closed_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(f"{UNUSED_KEY}\n", encoding="utf-8")
    expired = subprocess.TimeoutExpired(cmd="ruff", timeout=1)
    monkeypatch.setattr(check_dead_code.subprocess, "run", _fake_run(subprocess.run, ruff=expired))

    assert validate_dead_code(repo) is False


def test_pre_pr_sequence_runs_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import pre_pr_sequence

    calls: list[Path] = []

    def fake(root: Path) -> bool:
        calls.append(root)
        return False

    monkeypatch.setattr(pre_pr_sequence, "validate_dead_code", fake)
    gates = [g for g in pre_pr_sequence._SEQUENCE if g.name == "Dead Code Detection"]

    assert len(gates) == 1
    assert gates[0].run(REPO_ROOT, argparse.Namespace()) is False
    assert calls == [REPO_ROOT]


def test_baseline_is_sorted_so_removals_diff_cleanly() -> None:
    keys = load_baseline(BASELINE)

    assert keys == sorted(keys)


def test_baseline_entries_are_path_code_argument_with_no_line_number() -> None:
    bad = [key for key in load_baseline(BASELINE) if not BASELINE_LINE.match(key)]

    assert bad == []


def test_baseline_length_matches_the_pinned_constant() -> None:
    keys = load_baseline(BASELINE)

    assert len(keys) == EXPECTED_DEAD_CODE_BASELINE_ENTRIES, (
        f"{BASELINE.name} holds {len(keys)} entries, pinned at "
        f"{EXPECTED_DEAD_CODE_BASELINE_ENTRIES}. Lower the constant when you delete a "
        "line; never raise it. Use or remove the argument instead of listing it."
    )


def test_repo_wide_ruff_select_does_not_include_arg() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert not [rule for rule in config["tool"]["ruff"]["lint"]["select"] if "ARG".startswith(rule)]


def test_vulture_is_not_a_dependency_or_config() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = config["project"]["optional-dependencies"]["dev"]

    assert "vulture" not in config["tool"]
    assert not [dep for dep in extras if dep.lower().startswith("vulture")]
    assert "vulture" not in (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")


def _run_commands(node: object) -> list[str]:
    if isinstance(node, dict):
        found = [node["run"]] if isinstance(node.get("run"), str) else []
        return found + [cmd for value in node.values() for cmd in _run_commands(value)]
    if isinstance(node, list):
        return [cmd for item in node for cmd in _run_commands(item)]
    return []


def test_pre_push_hook_runs_the_gate() -> None:
    lefthook = yaml.safe_load((REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    assert any(SCRIPT in cmd for cmd in _run_commands(lefthook["pre-push"]))


def test_pytest_workflow_runs_the_gate() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pytest.yml").read_text(encoding="utf-8")
    )

    assert any(SCRIPT in cmd for cmd in _run_commands(workflow["jobs"]))


def test_baseline_sits_next_to_the_script() -> None:
    assert BASELINE == Path(check_dead_code.__file__).resolve().parent / "dead_code_baseline.txt"
