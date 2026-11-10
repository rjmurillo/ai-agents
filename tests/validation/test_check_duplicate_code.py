from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

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


def _run(repo: Path, runner: str, *args: str, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setenv("JSCPD_BIN", runner)
    return gate.main([str(repo), *args])


class TestEntryPoint:
    def test_missing_locked_runner_is_config_error_without_download(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        repo = _repo(tmp_path, {})
        monkeypatch.delenv("JSCPD_BIN", raising=False)

        def unexpected_run(*_args, **_kwargs):
            pytest.fail("a missing scanner must not launch an installer")

        monkeypatch.setattr(gate.subprocess, "run", unexpected_run)
        assert gate.main([str(repo)]) == 2
        assert "npm ci --ignore-scripts" in capsys.readouterr().err

    def test_locked_runner_is_resolved_locally(self, tmp_path, monkeypatch) -> None:
        monkeypatch.delenv("JSCPD_BIN", raising=False)
        binary = tmp_path / "node_modules" / ".bin" / "jscpd"
        binary.parent.mkdir(parents=True)
        binary.write_text("locked scanner", encoding="utf-8")
        assert gate.resolve_runner(tmp_path) == [str(binary)]

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


class TestBaseRef:
    def test_hand_added_baseline_entry_fails_against_base(self, tmp_path, monkeypatch) -> None:
        repo = _repo(tmp_path, {"a": 1})
        _git(repo, "init", "-b", "main")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "base")
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
        _git(repo, "init", "-b", "main")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "base")
        runner = _fake_jscpd(tmp_path, {"a": 1})
        assert _run(repo, runner, "--base-ref", "nope", monkeypatch=monkeypatch) == 3


class TestRealJscpd:
    """Exercise the pinned detector on authored files and an intentional mirror."""

    BLOCK = "".join(f"def f{i}(a, b):\n    return a * {i} + b - {i}\n\n" for i in range(12))

    def test_injected_copy_is_caught_and_ignored_mirror_is_not(self, tmp_path, monkeypatch) -> None:
        runner = " ".join(gate.resolve_runner(REPO_ROOT))
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
        monkeypatch.setenv("JSCPD_BIN", runner)
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
