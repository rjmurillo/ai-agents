from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "analyze-pr-churn.py"


def load_script():
    spec = importlib.util.spec_from_file_location("analyze_pr_churn", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_graphql_maps_payload_errors_to_external_exit(monkeypatch, capsys) -> None:
    module = load_script()

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"errors": [{"message": "bad query"}], "data": {"repository": None}}),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        module._graphql("query", {"owner": "rjmurillo"})

    assert exc.value.code == 3
    assert "GraphQL returned errors" in capsys.readouterr().err


def test_graphql_maps_timeout_to_external_exit(monkeypatch, capsys) -> None:
    module = load_script()

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["gh"], timeout=90)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        module._graphql("query", {"owner": "rjmurillo"})

    assert exc.value.code == 3
    assert "gh GraphQL failed" in capsys.readouterr().err


def test_fetch_headlines_exits_when_pull_request_is_missing(monkeypatch, capsys) -> None:
    module = load_script()
    monkeypatch.setattr(
        module,
        "_graphql",
        lambda query, variables: {"data": {"repository": {"pullRequest": None}}},
    )

    with pytest.raises(SystemExit) as exc:
        module.fetch_headlines("rjmurillo", "ai-agents", 999999)

    assert exc.value.code == 3
    assert "pull request not found" in capsys.readouterr().err


def test_main_rejects_overlapping_high_low_ranges(capsys) -> None:
    module = load_script()

    result = module.main(["--high", "10", "--low", "60"])

    assert result == 2
    assert "high > low" in capsys.readouterr().err


def test_main_analyzes_control_cohort(monkeypatch, capsys) -> None:
    module = load_script()
    analyzed: list[int] = []

    monkeypatch.setattr(
        module,
        "fetch_distribution",
        lambda owner, name: [
            {"number": 101, "commits": 61, "changedFiles": 3},
            {"number": 102, "commits": 5, "changedFiles": 2},
        ],
    )

    def fake_analyze_pr(owner: str, name: str, pr: int) -> dict:
        analyzed.append(pr)
        return {
            "pr": pr,
            "total": 1,
            "counts": {"progress": 1},
            "thrash_fraction": 0.0,
            "top": [("progress", 1)],
        }

    monkeypatch.setattr(module, "analyze_pr", fake_analyze_pr)

    result = module.main(["--high", "60", "--low", "10"])

    assert result == 0
    assert analyzed == [101, 102]
    assert "control (<10 commits)" in capsys.readouterr().out
