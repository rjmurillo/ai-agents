"""Tests for scripts/eval/eval_code_review_catch_rate.py (issue #7149).

A throwaway git repository holds four introducing/fixing commit pairs. The model
seam is a plain callable, so every path runs with no API spend and no network.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
EVAL_DIR = _REPO / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from _adr_catch_rate_stats import wilson_interval  # noqa: E402


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "eval_code_review_catch_rate", EVAL_DIR / "eval_code_review_catch_rate.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cli = _load_cli()

CLASSES = ["logic-error", "edge-case", "error-handling", "resource-handling"]


def _run(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> dict:
    """Four bug/fix pairs. Pair i edits pkg/mod{i}.py; the fix swaps a distinctive line."""
    root = tmp_path / "repo"
    root.mkdir()
    _run(root, "init", "-q")
    (root / "pkg").mkdir()
    pairs = []
    for i in range(4):
        path = root / "pkg" / f"mod{i}.py"
        path.write_text(
            f"def f{i}(value):\n    return value + {i}  # BUGGY_LINE_{i}_not_checked_at_all\n"
        )
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / f"note{i}.md").write_text(f"note {i}\n")
        _run(root, "add", "-A")
        _run(root, "commit", "-q", "-m", f"feat: add module {i}")
        introducer = _run(root, "rev-parse", "HEAD")
        path.write_text(
            f"def f{i}(value):\n    return value - {i}  # REPAIRED_LINE_{i}_now_checked_with_care\n"
        )
        _run(root, "commit", "-q", "-am", f"fix: repair module {i} arithmetic")
        pairs.append((introducer, _run(root, "rev-parse", "HEAD")))
    return {"root": root, "pairs": pairs}


def _git(root: Path):
    def run(args):
        done = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return done.stdout if done.returncode == 0 else None

    return run


def _write_corpus(tmp_path: Path, repo: dict, **override) -> Path:
    entries = []
    for i, (introducer, fix) in enumerate(repo["pairs"]):
        entries.append(
            {
                "id": f"CR{i + 1:02d}",
                "introducer": introducer,
                "fix": fix,
                "introducer_ref": f"commit {introducer[:12]}",
                "link_evidence": f"fix: repair module {i} arithmetic",
                "defect": f"Module {i} adds where it should subtract.",
                "defect_files": [f"pkg/mod{i}.py"],
                "defect_class": CLASSES[i],
                "confidence": "high",
                **override,
            }
        )
    path = tmp_path / "corpus.json"
    path.write_text(
        json.dumps(
            {"schema_version": 1, "selection": {"rule": "test fixture"}, "entries": entries}
        ),
        encoding="utf-8",
    )
    return path


def _stub(prompts: list[str] | None = None):
    """Catch pairs 0 and 1, right file with the wrong class for 2, nothing for 3."""

    def call(system: str, user: str) -> str:
        if prompts is not None:
            prompts.append(system + "\n" + user)
        if "pkg/mod0.py" in user:
            return (
                "FINDING: pkg/mod0.py:2 | logic-error | Adds instead of subtracting.\nVERDICT: WARN"
            )
        if "pkg/mod1.py" in user:
            return "FINDING: pkg/mod1.py:2 | edge-case | Wrong operator.\nVERDICT: WARN"
        if "pkg/mod2.py" in user:
            return "FINDING: pkg/mod2.py:2 | security | Looks unsafe.\nVERDICT: WARN"
        return "NO FINDINGS\nVERDICT: PASS"

    return call


def _argv(corpus: Path, *extra: str) -> list[str]:
    return ["--corpus", str(corpus), "--workers", "1", *extra]


class TestDryRun:
    def test_stub_reviewer_yields_the_known_rate_and_interval(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        out = tmp_path / "results.json"

        code = cli.main(_argv(corpus, "--output", str(out)), caller=_stub(), git=_git(repo["root"]))

        result = json.loads(out.read_text(encoding="utf-8"))
        caught = result["aggregate"]["caught_top5"]
        low, high = wilson_interval(2, 4)
        assert code == 0
        assert (caught["hits"], caught["n"], caught["rate"]) == (2, 4, 0.5)
        assert caught["ci95"] == [round(low, 4), round(high, 4)]

    def test_near_miss_and_empty_findings_are_reported_apart_from_catches(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        out = tmp_path / "results.json"

        cli.main(_argv(corpus, "--output", str(out)), caller=_stub(), git=_git(repo["root"]))

        result = json.loads(out.read_text(encoding="utf-8"))
        by_id = {e["entry"]: e for e in result["entries"]}
        assert result["aggregate"]["file_only_top5"]["hits"] == 3
        assert result["aggregate"]["no_findings"] == 1
        assert (by_id["CR03"]["caught"], by_id["CR03"]["near_miss"]) == (0, 1)
        assert (by_id["CR04"]["caught"], by_id["CR04"]["no_findings"]) == (0, 1)

    def test_report_names_model_date_trials_and_rate(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        report = tmp_path / "report.md"

        cli.main(
            _argv(corpus, "--model", "stub-model", "--report", str(report)),
            caller=_stub(),
            git=_git(repo["root"]),
        )

        text = report.read_text(encoding="utf-8")
        assert "stub-model" in text and "4 entries x 1 trial" in text
        assert "2/4 (50%" in text

    def test_report_states_cost_for_a_subscription_provider(self, tmp_path, repo, monkeypatch):
        monkeypatch.setenv("EVAL_PROVIDER", "claude-cli")
        corpus = _write_corpus(tmp_path, repo)
        out = tmp_path / "results.json"
        report = tmp_path / "report.md"

        cli.main(
            _argv(corpus, "--output", str(out), "--report", str(report)),
            caller=_stub(),
            git=_git(repo["root"]),
        )

        meta = json.loads(out.read_text(encoding="utf-8"))["meta"]
        assert meta["provider"] == "claude-cli" and "subscription" in meta["cost"]
        assert "Cost: subscription" in report.read_text(encoding="utf-8")

    def test_planned_call_count_is_entries_times_trials(self, tmp_path, repo, capsys):
        corpus = _write_corpus(tmp_path, repo)

        code = cli.main(_argv(corpus, "--trials", "3", "--dry-run"), git=_git(repo["root"]))

        assert code == 0
        assert json.loads(capsys.readouterr().out) == {"entries": 4, "planned_calls": 12}

    def test_trials_multiply_calls_and_keep_the_rate(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        out = tmp_path / "results.json"
        calls: list[str] = []

        def counting(system, user):
            calls.append(user)
            return _stub()(system, user)

        cli.main(
            _argv(corpus, "--trials", "2", "--output", str(out)),
            caller=counting,
            git=_git(repo["root"]),
        )

        caught = json.loads(out.read_text(encoding="utf-8"))["aggregate"]["caught_top5"]
        assert len(calls) == 8
        assert (caught["hits"], caught["n"]) == (4, 8)


class TestParallelRun:
    def test_four_workers_write_each_job_once_to_the_checkpoint(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        out = tmp_path / "results.json"

        code = cli.main(
            ["--corpus", str(corpus), "--workers", "4", "--trials", "3"]
            + ["--checkpoint", str(checkpoint), "--output", str(out)],
            caller=_stub(),
            git=_git(repo["root"]),
        )

        rows = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()]
        keys = sorted((r["entry"], r["trial"]) for r in rows)
        expected = sorted((f"CR{i:02d}", t) for i in range(1, 5) for t in range(3))
        caught = json.loads(out.read_text(encoding="utf-8"))["aggregate"]["caught_top5"]
        assert code == 0
        assert keys == expected
        assert (caught["hits"], caught["n"]) == (6, 12)


class TestLeakGuard:
    def test_no_prompt_sent_to_the_reviewer_carries_fix_content(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        prompts: list[str] = []

        cli.main(_argv(corpus), caller=_stub(prompts), git=_git(repo["root"]))

        assert len(prompts) == 4
        for prompt in prompts:
            assert "REPAIRED_LINE" not in prompt
            assert "repair module" not in prompt
            assert not any(fix[:12] in prompt for _, fix in repo["pairs"])
            assert "BUGGY_LINE" in prompt

    def test_the_reviewer_sees_only_its_own_introducing_diff(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        prompts: list[str] = []

        cli.main(_argv(corpus), caller=_stub(prompts), git=_git(repo["root"]))

        for prompt in prompts:
            assert sum(f"BUGGY_LINE_{i}_" in prompt for i in range(4)) == 1

    def test_validate_corpus_passes_on_a_clean_corpus(self, tmp_path, repo, capsys):
        corpus = _write_corpus(tmp_path, repo)

        code = cli.main(_argv(corpus, "--validate-corpus"), git=_git(repo["root"]))

        summary = json.loads(capsys.readouterr().out)
        assert code == 0 and summary["leaks"] == {} and summary["entries"] == 4

    def test_validate_corpus_exits_2_when_the_defect_text_is_in_the_prompt(
        self, tmp_path, repo, capsys
    ):
        corpus = _write_corpus(
            tmp_path, repo, defect="return value + 0  # BUGGY_LINE_0_not_checked_at_all"
        )

        code = cli.main(_argv(corpus, "--validate-corpus"), git=_git(repo["root"]))

        assert code == 2
        assert "corpus defect description" in json.dumps(
            json.loads(capsys.readouterr().out)["leaks"]
        )


class TestFailureModes:
    def test_every_call_failing_exits_3(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)

        def failing(system, user):
            raise RuntimeError("provider down")

        assert cli.main(_argv(corpus), caller=failing, git=_git(repo["root"])) == 3

    def test_errored_calls_are_excluded_from_n_not_counted_as_misses(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        out = tmp_path / "results.json"

        def flaky(system, user):
            if "pkg/mod3.py" in user:
                raise RuntimeError("timed out")
            return _stub()(system, user)

        code = cli.main(_argv(corpus, "--output", str(out)), caller=flaky, git=_git(repo["root"]))

        agg = json.loads(out.read_text(encoding="utf-8"))["aggregate"]
        assert code == 0
        assert (agg["caught_top5"]["hits"], agg["caught_top5"]["n"], agg["errors"]) == (2, 3, 1)

    def test_unknown_entry_id_exits_2(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)

        assert (
            cli.main(_argv(corpus, "--entries", "CR99", "--dry-run"), git=_git(repo["root"])) == 2
        )

    def test_unreadable_introducer_exits_2(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)

        assert cli.main(_argv(corpus, "--dry-run"), git=lambda args: None) == 2


class TestCheckpoint:
    def test_a_rerun_with_a_checkpoint_makes_no_new_calls(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )

        def forbidden(system, user):
            raise AssertionError("model called on a finished checkpoint")

        code = cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=forbidden, git=_git(repo["root"])
        )

        assert code == 0

    def test_rescore_reads_stored_responses_with_no_model_call(self, tmp_path, repo):
        corpus = _write_corpus(tmp_path, repo)
        checkpoint = tmp_path / "rows.jsonl"
        out = tmp_path / "rescored.json"
        cli.main(
            _argv(corpus, "--checkpoint", str(checkpoint)), caller=_stub(), git=_git(repo["root"])
        )

        code = cli.main(
            _argv(corpus, "--rescore", "--checkpoint", str(checkpoint), "--output", str(out))
        )

        caught = json.loads(out.read_text(encoding="utf-8"))["aggregate"]["caught_top5"]
        assert code == 0 and (caught["hits"], caught["n"]) == (2, 4)

    def test_rescore_without_a_checkpoint_exits_2(self, tmp_path, repo):
        assert cli.main(_argv(_write_corpus(tmp_path, repo), "--rescore")) == 2


def test_report_from_renders_saved_results(tmp_path, repo, capsys):
    corpus = _write_corpus(tmp_path, repo)
    out = tmp_path / "results.json"
    cli.main(_argv(corpus, "--output", str(out)), caller=_stub(), git=_git(repo["root"]))
    capsys.readouterr()

    code = cli.main(["--report-from", str(out)])

    assert code == 0 and "Caught in top 5" in capsys.readouterr().out
