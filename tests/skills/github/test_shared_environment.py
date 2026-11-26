"""AC-DUP-6: Timeout extraction preserves existing environment parsing."""

import pytest

from scripts.github_core.environment import env_timeout_seconds


@pytest.mark.parametrize(
    "value,expected", [(None, 30), ("7", 7), ("bad", 30), ("", 30), ("-1", -1)]
)
def test_timeout_override_keeps_default_fallback(
    value: str | None, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GH_TIMEOUT_SECONDS", raising=False)
    if value is not None:
        monkeypatch.setenv("GH_TIMEOUT_SECONDS", value)
    assert env_timeout_seconds() == expected
