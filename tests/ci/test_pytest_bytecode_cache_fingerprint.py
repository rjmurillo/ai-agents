"""Tests for scripts/ci/pytest_bytecode_cache_fingerprint.py."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from scripts.ci import pytest_bytecode_cache_fingerprint as fingerprint

PYTEST_TABLE = """[tool.pytest.ini_options]
python_files = ["test_*.py"]
enable_assertion_pass_hook = false
"""


def _write_pyproject(path: Path, *, pytest_table: str = PYTEST_TABLE, extra: str = "") -> Path:
    content = f'[project]\nname = "probe"\nversion = "0.1.0"\n{extra}\n{pytest_table}'
    path.write_text(content, encoding="utf-8")
    return path


def test_unrelated_pyproject_content_does_not_rotate_the_fingerprint(tmp_path: Path) -> None:
    first = _write_pyproject(tmp_path / "first.toml")
    second = _write_pyproject(
        tmp_path / "second.toml", extra='description = "unrelated metadata"\n'
    )

    assert fingerprint.load_pytest_ini_options(first) == fingerprint.load_pytest_ini_options(second)
    assert fingerprint.fingerprint_file(first) == fingerprint.fingerprint_file(second)


def test_a_pytest_setting_change_rotates_the_fingerprint(tmp_path: Path) -> None:
    plain = _write_pyproject(tmp_path / "plain.toml")
    pass_hook = _write_pyproject(
        tmp_path / "pass-hook.toml",
        pytest_table=PYTEST_TABLE.replace("false", "true"),
    )

    assert fingerprint.fingerprint_file(plain) != fingerprint.fingerprint_file(pass_hook)


def test_the_digest_is_canonical_json_of_the_effective_inputs() -> None:
    options = {"enable_assertion_pass_hook": False, "python_files": ["test_*.py"]}
    payload = {
        "format": 1,
        "config_file": "pyproject.toml",
        "pytest_ini_options": options,
        "pytest_version": "9.2.0",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    assert fingerprint.fingerprint_options(options, "9.2.0") == hashlib.sha256(encoded).hexdigest()


def test_main_writes_a_hex_fingerprint_to_github_output(tmp_path: Path, monkeypatch) -> None:
    pyproject = _write_pyproject(tmp_path / "pyproject.toml")
    output = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    assert fingerprint.main(["--pyproject", str(pyproject)]) == 0

    line = output.read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"fingerprint=[0-9a-f]{64}", line)


def test_a_missing_pyproject_is_a_configuration_error(tmp_path: Path) -> None:
    assert fingerprint.main(["--pyproject", str(tmp_path / "missing.toml")]) == 2
