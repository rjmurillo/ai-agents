"""Tests for scripts/eval/eval-oneshot-vs-shipped.py CLI (issue #2788).

The CLI module has a hyphenated filename, so it is loaded via importlib. The
Anthropic transport (`_call_api`) and `_load_api_key` are monkeypatched so the
live path is exercised with zero network spend; the dry-run path is tested
directly for the zero-spend contract and exit codes.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "eval_oneshot_vs_shipped", EVAL_DIR / "eval-oneshot-vs-shipped.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


def _fixture_dict(**overrides: object) -> dict:
    base = {
        "id": "f1",
        "source_repo": "owner/repo",
        "issue_number": 10,
        "title": "Bug title",
        "discourse": "the discussion",
        "shipped_fix": "the merged fix",
        "edges_named_in_discourse": ["edge A"],
        "difficulty": 4,
    }
    base.update(overrides)
    return base


def _write_fixture(fixtures_dir: Path, name: str, **overrides: object) -> None:
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / name).write_text(
        json.dumps(_fixture_dict(**overrides)), encoding="utf-8"
    )


# --- config / exit codes -----------------------------------------------------


def test_missing_fixtures_dir_exits_config(tmp_path: Path, capsys):
    code = cli.main(["--fixtures", str(tmp_path / "none")])
    assert code == cli.EXIT_CONFIG
    assert "not a directory" in capsys.readouterr().err


def test_empty_fixtures_dir_exits_config(tmp_path: Path, capsys):
    (tmp_path / "fx").mkdir()
    code = cli.main(["--fixtures", str(tmp_path / "fx")])
    assert code == cli.EXIT_CONFIG
    assert "no fixtures" in capsys.readouterr().err


def test_malformed_fixture_exits_config(tmp_path: Path, capsys):
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "bad.json").write_text("{not json", encoding="utf-8")
    code = cli.main(["--fixtures", str(fx)])
    assert code == cli.EXIT_CONFIG


# --- dry run (zero spend) ----------------------------------------------------


def test_dry_run_lists_fixtures_and_does_not_call_api(tmp_path: Path, capsys, monkeypatch):
    fx = tmp_path / "fx"
    _write_fixture(fx, "f1.json")

    def _boom(*_a, **_k):
        raise AssertionError("dry run must not call the API")

    monkeypatch.setattr(cli, "_call_api", _boom)
    monkeypatch.setattr(cli, "_load_api_key", _boom)
    code = cli.main(["--fixtures", str(fx), "--dry-run"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "DRY RUN" in out
    assert "ZERO spend" in out
    assert "f1" in out


# --- live path (mocked transport) -------------------------------------------


def test_live_run_grades_with_mocked_judge(tmp_path: Path, capsys, monkeypatch):
    fx = tmp_path / "fx"
    _write_fixture(fx, "f1.json")

    calls = {"n": 0}

    def _fake_call(api_key, messages, **kwargs):
        calls["n"] += 1
        # First call is the agent, second is the judge.
        if calls["n"] % 2 == 1:
            return "root cause X; fix Y; acceptance Z"
        return json.dumps(
            {"grade": "FULL", "edges_caught": ["edge A"], "edges_missed": [], "reasoning": "ok"}
        )

    monkeypatch.setattr(cli, "_call_api", _fake_call)
    monkeypatch.setattr(cli, "_load_api_key", lambda: "test-key")
    code = cli.main(["--fixtures", str(fx), "--output-format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert payload["full"] == 1
    assert payload["verdict"] == "SCORED"
    assert calls["n"] == 2


def test_live_run_api_error_exits_external(tmp_path: Path, capsys, monkeypatch):
    fx = tmp_path / "fx"
    _write_fixture(fx, "f1.json")

    def _raise(*_a, **_k):
        raise RuntimeError("api down")

    monkeypatch.setattr(cli, "_call_api", _raise)
    monkeypatch.setattr(cli, "_load_api_key", lambda: "test-key")
    code = cli.main(["--fixtures", str(fx)])
    assert code == cli.EXIT_EXTERNAL
    assert "API" in capsys.readouterr().out


def test_api_error_not_counted_as_judge_failure(tmp_path: Path, capsys, monkeypatch):
    """One transport error must not inflate both api_errors and judge_failures."""
    fx = tmp_path / "fx"
    _write_fixture(fx, "f1.json")

    def _raise(*_a, **_k):
        raise RuntimeError("api down")

    monkeypatch.setattr(cli, "_call_api", _raise)
    monkeypatch.setattr(cli, "_load_api_key", lambda: "test-key")
    code = cli.main(["--fixtures", str(fx), "--output-format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_EXTERNAL
    assert payload["api_errors"] == 1
    assert payload["judge_failures"] == 0


def test_judge_parse_failure_exits_external(tmp_path: Path, capsys, monkeypatch):
    """API succeeds but the judge returns garbage: inconclusive, exit non-zero."""
    fx = tmp_path / "fx"
    _write_fixture(fx, "f1.json")

    calls = {"n": 0}

    def _fake_call(api_key, messages, **kwargs):
        calls["n"] += 1
        # Agent answers; judge returns un-parseable prose.
        return "a real fix" if calls["n"] % 2 == 1 else "I refuse to grade."

    monkeypatch.setattr(cli, "_call_api", _fake_call)
    monkeypatch.setattr(cli, "_load_api_key", lambda: "test-key")
    code = cli.main(["--fixtures", str(fx), "--output-format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_EXTERNAL
    assert payload["api_errors"] == 0
    assert payload["judge_failures"] == 1
    assert payload["verdict"] == "INCONCLUSIVE_HARNESS_ERRORS"


def test_load_api_key_failure_exits_external(tmp_path: Path, capsys, monkeypatch):
    fx = tmp_path / "fx"
    _write_fixture(fx, "f1.json")

    def _raise():
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    monkeypatch.setattr(cli, "_load_api_key", _raise)
    code = cli.main(["--fixtures", str(fx)])
    assert code == cli.EXIT_EXTERNAL
    assert "API key" in capsys.readouterr().err


def test_live_run_writes_report(tmp_path: Path, monkeypatch):
    fx = tmp_path / "fx"
    _write_fixture(fx, "f1.json")
    report = tmp_path / "reports" / "run.json"

    monkeypatch.setattr(
        cli,
        "_call_api",
        lambda *a, **k: json.dumps({"grade": "PARTIAL", "reasoning": "x"}),
    )
    monkeypatch.setattr(cli, "_load_api_key", lambda: "test-key")
    code = cli.main(["--fixtures", str(fx), "--report", str(report)])
    assert code == cli.EXIT_OK
    assert report.exists()
    assert json.loads(report.read_text())["partial"] == 1


def test_seed_fixture_is_valid_and_dry_runs(capsys):
    """The shipped seed corpus must load and dry-run cleanly."""
    seed_dir = EVAL_DIR.parents[1] / "evals" / "oneshot-vs-shipped" / "fixtures"
    code = cli.main(["--fixtures", str(seed_dir), "--dry-run"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "moq1208-1091" in out
