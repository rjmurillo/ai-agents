from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from functools import partial
from pathlib import Path
from unittest.mock import Mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATION_DIR))

import check_duplicate_code as gate

SCRIPT = VALIDATION_DIR / "check_duplicate_code.py"


class TestBaselineParsing:
    def test_round_trips_sorted(self) -> None:
        text = gate.render_baseline({"b": 2, "a": 1})
        assert list(json.loads(text)["fingerprints"]) == ["a", "b"]
        assert gate.parse_baseline(text, "t") == {"a": 1, "b": 2}

    @pytest.mark.parametrize(
        "text",
        [
            "not json",
            "[]",
            '{"version": 2, "fingerprints": {}}',
            '{"version": 1, "fingerprints": []}',
            '{"version": 1, "fingerprints": {"a": 0}}',
            '{"version": 1, "fingerprints": {"a": true}}',
        ],
    )
    def test_rejects_untrusted_shapes_with_config_error(self, text: str) -> None:
        with pytest.raises(gate.GateError) as exc:
            gate.parse_baseline(text, "t")
        assert exc.value.code == 2


class TestRatchetMath:
    def test_new_fingerprint_is_growth(self) -> None:
        delta = gate.diff_against_ceiling({"a": 1}, {"a": 1, "b": 1})
        assert delta.grown == {"b": 1}
        assert delta.stale == {}

    def test_higher_count_is_growth(self) -> None:
        assert gate.diff_against_ceiling({"a": 1}, {"a": 2}).grown == {"a": 2}

    def test_removed_clone_is_stale(self) -> None:
        delta = gate.diff_against_ceiling({"a": 2, "b": 1}, {"a": 1})
        assert delta.grown == {}
        assert delta.stale == {"a": 2, "b": 1}

    def test_equal_is_clean(self) -> None:
        delta = gate.diff_against_ceiling({"a": 1}, {"a": 1})
        assert (delta.grown, delta.stale) == ({}, {})

    def test_base_ceiling_blocks_hand_added_entries(self) -> None:
        ceiling = gate.compute_ceiling({"a": 3, "new": 1}, {"a": 2})
        assert ceiling == {"a": 2}

    def test_no_base_keeps_working_baseline(self) -> None:
        assert gate.compute_ceiling({"a": 3}, None) == {"a": 3}

    def test_prune_never_adds_or_raises(self) -> None:
        assert gate.pruned({"a": 2, "b": 1}, {"a": 1, "c": 5}) == {"a": 1}


def _fake_jscpd(
    tmp_path: Path,
    fingerprints: dict[str, int],
    duplicates: list[dict[str, object]] | None = None,
) -> str:
    """A stand-in runner that rewrites --baseline with fixed fingerprints."""
    script = tmp_path / "fake_jscpd.py"
    script.write_text(
        "import json, sys\n"
        "a = sys.argv\n"
        "if '--update-baseline' in a:\n"
        "    p = a[a.index('--baseline') + 1]\n"
        f"    json.dump({{'version': 1, 'fingerprints': {fingerprints!r}}}, open(p, 'w'))\n"
        "    out = a[a.index('-o') + 1]\n"
        "    json.dump({'statistics': {'total': {'sources': 2}}}, "
        "open(out + '/jscpd-report.json', 'w'))\n"
        "elif '-r' in a and a[a.index('-r') + 1] == 'json':\n"
        "    p = a[a.index('--baseline') + 1]\n"
        "    json.dump(json.load(open(p)), "
        f"open({str(tmp_path / 'diagnostic-baseline.json')!r}, 'w'))\n"
        "    out = a[a.index('-o') + 1]\n"
        f"    json.dump({{'duplicates': {duplicates or []!r}}}, "
        "open(out + '/jscpd-report.json', 'w'))\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {script}"


def _repo(tmp_path: Path, baseline: dict[str, int]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".jscpd.json").write_text("{}", encoding="utf-8")
    (repo / ".jscpd-baseline.json").write_text(gate.render_baseline(baseline), encoding="utf-8")
    return repo


def _use_runner(monkeypatch: pytest.MonkeyPatch, command: list[str]) -> None:
    """Inject the scanner command. The environment cannot choose it (CWE-426)."""
    monkeypatch.setattr(gate, "resolve_runner", lambda _root: command)


def _run(repo: Path, runner: str, *args: str, monkeypatch: pytest.MonkeyPatch) -> int:
    _use_runner(monkeypatch, shlex.split(runner))
    return gate.main([str(repo), *args])


def _diagnostic_runner(
    report: str | Exception | None, cmd: list[str], **_kwargs: object
) -> subprocess.CompletedProcess[str]:
    output = Path(cmd[cmd.index("-o") + 1]) / "jscpd-report.json"
    if "--update-baseline" in cmd:
        Path(cmd[cmd.index("--baseline") + 1]).write_text(
            gate.render_baseline({"new": 1}), encoding="utf-8"
        )
        output.write_text('{"statistics": {"total": {"sources": 2}}}', encoding="utf-8")
    elif isinstance(report, Exception):
        raise report
    elif report is not None:
        output.write_text(report, encoding="utf-8")
    return subprocess.CompletedProcess(cmd, 0, "", "")


def _diagnostic_clone(**overrides: object) -> dict[str, object]:
    clone: dict[str, object] = {
        "isNew": True,
        "firstFile": {"name": "first.py", "start": 1, "end": 12},
        "secondFile": {"name": "second.py", "start": 20, "end": 31},
        "lines": 12,
    }
    clone.update(overrides)
    return clone


BAD_CLONE_FIELDS: list[tuple[str, object]] = [
    ("isNew", "true"),
    ("isNew", None),
    ("lines", True),
    ("lines", 0),
    ("firstFile", None),
    ("secondFile", []),
    ("firstFile", {"name": "x", "start": 1}),
    ("firstFile", {"name": " ", "start": 1, "end": 2}),
    ("firstFile", {"name": 5, "start": 1, "end": 2}),
    ("firstFile", {"name": "x", "start": True, "end": 2}),
    ("firstFile", {"name": "x", "start": 0, "end": 2}),
    ("secondFile", {"name": "x", "start": 3, "end": 2}),
    ("secondFile", {"name": "x", "start": 1, "end": None}),
]


@pytest.mark.parametrize(
    "report",
    [
        "{bad",
        "null",
        "[]",
        "1",
        '""',
        "{}",
        '{"duplicates": null}',
        '{"duplicates": {}}',
        '{"duplicates": [null]}',
        '{"duplicates": [[]]}',
        '{"duplicates": [{}]}',
        *[
            json.dumps({"duplicates": [_diagnostic_clone(**{field: value})]})
            for field, value in BAD_CLONE_FIELDS
        ],
        *[
            json.dumps(
                {"duplicates": [{k: v for k, v in _diagnostic_clone().items() if k != field}]}
            )
            for field in ("isNew", "firstFile", "secondFile", "lines")
        ],
    ],
)
def test_bad_diagnostics_preserve_duplication_failure(
    report: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """AC3: Optional diagnostic corruption cannot replace the primary verdict."""
    repo = _repo(tmp_path, {})
    _use_runner(monkeypatch, ["fake-jscpd"])
    monkeypatch.setattr(gate.subprocess, "run", partial(_diagnostic_runner, report))

    assert gate.main([str(repo)]) == 1

    captured = capsys.readouterr()
    assert "FAIL: 1 duplicated block(s) are new" in captured.out
    assert "WARNING: clone diagnostics unavailable" in captured.err
    assert "OK:" not in captured.out
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "report",
    [
        '{"duplicates": []}',
        '{"duplicates": ' + json.dumps([_diagnostic_clone(isNew=False)]) + "}",
    ],
)
def test_absent_or_old_diagnostics_preserve_failure_without_corruption_warning(
    report, tmp_path, monkeypatch, capsys
) -> None:
    repo = _repo(tmp_path, {})
    _use_runner(monkeypatch, ["fake-jscpd"])
    monkeypatch.setattr(gate.subprocess, "run", partial(_diagnostic_runner, report))
    assert gate.main([str(repo)]) == 1
    captured = capsys.readouterr()
    assert "FAIL:" in captured.out
    assert captured.err == ""


def test_missing_diagnostics_report_warns_and_preserves_failure(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, {})
    _use_runner(monkeypatch, ["fake-jscpd"])
    monkeypatch.setattr(gate.subprocess, "run", partial(_diagnostic_runner, None))
    assert gate.main([str(repo)]) == 1
    captured = capsys.readouterr()
    assert "FAIL: 1 duplicated block(s) are new" in captured.out
    assert "WARNING: clone diagnostics unavailable: jscpd diagnostics rerun wrote no report" in (
        captured.err
    )


def test_failed_diagnostics_rerun_warns_with_exit_code(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, {})
    _use_runner(monkeypatch, ["fake-jscpd"])

    def rerun_fails(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--update-baseline" in cmd:
            return _diagnostic_runner(None, cmd, **kwargs)
        return subprocess.CompletedProcess(cmd, 3, "", "boom")

    monkeypatch.setattr(gate.subprocess, "run", rerun_fails)
    assert gate.main([str(repo)]) == 1
    captured = capsys.readouterr()
    assert "FAIL: 1 duplicated block(s) are new" in captured.out
    assert "WARNING: clone diagnostics unavailable: jscpd diagnostics rerun exited 3" in (
        captured.err
    )


@pytest.mark.parametrize("error", [OSError("unavailable"), subprocess.TimeoutExpired("jscpd", 1)])
def test_diagnostic_process_errors_preserve_primary_failure(error, tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, {})
    _use_runner(monkeypatch, ["fake-jscpd"])
    monkeypatch.setattr(gate.subprocess, "run", partial(_diagnostic_runner, error))
    assert gate.main([str(repo)]) == 1
    captured = capsys.readouterr()
    assert "FAIL:" in captured.out
    assert "WARNING: clone diagnostics unavailable" in captured.err


@pytest.mark.parametrize("count", [1, gate.MAX_REPORTED + 1])
def test_valid_diagnostics_render_bounded_locations(count, tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path, {})
    report = json.dumps({"duplicates": [_diagnostic_clone()] * count})
    _use_runner(monkeypatch, ["fake-jscpd"])
    monkeypatch.setattr(gate.subprocess, "run", partial(_diagnostic_runner, report))
    assert gate.main([str(repo)]) == 1
    captured = capsys.readouterr()
    assert captured.out.count("first.py:1-12 <-> second.py:20-31 (12 lines)") == min(
        count, gate.MAX_REPORTED
    )
    assert "FAIL:" in captured.out
    assert captured.err == ""


def test_setup_command_installs_required_locked_scanner_before_testing() -> None:
    """AC2: A contributor following setup installs the hard-gated Node tool."""
    guide = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    setup = guide.split("### Setup Steps", 1)[1].split("```bash\n", 1)[1].split("```", 1)[0]
    commands = setup.strip().split(" && ")
    assert "npm ci --ignore-scripts" in commands
    assert commands.index("npm ci --ignore-scripts") < next(
        i for i, command in enumerate(commands) if "pytest " in command
    )
    prerequisites = guide.split("**Required Versions:**", 1)[1].split("### Setup Steps", 1)[0]
    assert "Node.js LTS" in prerequisites and "npm" in prerequisites


class TestEntryPoint:
    def test_missing_locked_runner_is_config_error_without_download(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        repo = _repo(tmp_path, {})

        runner = Mock(side_effect=AssertionError("a missing scanner must not launch an installer"))
        monkeypatch.setattr(gate.subprocess, "run", runner)
        assert gate.main([str(repo)]) == 2
        runner.assert_not_called()
        assert "npm ci --ignore-scripts" in capsys.readouterr().err

    def test_locked_runner_is_resolved_locally(self, tmp_path) -> None:
        binary = tmp_path / "node_modules" / "jscpd" / "run-jscpd.js"
        binary.parent.mkdir(parents=True)
        binary.write_text("locked scanner", encoding="utf-8")
        assert gate.resolve_runner(tmp_path) == ["node", str(binary)]

    def test_environment_cannot_choose_the_runner(self, tmp_path, monkeypatch) -> None:
        """CWE-426: JSCPD_BIN must not select the executable, present or absent."""
        monkeypatch.setenv("JSCPD_BIN", "/tmp/attacker-jscpd")
        with pytest.raises(gate.GateError) as missing:
            gate.resolve_runner(tmp_path)
        assert missing.value.code == 2
        binary = tmp_path / "node_modules" / "jscpd" / "run-jscpd.js"
        binary.parent.mkdir(parents=True)
        binary.write_text("locked scanner", encoding="utf-8")
        assert gate.resolve_runner(tmp_path) == ["node", str(binary)]

    def test_passes_when_scan_matches_baseline(self, tmp_path, monkeypatch, capsys) -> None:
        repo = _repo(tmp_path, {"a": 1})
        code = _run(repo, _fake_jscpd(tmp_path, {"a": 1}), monkeypatch=monkeypatch)
        assert code == 0
        output = capsys.readouterr().out
        assert "Examined 2 Python files." in output
        assert "OK" in output

    def test_fails_on_new_duplication(self, tmp_path, monkeypatch, capsys) -> None:
        repo = _repo(tmp_path, {"a": 1})
        code = _run(repo, _fake_jscpd(tmp_path, {"a": 1, "b": 1}), monkeypatch=monkeypatch)
        assert code == 1
        assert "new or occur more often" in capsys.readouterr().out

    def test_diagnostics_show_only_new_clones(self, tmp_path, monkeypatch, capsys) -> None:
        repo = _repo(tmp_path, {"a": 1})
        duplicates = [
            {
                "firstFile": {"name": name, "start": 1, "end": 12},
                "secondFile": {"name": "copy.py", "start": 20, "end": 31},
                "lines": 12,
                "isNew": is_new,
            }
            for name, is_new in [("old.py", False), ("new.py", True)]
        ]
        runner = _fake_jscpd(tmp_path, {"a": 1, "b": 1}, duplicates)

        assert _run(repo, runner, monkeypatch=monkeypatch) == 1

        output = capsys.readouterr().out
        assert "new.py:1-12 <-> copy.py:20-31 (12 lines)" in output
        assert "old.py" not in output
        diagnostic_baseline = json.loads(
            (tmp_path / "diagnostic-baseline.json").read_text(encoding="utf-8")
        )
        assert diagnostic_baseline["fingerprints"] == {"a": 1}

    def test_fails_on_stale_entry_and_prune_fixes_it(self, tmp_path, monkeypatch) -> None:
        repo = _repo(tmp_path, {"a": 1, "gone": 1})
        runner = _fake_jscpd(tmp_path, {"a": 1})
        assert _run(repo, runner, monkeypatch=monkeypatch) == 1
        assert _run(repo, runner, "--prune", monkeypatch=monkeypatch) == 0
        saved = json.loads((repo / ".jscpd-baseline.json").read_text(encoding="utf-8"))
        assert saved["fingerprints"] == {"a": 1}
        assert _run(repo, runner, monkeypatch=monkeypatch) == 0

    def test_prune_refuses_when_duplication_grew(self, tmp_path, monkeypatch) -> None:
        repo = _repo(tmp_path, {"a": 1})
        before = (repo / ".jscpd-baseline.json").read_text(encoding="utf-8")
        code = _run(
            repo, _fake_jscpd(tmp_path, {"a": 1, "b": 1}), "--prune", monkeypatch=monkeypatch
        )
        assert code == 1
        assert (repo / ".jscpd-baseline.json").read_text(encoding="utf-8") == before

    def test_init_bootstraps_once(self, tmp_path, monkeypatch) -> None:
        repo = _repo(tmp_path, {})
        (repo / ".jscpd-baseline.json").unlink()
        runner = _fake_jscpd(tmp_path, {"a": 2})
        assert _run(repo, runner, "--init", monkeypatch=monkeypatch) == 0
        assert _run(repo, runner, "--init", monkeypatch=monkeypatch) == 2

    def test_missing_config_and_baseline_are_config_errors(self, tmp_path, monkeypatch) -> None:
        runner = _fake_jscpd(tmp_path, {})
        repo = _repo(tmp_path, {})
        (repo / ".jscpd-baseline.json").unlink()
        assert _run(repo, runner, monkeypatch=monkeypatch) == 2
        (repo / ".jscpd.json").unlink()
        assert _run(repo, runner, monkeypatch=monkeypatch) == 2

    def test_runner_failure_is_external_error(self, tmp_path, monkeypatch) -> None:
        repo = _repo(tmp_path, {})
        failing = tmp_path / "boom.py"
        failing.write_text("import sys; sys.exit(7)\n", encoding="utf-8")
        assert _run(repo, f"{sys.executable} {failing}", monkeypatch=monkeypatch) == 3

    def test_bad_root_is_config_error(self, tmp_path) -> None:
        assert gate.main([str(tmp_path / "missing")]) == 2


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


def _commit_base(repo: Path) -> None:
    """Commit the fixture with a repo-local identity; CI runners have none globally."""
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")


class TestBaseRef:
    def test_hand_added_baseline_entry_fails_against_base(self, tmp_path, monkeypatch) -> None:
        repo = _repo(tmp_path, {"a": 1})
        _commit_base(repo)
        # Branch hand-edits the baseline to cover its own new clone "b".
        (repo / ".jscpd-baseline.json").write_text(
            gate.render_baseline({"a": 1, "b": 1}), encoding="utf-8"
        )
        runner = _fake_jscpd(tmp_path, {"a": 1, "b": 1})
        assert _run(repo, runner, monkeypatch=monkeypatch) == 0
        assert _run(repo, runner, "--base-ref", "main", monkeypatch=monkeypatch) == 1
        diagnostic_baseline = json.loads(
            (tmp_path / "diagnostic-baseline.json").read_text(encoding="utf-8")
        )
        assert diagnostic_baseline["fingerprints"] == {"a": 1}

    def test_unknown_ref_is_external_error(self, tmp_path, monkeypatch) -> None:
        repo = _repo(tmp_path, {"a": 1})
        _commit_base(repo)
        runner = _fake_jscpd(tmp_path, {"a": 1})
        assert _run(repo, runner, "--base-ref", "nope", monkeypatch=monkeypatch) == 3


class TestRealJscpd:
    """Exercise the pinned detector on authored files and an intentional mirror."""

    BLOCK = "".join(f"def f{i}(a, b):\n    return a * {i} + b - {i}\n\n" for i in range(12))

    @staticmethod
    def _real_runner() -> list[str]:
        """The locked jscpd command, or a clean skip when 'npm ci' has not run."""
        try:
            return gate.resolve_runner(REPO_ROOT)
        except gate.GateError:
            pytest.skip("locked jscpd is not installed (run 'npm ci --ignore-scripts')")

    def test_deleted_recorded_clone_is_stale_and_prune_clears_it(
        self, tmp_path, monkeypatch
    ) -> None:
        """--update-baseline rewrites to current clones only, so a removed clone is stale."""
        _use_runner(monkeypatch, self._real_runner())
        repo = tmp_path / "repo"
        (repo / "scripts").mkdir(parents=True)
        shutil.copy(REPO_ROOT / ".jscpd.json", repo / ".jscpd.json")
        for name in ("first.py", "second.py"):
            (repo / "scripts" / name).write_text(self.BLOCK, encoding="utf-8")
        (repo / "scripts" / "other.py").write_text("print('x')\n" * 3, encoding="utf-8")
        assert gate.main([str(repo), "--init"]) == 0
        assert gate.main([str(repo)]) == 0
        (repo / "scripts" / "second.py").unlink()
        assert gate.main([str(repo)]) == 1
        assert gate.main([str(repo), "--prune"]) == 0
        assert gate.main([str(repo)]) == 0

    def test_injected_copy_is_caught_and_ignored_mirror_is_not(self, tmp_path, monkeypatch) -> None:
        _use_runner(monkeypatch, self._real_runner())
        repo = tmp_path / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "src" / "codex").mkdir(parents=True)
        shutil.copy(REPO_ROOT / ".jscpd.json", repo / ".jscpd.json")
        (repo / "scripts" / "metrics_writer.py").write_text(self.BLOCK, encoding="utf-8")
        (repo / "src" / "codex" / "mirror.py").write_text(self.BLOCK, encoding="utf-8")
        bundled = repo / "src" / "claude" / "skills" / "spec" / "scripts"
        bundled.mkdir(parents=True)
        (bundled / "metrics_writer.py").write_text(self.BLOCK, encoding="utf-8")
        (repo / "scripts" / "other.py").write_text("print('x')\n" * 3, encoding="utf-8")
        assert gate.main([str(repo), "--init"]) == 0
        assert gate.main([str(repo)]) == 0
        (repo / "scripts" / "copy.py").write_text(self.BLOCK, encoding="utf-8")
        assert gate.main([str(repo)]) == 1
        (repo / "scripts" / "copy.py").unlink()
        authored = repo / ".claude" / "lib"
        authored.mkdir(parents=True)
        (authored / "hand_written.py").write_text(self.BLOCK, encoding="utf-8")
        assert gate.main([str(repo)]) == 1
        (authored / "hand_written.py").unlink()
        (bundled / "authored.py").write_text(self.BLOCK, encoding="utf-8")
        assert gate.main([str(repo)]) == 1
