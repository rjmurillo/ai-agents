"""Tests for check_spec_failures.py consumer script."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import the consumer script via importlib (not a package)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / ".github" / "scripts"


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None, f"Could not load spec for {name}"
    assert spec.loader is not None, f"Spec for {name} has no loader"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("check_spec_failures")
main = _mod.main
build_parser = _mod.build_parser


# ---------------------------------------------------------------------------
# Tests: build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_defaults_to_empty(self, monkeypatch):
        monkeypatch.delenv("TRACE_VERDICT", raising=False)
        monkeypatch.delenv("COMPLETENESS_VERDICT", raising=False)
        args = build_parser().parse_args([])
        assert args.trace_verdict == ""
        assert args.completeness_verdict == ""

    def test_cli_args_override(self):
        args = build_parser().parse_args([
            "--trace-verdict", "PASS",
            "--completeness-verdict", "FAIL",
        ])
        assert args.trace_verdict == "PASS"
        assert args.completeness_verdict == "FAIL"

    def test_env_vars_used_as_defaults(self, monkeypatch):
        monkeypatch.setenv("TRACE_VERDICT", "WARN")
        monkeypatch.setenv("COMPLETENESS_VERDICT", "PASS")
        args = build_parser().parse_args([])
        assert args.trace_verdict == "WARN"
        assert args.completeness_verdict == "PASS"


# ---------------------------------------------------------------------------
# Tests: main
# ---------------------------------------------------------------------------


class TestMain:
    def test_both_pass_returns_0(self, capsys):
        rc = main(["--trace-verdict", "PASS", "--completeness-verdict", "PASS"])
        assert rc == 0
        assert "passed" in capsys.readouterr().out.lower()

    def test_trace_fail_returns_1(self):
        rc = main(["--trace-verdict", "FAIL", "--completeness-verdict", "PASS"])
        assert rc == 1

    def test_completeness_fail_returns_1(self):
        rc = main(["--trace-verdict", "PASS", "--completeness-verdict", "FAIL"])
        assert rc == 1

    def test_both_fail_returns_1(self):
        rc = main(["--trace-verdict", "FAIL", "--completeness-verdict", "FAIL"])
        assert rc == 1

    def test_critical_fail_returns_1(self):
        rc = main([
            "--trace-verdict", "CRITICAL_FAIL",
            "--completeness-verdict", "PASS",
        ])
        assert rc == 1

    def test_both_empty_returns_0(self):
        """Empty verdicts are not failures."""
        rc = main(["--trace-verdict", "", "--completeness-verdict", ""])
        assert rc == 0

    def test_warn_is_not_failure(self):
        rc = main(["--trace-verdict", "WARN", "--completeness-verdict", "WARN"])
        assert rc == 0

    def test_error_message_on_failure(self, capsys):
        main(["--trace-verdict", "FAIL", "--completeness-verdict", "PASS"])
        captured = capsys.readouterr()
        assert "Spec validation failed" in captured.out
