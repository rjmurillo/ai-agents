"""Command-line tests for api_examples."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import sys
from pathlib import Path

import api_examples as ax
import pytest
from api_fixtures import SKILL_DIR, WORKED_EXAMPLE

SCRIPT = SKILL_DIR / "scripts" / "api_examples.py"


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_list_reports_examples() -> None:
    done = cli("list", str(WORKED_EXAMPLE))
    assert done.returncode == 0
    report = json.loads(done.stdout)
    assert report["count"] == 4 and report["examples"][0]["id"] == "create-order"


def test_list_touching_filters() -> None:
    report = json.loads(cli("list", str(WORKED_EXAMPLE), "--touching", "/orders/ord_9").stdout)
    assert [e["id"] for e in report["examples"]] == ["missing-order"]


def test_lint_passes_on_the_worked_example() -> None:
    done = cli("lint", str(WORKED_EXAMPLE))
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "PASS"


def test_lint_fails_on_findings(tmp_path: Path) -> None:
    doc = tmp_path / "d.md"
    doc.write_text("```http expect=200\nGET /x\n```\n", encoding="utf-8")
    done = cli("lint", str(doc))
    assert done.returncode == 1
    assert json.loads(done.stdout)["findings"][0]["code"] == "missing-id"


def test_run_end_to_end(order_api: str, tmp_path: Path) -> None:
    evidence = tmp_path / "e.json"
    done = cli("run", str(WORKED_EXAMPLE), "--base-url", order_api, "--evidence", str(evidence))
    assert done.returncode == 0
    assert json.loads(evidence.read_text(encoding="utf-8"))["verdict"] == "PASS"


def test_run_exits_one_on_a_stale_example(changed_order_api: str) -> None:
    done = cli("run", str(WORKED_EXAMPLE), "--base-url", changed_order_api)
    assert done.returncode == 1 and json.loads(done.stdout)["verdict"] == "FAIL"


def test_run_exits_two_for_a_remote_host() -> None:
    done = cli("run", str(WORKED_EXAMPLE), "--base-url", "https://api.example.com")
    assert done.returncode == 2
    assert json.loads(done.stdout)["verdict"] == "UNVERIFIED"


def test_missing_document_exits_two(tmp_path: Path) -> None:
    done = cli("lint", str(tmp_path / "nope.md"))
    assert done.returncode == 2 and "cannot read" in json.loads(done.stdout)["error"]


def test_main_returns_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert ax.main(["lint", str(WORKED_EXAMPLE)]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "PASS"


def test_script_runs_as_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "lint", str(WORKED_EXAMPLE)])
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert caught.value.code == 0


def test_main_list_in_process(capsys: pytest.CaptureFixture[str]) -> None:
    assert ax.main(["list", str(WORKED_EXAMPLE), "--touching", "/orders"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] == 4


def test_main_reports_unverified_in_process(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert ax.main(["lint", str(tmp_path / "nope.md")]) == ax.EXIT_UNVERIFIABLE
    assert json.loads(capsys.readouterr().out)["verdict"] == "UNVERIFIED"


def test_collect_requires_a_document() -> None:
    with pytest.raises(ax.InputError, match="at least one"):
        ax.cmd_list(argparse.Namespace(docs=[], touching=None))
