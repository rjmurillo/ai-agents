#!/usr/bin/env python3
"""Tests for the defect_lineage CLI and its git probe (issue #5638)."""

from __future__ import annotations

import json
import re
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_METRICS_DIR = str(Path(__file__).resolve().parent)
SKILL_METRICS_DIR = str(Path(__file__).resolve().parents[3] / ".claude" / "skills" / "metrics")
for _entry in (TESTS_METRICS_DIR, SKILL_METRICS_DIR):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import defect_lineage as cli
import defect_lineage_record as rec
from lineage_test_helpers import PROJECT_ROOT, SHA_A, SHA_B, SKILL_DIR, fixed_chain

SHIPPED = PROJECT_ROOT / ".project-toolkit" / "metrics" / "lineage"


def write(path: Path, record) -> Path:
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def run(argv, prober=None, now=lambda: "2026-10-14T00:00:00Z"):
    lines: list[str] = []
    kwargs = {"out": lines.append, "now": now}
    if prober is not None:
        kwargs["prober"] = prober
    code = cli.run(argv, **kwargs)
    return code, lines


def fixed_prober(state):
    def prober(root, rev, record, checked_at):
        return rec.Probe(state, SHA_B, checked_at, f"{state} at {rev}")

    return prober


class TestCheck:
    def test_valid_file_and_directory(self, tmp_path):
        write(tmp_path / "a.json", fixed_chain())
        assert run(["check", str(tmp_path / "a.json")]) == (0, [])
        assert run(["check", str(tmp_path)]) == (0, [])

    def test_invalid_record_prints_each_problem_and_exits_1(self, tmp_path):
        bad = fixed_chain()
        bad["status"] = "CURRENT"
        path = write(tmp_path / "bad.json", bad)
        code, lines = run(["check", str(path)])
        assert code == 1
        assert lines and all(line.startswith(f"{path}: ") for line in lines)

    def test_missing_path_is_config_error(self, tmp_path, capsys):
        assert run(["check", str(tmp_path / "none.json")])[0] == 2
        assert "no such record file" in capsys.readouterr().err

    def test_empty_directory_is_config_error(self, tmp_path):
        assert run(["check", str(tmp_path)])[0] == 2

    def test_unreadable_json_is_config_error(self, tmp_path, capsys):
        path = tmp_path / "x.json"
        path.write_text("{not json", encoding="utf-8")
        assert run(["check", str(path)])[0] == 2
        assert "cannot read" in capsys.readouterr().err

    def test_non_object_json_is_config_error(self, tmp_path):
        path = tmp_path / "x.json"
        path.write_text("[1]", encoding="utf-8")
        assert run(["check", str(path)])[0] == 2

    def test_duplicate_paths_are_checked_once(self, tmp_path):
        path = write(tmp_path / "a.json", fixed_chain())
        assert cli.expand_paths([str(path), str(tmp_path)]) == [path]


class TestReport:
    def test_markdown_for_explicit_path(self, tmp_path):
        write(tmp_path / "a.json", fixed_chain())
        code, lines = run(["report", str(tmp_path)])
        assert code == 0
        assert "## Historical mechanism evidence (not live)" in lines[0]

    def test_json_output(self, tmp_path):
        write(tmp_path / "a.json", fixed_chain())
        code, lines = run(["report", str(tmp_path), "--output-format", "json"])
        assert code == 0
        assert json.loads(lines[0])["counts"]["historical"] == 1

    def test_report_without_a_path_is_an_argument_error(self):
        with pytest.raises(SystemExit) as exit_info:
            run(["report"])
        assert exit_info.value.code == 2

    def test_invalid_record_exits_1(self, tmp_path):
        write(tmp_path / "a.json", {"id": "x"})
        code, lines = run(["report", str(tmp_path)])
        assert code == 1 and lines[0].startswith("invalid: ")


class TestRecheck:
    def test_prints_transition_without_writing(self, tmp_path):
        path = write(tmp_path / "a.json", fixed_chain())
        before = path.read_text(encoding="utf-8")
        code, lines = run(["recheck", str(path)], prober=fixed_prober("present"))
        assert code == 0
        assert lines[0] == f"pr-5623-chain: FIXED -> CURRENT at {SHA_B}"
        assert lines[1].startswith("basis: claim holds")
        assert path.read_text(encoding="utf-8") == before

    def test_write_appends_history_and_keeps_chain(self, tmp_path):
        original = fixed_chain()
        path = write(tmp_path / "a.json", original)
        code, lines = run(["recheck", str(path), "--write"], prober=fixed_prober("absent"))
        assert code == 0 and lines[-1] == f"wrote {path}"
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert path.read_text(encoding="utf-8").endswith("}\n")
        assert saved["status"] == "FIXED"
        assert saved["status_history"][:2] == original["status_history"]
        assert len(saved["status_history"]) == 3
        assert saved["introduction"] == original["introduction"]

    def test_default_rev_is_origin_default_branch(self, tmp_path):
        seen = []

        def prober(root, rev, record, checked_at):
            seen.append(rev)
            return rec.Probe("present", SHA_A, checked_at, "d")

        path = write(tmp_path / "a.json", fixed_chain())
        run(["recheck", str(path)], prober=prober)
        run(["recheck", str(path), "--rev", "feature/x"], prober=prober)
        assert seen == ["origin/main", "feature/x"]

    @pytest.mark.parametrize("rev", ["--upload-pack=x", "-x", "a b", "a;b", "$(x)"])
    def test_unsafe_revision_is_config_error(self, tmp_path, rev):
        path = write(tmp_path / "a.json", fixed_chain())
        assert run(["recheck", str(path), f"--rev={rev}"], prober=fixed_prober("present"))[0] == 2

    def test_stale_clock_exits_1(self, tmp_path):
        path = write(tmp_path / "a.json", fixed_chain())
        code, lines = run(
            ["recheck", str(path)],
            prober=fixed_prober("present"),
            now=lambda: "2026-10-13T11:00:00Z",
        )
        assert code == 1 and "later than the last" in lines[0]

    def test_invalid_record_exits_1(self, tmp_path):
        path = write(tmp_path / "a.json", {"id": "x"})
        assert run(["recheck", str(path)], prober=fixed_prober("present"))[0] == 1

    def test_external_error_exits_3(self, tmp_path, capsys):
        def broken(root, rev, record, checked_at):
            raise cli.ExternalError("git exploded")

        path = write(tmp_path / "a.json", fixed_chain())
        assert run(["recheck", str(path)], prober=broken)[0] == 3
        assert "external error: git exploded" in capsys.readouterr().err


def git(root, *args):
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": __import__("os").environ["PATH"],
        },
    )


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "scripts" / "x.py").write_text("ok\nbug_line = 1\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "introduce")
    git(root, "tag", "introduced")
    (root / "scripts" / "x.py").write_text("ok\nfixed = 1\n", encoding="utf-8")
    git(root, "commit", "-q", "-am", "fix")
    return root


class TestProbeGit:
    def test_pattern_present_at_the_introducing_commit(self, repo):
        probe = cli.probe_git(repo, "introduced", fixed_chain(), "2026-10-14T00:00:00Z")
        assert probe.state == "present"
        assert re.fullmatch(r"[0-9a-f]{40}", probe.live_sha)

    def test_pattern_absent_after_the_fix(self, repo):
        probe = cli.probe_git(repo, "main", fixed_chain(), "2026-10-14T00:00:00Z")
        assert probe.state == "absent"

    def test_missing_path_is_unavailable_not_absent(self, repo):
        record = fixed_chain()
        record["recheck"]["path"] = "scripts/moved.py"
        probe = cli.probe_git(repo, "main", record, "2026-10-14T00:00:00Z")
        assert probe.state == "unavailable" and "is missing at" in probe.detail

    def test_unresolved_revision_is_external_error(self, repo):
        with pytest.raises(cli.ExternalError, match="does not resolve"):
            cli.probe_git(repo, "no-such-ref", fixed_chain(), "2026-10-14T00:00:00Z")

    def test_show_failure_is_unavailable(self, repo, monkeypatch):
        real = cli._git

        def flaky(root, *args):
            if args[0] == "show":
                return subprocess.CompletedProcess(args, 128, b"", b"boom")
            return real(root, *args)

        monkeypatch.setattr(cli, "_git", flaky)
        probe = cli.probe_git(repo, "main", fixed_chain(), "2026-10-14T00:00:00Z")
        assert probe.state == "unavailable" and "git show failed" in probe.detail

    def test_missing_git_binary_is_external_error(self, repo, monkeypatch):
        def no_git(*args, **kwargs):
            raise FileNotFoundError("git")

        monkeypatch.setattr(cli.subprocess, "run", no_git)
        with pytest.raises(cli.ExternalError, match="git failed to run"):
            cli.probe_git(repo, "main", fixed_chain(), "2026-10-14T00:00:00Z")

    def test_timeout_is_external_error(self, repo, monkeypatch):
        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired("git", 30)

        monkeypatch.setattr(cli.subprocess, "run", slow)
        with pytest.raises(cli.ExternalError):
            cli.probe_git(repo, "main", fixed_chain(), "2026-10-14T00:00:00Z")

    def test_end_to_end_recheck_moves_current_to_fixed_and_keeps_history(self, repo, tmp_path):
        record = fixed_chain()
        record["status"] = "CURRENT"
        record["status_history"] = record["status_history"][:1]
        record["status_history"][0]["status"] = "CURRENT"
        path = write(tmp_path / "a.json", record)
        lines: list[str] = []
        code = cli.run(
            ["--root", str(repo), "recheck", str(path), "--rev", "main", "--write"],
            out=lines.append,
            now=lambda: "2026-10-14T00:00:00Z",
        )
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert code == 0
        assert saved["status"] == "FIXED"
        assert [e["status"] for e in saved["status_history"]] == ["CURRENT", "FIXED"]


class TestUtcNow:
    def test_format_is_seconds_resolution_utc(self):
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", cli.utc_now())


class TestScriptEntryPoint:
    def test_main_guard_exits_with_the_run_code(self, tmp_path, monkeypatch):
        path = write(tmp_path / "a.json", fixed_chain())
        monkeypatch.setattr(sys, "argv", ["defect_lineage.py", "check", str(path)])
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_path(str(SKILL_DIR / "defect_lineage.py"), run_name="__main__")
        assert exit_info.value.code == 0


class TestSiblingImportBootstrap:
    """Importing by file path, as import_skill_script does, must find the sibling modules."""

    def stripped_path(self, monkeypatch):
        keep = [p for p in sys.path if Path(p or ".").resolve() != SKILL_DIR]
        monkeypatch.setattr(sys, "path", keep)

    def test_cli_adds_its_own_directory(self, monkeypatch):
        self.stripped_path(monkeypatch)
        runpy.run_path(str(SKILL_DIR / "defect_lineage.py"), run_name="not_main")
        assert str(SKILL_DIR) in sys.path

    def test_report_adds_its_own_directory(self, monkeypatch):
        self.stripped_path(monkeypatch)
        runpy.run_path(str(SKILL_DIR / "defect_lineage_report.py"), run_name="not_main")
        assert str(SKILL_DIR) in sys.path


class TestShippedRecords:
    def test_every_shipped_record_is_valid(self):
        assert run(["check", str(SHIPPED)]) == (0, [])

    def test_planned_chain_is_not_labeled_a_defect(self):
        record = json.loads((SHIPPED / "pr-5547-codex-probers-planned-follow-up.json").read_text())
        assert record["supports"] == ["observation"]
        assert record["follow_up"]["kind"] == "planned_work"

    def test_5623_chain_keeps_seconds_level_ordering_and_is_not_live(self):
        record = json.loads((SHIPPED / "pr-5623-concurrency-review-race.json").read_text())
        assert record["introduction"]["merged_at"] == "2026-09-06T22:23:33Z"
        assert record["detection"]["at"] == "2026-09-06T22:23:38Z"
        assert rec.detection_delay_seconds(record) == 5
        assert record["follow_up"]["pr"] == 5630
        assert record["status"] == "FIXED"
        assert record["status_history"][0]["status"] == "CURRENT"

    def test_report_places_5623_chain_outside_the_live_bucket(self):
        code, lines = run(["report", str(SHIPPED), "--output-format", "json"])
        summary = json.loads(lines[0])
        live_ids = [e["id"] for e in summary["buckets"]["live"]]
        assert code == 0
        assert "pr-5623-concurrency-review-race" not in live_ids
