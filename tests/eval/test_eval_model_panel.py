"""Tests for scripts/eval/eval-model-panel.py CLI (issue #3042).

The hyphenated CLI module is loaded via importlib. The harness runner seam is
injected so the sweep is exercised with zero API spend.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import shlex
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
PANEL_SCRIPT = "eval-model-panel.py"
PANELS_DIR = EVAL_DIR / "panels"
OWNER_PANEL_CONFIG = PANELS_DIR / "owner-copilot-cli.json"
README = EVAL_DIR / "README.md"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "eval_model_panel", EVAL_DIR / "eval-model-panel.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


def _capturing_subprocess_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "run"
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
        ):
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg is not None}
        capture_output = keywords.get("capture_output")
        if isinstance(capture_output, ast.Constant) and capture_output.value is True:
            calls.append(node)
    return calls


def test_panel_and_router_subprocess_readers_pin_utf8_decoding():
    for filename in ("eval-model-panel.py", "eval_skill_router.py"):
        calls = _capturing_subprocess_calls(EVAL_DIR / filename)
        assert calls, f"{filename} has no captured subprocess readers"
        for call in calls:
            keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
            encoding = keywords.get("encoding")
            errors = keywords.get("errors")
            assert isinstance(encoding, ast.Constant)
            assert encoding.value == "utf-8"
            assert isinstance(errors, ast.Constant)
            assert errors.value == "replace"


def _fake_runner(deltas):
    """Runner that returns a report.json with recall_delta from deltas[(unit,tier)]."""
    def run(unit, tier, n_runs, fixtures):
        key = (unit, tier.label)
        if key not in deltas:
            raise RuntimeError(f"no fake result for {key}")
        return {
            "error_count": 0,
            "recall_delta": deltas[key],
            "bootstrap_ci_95": [0.0, 1.0],
        }
    return run


def test_dry_run_zero_spend(capsys):
    code = cli.main(["--agents", "qa", "--dry-run"])
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "DRY RUN" in out
    assert "ZERO spend" in out
    assert "qa @ opus" in out


def _panel_argv(tokens: list[str]) -> list[str]:
    """Argv after the script name, with repo-relative config paths resolved."""
    script = next(i for i, t in enumerate(tokens) if t.endswith(PANEL_SCRIPT))
    repo_root = EVAL_DIR.parents[1]
    return [
        str(repo_root / token) if token.endswith(".json") else token
        for token in tokens[script + 1:]
    ]


def _panel_config_usage_commands() -> list[tuple[str, list[str]]]:
    """(source, argv) for the `Usage:` line each shipped panel config carries."""
    return [
        (path.name, _panel_argv(shlex.split(line[len("Usage: "):])))
        for path in sorted(PANELS_DIR.glob("*.json"))
        for line in json.loads(path.read_text(encoding="utf-8")).get("_comment", [])
        if line.startswith("Usage: ") and PANEL_SCRIPT in line
    ]


def _is_shell_invocation(line: str) -> bool:
    """True for a line that runs something, not a table row or prose mention.

    The README writes commands both as `python3 scripts/eval/<name>.py` and as
    a bare `scripts/eval/<name>.py`, so both leading forms count. A prose
    mention wraps the script in backticks, which fails both tests.
    """
    head = line.split(maxsplit=1)
    return bool(head) and (
        head[0].endswith(".py") or head[0] in ("python", "python3", "uv")
    )


def _readme_commands() -> list[tuple[str, list[str]]]:
    """(source, argv) for every panel invocation the eval README documents."""
    # Join shell line continuations first: a documented command spans lines.
    prose = README.read_text(encoding="utf-8").replace("\\\n", " ")
    return [
        (f"{README.name}: {line.strip()}", _panel_argv(shlex.split(line)))
        for line in prose.splitlines()
        if PANEL_SCRIPT in line and _is_shell_invocation(line)
    ]


def documented_panel_commands() -> list[tuple[str, list[str]]]:
    """Every eval-model-panel.py command this repository tells a reader to run."""
    return _panel_config_usage_commands() + _readme_commands()


def test_documented_panel_commands_name_both_known_sources() -> None:
    # Guards the test below from passing vacuously: a renamed README or panels
    # directory would otherwise leave the extractor returning an empty list.
    sources = {source.split(":")[0] for source, _ in documented_panel_commands()}
    assert {OWNER_PANEL_CONFIG.name, README.name} <= sources, sources


def _dry_run_exit_code(argv: list[str]) -> int:
    """Exit code for a documented argv, including the one argparse raises.

    A missing required flag leaves `main` through `SystemExit` rather than a
    return, so catching it is what lets the assertion below name the document
    that carries the broken command instead of reporting a bare `SystemExit`.
    """
    try:
        return cli.main([*argv, "--dry-run"])
    except SystemExit as exit_signal:
        return int(exit_signal.code or 0)


def test_documented_panel_commands_run(capsys):
    # Issue #3905: both scripts/eval/panels/owner-copilot-cli.json and
    # scripts/eval/README.md documented `--panel-config ...` with no --agents.
    # argparse marks --agents required, so every copy-paste of either exited 2.
    for source, argv in documented_panel_commands():
        code = _dry_run_exit_code(argv)

        out = capsys.readouterr().out
        assert code == cli.EXIT_OK, f"{source} -> exit {code}"
        assert "orchestrator @ opus5" in out, f"{source} -> {out}"


def test_bad_n_runs_exits_config(capsys):
    code = cli.main(["--agents", "qa", "--n-runs", "0", "--dry-run"])
    assert code == cli.EXIT_CONFIG
    assert "n-runs" in capsys.readouterr().err


def test_bad_panel_config_exits_config(tmp_path, capsys):
    cfg = tmp_path / "panel.json"
    cfg.write_text('{"tiers": []}', encoding="utf-8")
    code = cli.main(["--agents", "qa", "--panel-config", str(cfg), "--dry-run"])
    assert code == cli.EXIT_CONFIG


def test_live_sweep_reports_degradation(capsys):
    deltas = {
        ("qa", "opus"): 0.5, ("qa", "sol"): 0.5,
        ("qa", "sonnet"): 0.2, ("qa", "terra"): 0.45,
    }
    code = cli.main(
        ["--agents", "qa", "--output-format", "json"],
        runner=_fake_runner(deltas),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    unit = payload["units"][0]
    assert unit["unit"] == "qa"
    assert "sonnet" in unit["degraded_tiers"]
    assert unit["robust"] is False


def test_live_sweep_robust_unit(capsys):
    deltas = {
        ("qa", "opus"): 0.5, ("qa", "sol"): 0.5,
        ("qa", "sonnet"): 0.48, ("qa", "terra"): 0.47,
    }
    code = cli.main(
        ["--agents", "qa", "--output-format", "json"],
        runner=_fake_runner(deltas),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert payload["units"][0]["robust"] is True


def test_runner_error_records_cell_and_exits_external(capsys):
    # Missing terra result -> that cell errors -> exit 3, but others still scored.
    deltas = {
        ("qa", "opus"): 0.5, ("qa", "sol"): 0.5, ("qa", "sonnet"): 0.5,
    }
    code = cli.main(
        ["--agents", "qa", "--output-format", "json"],
        runner=_fake_runner(deltas),
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_EXTERNAL
    # terra missing -> unit incomplete
    assert payload["units"][0]["incomplete"] is True


def test_report_written(tmp_path):
    deltas = {
        ("qa", "opus"): 0.5, ("qa", "sol"): 0.5,
        ("qa", "sonnet"): 0.5, ("qa", "terra"): 0.5,
    }
    report = tmp_path / "reports" / "panel.json"
    code = cli.main(
        ["--agents", "qa", "--report", str(report)],
        runner=_fake_runner(deltas),
    )
    assert code == cli.EXIT_OK
    assert json.loads(report.read_text())["units"][0]["robust"] is True
