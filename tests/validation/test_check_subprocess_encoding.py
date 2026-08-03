"""Tests for scripts/validation/check_subprocess_encoding.py (issue #4261).

Covers:
- Positive: text mode without errors= is flagged
- Positive: encoding= without errors= is flagged
- Negative: bytes mode (no text= or encoding=) is not flagged
- Negative: text mode WITH errors= passes
- Edge: multi-line call is detected
- Edge: fixture prefix is exempted
- Vacuity: checker returns non-empty list on a known-bad input
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.check_subprocess_encoding import (
    check_file,
    main,
)


def _write(tmp_path: Path, name: str, source: str) -> Path:
    p = tmp_path / name
    p.write_text(source, encoding="utf-8")
    return p


class TestCheckFile:
    def test_text_only_flagged(self, tmp_path: Path) -> None:
        """text=True without errors= is a violation."""
        p = _write(tmp_path, "bad.py", 'subprocess.run(["cmd"], text=True)\n')
        violations = check_file(p)
        assert len(violations) == 1
        assert "errors=" in violations[0][1]

    def test_encoding_only_flagged(self, tmp_path: Path) -> None:
        """encoding= without errors= is a violation."""
        p = _write(tmp_path, "bad.py", 'subprocess.run(["cmd"], encoding="utf-8")\n')
        violations = check_file(p)
        assert len(violations) == 1

    def test_text_with_errors_clean(self, tmp_path: Path) -> None:
        """text=True with errors= is not flagged."""
        p = _write(
            tmp_path,
            "good.py",
            'subprocess.run(["cmd"], text=True, encoding="utf-8", errors="replace")\n',
        )
        assert check_file(p) == []

    def test_bytes_mode_clean(self, tmp_path: Path) -> None:
        """No text= or encoding=: bytes mode, not flagged."""
        p = _write(tmp_path, "bytes.py", 'subprocess.run(["cmd"], capture_output=True)\n')
        assert check_file(p) == []

    def test_multiline_call_detected(self, tmp_path: Path) -> None:
        """Multi-line call is detected via AST (single-line grep misses it)."""
        source = (
            "result = subprocess.run(\n"
            '    ["cmd"],\n'
            "    capture_output=True,\n"
            "    text=True,\n"
            ")\n"
        )
        p = _write(tmp_path, "multi.py", source)
        violations = check_file(p)
        assert len(violations) == 1

    def test_popen_flagged(self, tmp_path: Path) -> None:
        """subprocess.Popen is also covered."""
        p = _write(
            tmp_path,
            "popen.py",
            'proc = subprocess.Popen(["cmd"], text=True)\n',
        )
        assert len(check_file(p)) == 1

    def test_check_output_flagged(self, tmp_path: Path) -> None:
        """subprocess.check_output is also covered."""
        p = _write(
            tmp_path,
            "co.py",
            'out = subprocess.check_output(["cmd"], text=True)\n',
        )
        assert len(check_file(p)) == 1

    def test_no_subprocess_clean(self, tmp_path: Path) -> None:
        """File with no subprocess calls returns empty list."""
        p = _write(tmp_path, "noop.py", "x = 1 + 1\n")
        assert check_file(p) == []

    def test_syntax_error_raises_value_error(self, tmp_path: Path) -> None:
        """Unparseable file raises ValueError, not crashes."""
        p = _write(tmp_path, "broken.py", "def broken(\n")
        with pytest.raises(ValueError, match="syntax error"):
            check_file(p)


class TestMainVacuity:
    """Vacuity checks: checker must fail on known-bad input, not silently pass."""

    def test_known_bad_input_exits_nonzero(self, tmp_path: Path) -> None:
        """A file with text=True but no errors= causes exit 1 (not exit 0)."""
        p = _write(tmp_path, "bad.py", 'subprocess.run(["cmd"], text=True)\n')
        rc = main([str(p)])
        assert rc == 1, "checker must exit 1 on a violation, not silently pass"

    def test_known_good_input_exits_zero(self, tmp_path: Path) -> None:
        """A file with no violations exits 0."""
        p = _write(
            tmp_path,
            "good.py",
            'subprocess.run(["cmd"], text=True, encoding="utf-8", errors="replace")\n',
        )
        rc = main([str(p)])
        assert rc == 0

    def test_empty_file_list_exits_zero(self, tmp_path: Path) -> None:
        """No files to check prints a message and exits 0 (not a false green
        on bad input, just nothing to scan)."""
        rc = main([str(tmp_path / "nonexistent.py")])
        assert rc == 0

    def test_fixture_prefix_exempt(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Files under tests/hooks/fixtures/ are exempt."""
        import scripts.validation.check_subprocess_encoding as mod

        # Patch the repo root to be tmp_path so relative_to works
        fixture_dir = tmp_path / "tests" / "hooks" / "fixtures"
        fixture_dir.mkdir(parents=True)
        p = fixture_dir / "bad.py"
        p.write_text('subprocess.run(["cmd"], text=True)\n', encoding="utf-8")

        # Run check_file directly: no exemption at this level
        violations = mod.check_file(p)
        assert len(violations) == 1

        # Run main with the full path: exemption kicks in via _is_exempt
        # We need to monkeypatch the repo root detection
        import subprocess as sp
        original_run = sp.run

        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
                r = type("R", (), {"stdout": str(tmp_path) + "\n", "returncode": 0})()
                return r
            return original_run(cmd, **kwargs)

        monkeypatch.setattr(sp, "run", fake_run)
        rc = main([str(p)])
        assert rc == 0, "file under tests/hooks/fixtures/ must be exempt"


class TestNegativeControl:
    """Negative controls: clean code must not be flagged."""

    def test_errors_strict_also_passes(self, tmp_path: Path) -> None:
        """errors='strict' is explicitly OK (intentional strict decoding)."""
        p = _write(
            tmp_path,
            "strict.py",
            'subprocess.run(["cmd"], text=True, encoding="utf-8", errors="strict")\n',
        )
        assert check_file(p) == []

    def test_errors_ignore_also_passes(self, tmp_path: Path) -> None:
        """errors='ignore' is accepted by the checker (may be intentional)."""
        p = _write(
            tmp_path,
            "ignore.py",
            'subprocess.run(["cmd"], encoding="utf-8", errors="ignore")\n',
        )
        assert check_file(p) == []

    def test_bare_import_run_not_flagged_without_text(self, tmp_path: Path) -> None:
        """run() from 'from subprocess import run' without text= is bytes mode."""
        p = _write(tmp_path, "bare.py", 'run(["cmd"], capture_output=True)\n')
        assert check_file(p) == []
