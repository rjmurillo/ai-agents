"""Tests for `validate_http_url` in the memory skill.

Security-critical: locks the M7 URL scheme allowlist that blocks
CWE-918 SSRF and CWE-22 file:// local file read via urllib. The helper
lives in `.claude/skills/memory/memory_core/url_validation.py` and is
imported by both `memory_router.py` and `measure_memory_performance.py`.
This test exercises the helper directly (single source of truth) and
asserts that both consumers import the same name.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
URL_VALIDATION_PATH = (
    REPO_ROOT / ".claude" / "skills" / "memory" / "memory_core" / "url_validation.py"
)


def _load_standalone(rel_path: Path, name: str):
    """Load a Python module from a path with no relative-import context.

    Suitable only for modules that do NOT use relative imports themselves.
    """
    spec = importlib.util.spec_from_file_location(name, rel_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def url_validation():
    return _load_standalone(URL_VALIDATION_PATH, "url_validation_under_test")


@pytest.fixture
def validate(url_validation):
    return url_validation.validate_http_url


# Positive cases ------------------------------------------------------------


def test_accepts_http(validate) -> None:
    assert validate("http://localhost:8020/mcp") == "http://localhost:8020/mcp"


def test_accepts_https(validate) -> None:
    assert validate("https://example.com/api") == "https://example.com/api"


def test_accepts_http_with_port(validate) -> None:
    assert (
        validate("http://10.0.0.1:8080/path") == "http://10.0.0.1:8080/path"
    )


# Negative: blocked schemes -------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "file://localhost/etc/passwd",
        "ftp://attacker.example.com/x",
        "gopher://attacker.example.com/",
        "dict://attacker.example.com:11111/",
        "ldap://attacker.example.com/",
        "javascript:alert(1)",
        "data:text/plain,hi",
        "sftp://example.com/",
    ],
)
def test_rejects_dangerous_schemes(validate, url: str) -> None:
    """Every non-http(s) scheme MUST raise ValueError.

    Without this gate, urllib.urlopen would happily read local files via
    file:// (CWE-22) or reach unintended services (CWE-918 SSRF).
    """
    with pytest.raises(ValueError, match="scheme"):
        validate(url)


# Negative: malformed input -------------------------------------------------


def test_rejects_empty_string(validate) -> None:
    """urlparse('') yields scheme='' which is not in the allowlist."""
    with pytest.raises(ValueError, match="scheme"):
        validate("")


def test_rejects_no_scheme(validate) -> None:
    """A bare host:port may parse with scheme='localhost' or '' depending
    on the value; either is rejected."""
    with pytest.raises(ValueError, match="scheme"):
        validate("localhost:8080/path")


def test_rejects_only_path(validate) -> None:
    with pytest.raises(ValueError, match="scheme"):
        validate("/etc/passwd")


# Boundary: scheme value in error message -----------------------------------


def test_error_message_includes_rejected_scheme(validate) -> None:
    with pytest.raises(ValueError) as exc_info:
        validate("file:///etc/passwd")
    assert "file" in str(exc_info.value)


def test_allowlist_is_frozen(url_validation) -> None:
    """The scheme allowlist MUST be immutable (frozenset)."""
    assert isinstance(url_validation.ALLOWED_URL_SCHEMES, frozenset)
    assert url_validation.ALLOWED_URL_SCHEMES == {"http", "https"}


# Consumer-side smoke: both downstream modules MUST import the helper -------


def test_memory_router_imports_validate_http_url() -> None:
    """memory_router uses `from .url_validation import validate_http_url`;
    verify the symbol is exported from the canonical module."""
    text = (
        REPO_ROOT
        / ".claude"
        / "skills"
        / "memory"
        / "memory_core"
        / "memory_router.py"
    ).read_text(encoding="utf-8")
    assert "from .url_validation import validate_http_url" in text


def test_measure_memory_imports_validate_http_url() -> None:
    """measure_memory_performance uses
    `from memory_core.url_validation import validate_http_url`."""
    text = (
        REPO_ROOT
        / ".claude"
        / "skills"
        / "memory"
        / "scripts"
        / "measure_memory_performance.py"
    ).read_text(encoding="utf-8")
    assert "from memory_core.url_validation import validate_http_url" in text
