"""Tests for `_validate_http_url` in memory skills.

Security-critical: locks the M7 URL scheme allowlist that blocks
CWE-918 SSRF and CWE-22 file:// local file read via urllib. The same
helper is duplicated in two files (memory_router.py and
measure_memory_performance.py); both copies are tested here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(rel_path: str, name: str):
    src = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, src)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def memory_router():
    return _load_module(
        ".claude/skills/memory/memory_core/memory_router.py",
        "memory_router_under_test",
    )


@pytest.fixture(scope="module")
def measure_memory():
    return _load_module(
        ".claude/skills/memory/scripts/measure_memory_performance.py",
        "measure_memory_under_test",
    )


# Both copies share the same allowlist contract; parametrize ----------------


@pytest.fixture(params=["memory_router", "measure_memory"])
def validate(request, memory_router, measure_memory):
    mod = {"memory_router": memory_router, "measure_memory": measure_memory}[
        request.param
    ]
    return mod._validate_http_url


# Positive cases ------------------------------------------------------------


def test_accepts_http(validate) -> None:
    # measure_memory returns the endpoint; memory_router returns None.
    # Both MUST not raise.
    result = validate("http://localhost:8020/mcp")
    assert result is None or result == "http://localhost:8020/mcp"


def test_accepts_https(validate) -> None:
    result = validate("https://example.com/api")
    assert result is None or result == "https://example.com/api"


def test_accepts_http_with_port(validate) -> None:
    validate("http://10.0.0.1:8080/path")  # Should not raise.


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
    """A bare host:port has scheme='' (urlparse heuristic)."""
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


def test_allowlist_is_frozen(memory_router, measure_memory) -> None:
    """The scheme allowlist MUST be immutable (frozenset)."""
    for mod in (memory_router, measure_memory):
        assert isinstance(mod._ALLOWED_URL_SCHEMES, frozenset)
        assert mod._ALLOWED_URL_SCHEMES == {"http", "https"}
