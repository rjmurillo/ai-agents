"""Tests for scripts/metrics/sg_reference_ab_api.py (#5856, REQ-8 support).

Credential/model resolution, plugin-contract loading, the Messages API
transport, and failure classification (module docstring citation 3: the
Claude API's documented error shape and the auth/billing status set). Split
out of ``tests/metrics/test_sg_reference_ab.py`` under the taste-lints
file-size gate; the tool loop built on this transport is tested in the
sibling ``tests/metrics/test_sg_reference_ab_toolloop.py``.

All network access is mocked: every test that reaches ``post_messages``
patches ``urllib.request.urlopen`` with a scripted fake transport. No test
performs a live Anthropic API call.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.metrics import sg_reference_ab_api as api
from tests.metrics.sg_reference_ab_helpers import (
    http_error,
    make_fake_urlopen,
    plugin_hooks_dir,
    write_stub_plugin,
)

# ---------------------------------------------------------------------------
# default_model / load_api_key
# ---------------------------------------------------------------------------


def test_default_model_imports_from_the_real_anthropic_api_module() -> None:
    assert api.default_model() == "claude-sonnet-5"


def test_default_model_falls_back_when_anthropic_api_file_absent(tmp_path: Path) -> None:
    assert api.default_model(eval_dir=tmp_path) == api.FALLBACK_MODEL


def test_default_model_falls_back_when_import_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A prior test may have cached the real module under this bare name;
    # importlib.import_module would then return the cached module instead of
    # re-executing this broken one, silently defeating the assertion.
    monkeypatch.delitem(__import__("sys").modules, "_anthropic_api", raising=False)
    (tmp_path / "_anthropic_api.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")

    assert api.default_model(eval_dir=tmp_path) == api.FALLBACK_MODEL


def test_default_model_reuses_sys_path_entry_already_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys as _sys

    monkeypatch.delitem(_sys.modules, "_anthropic_api", raising=False)
    (tmp_path / "_anthropic_api.py").write_text(
        "DEFAULT_MODEL = 'already-on-path'\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    assert api.default_model(eval_dir=tmp_path) == "already-on-path"
    # Reused entries are not removed by default_model's own cleanup.
    assert str(tmp_path) in _sys.path


def test_load_api_key_prefers_environment_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  from-env  ")

    assert api.load_api_key(tmp_path) == "from-env"


def test_load_api_key_reads_repo_root_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "# comment\n\nOTHER_VAR=1\nANTHROPIC_API_KEY=\"from-env-file\"\n", encoding="utf-8"
    )

    assert api.load_api_key(tmp_path) == "from-env-file"


def test_load_api_key_returns_none_when_env_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert api.load_api_key(tmp_path) is None


def test_load_api_key_returns_none_when_env_file_is_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    real = tmp_path / "real.env"
    real.write_text("ANTHROPIC_API_KEY=leaked\n", encoding="utf-8")
    (tmp_path / ".env").symlink_to(real)

    assert api.load_api_key(tmp_path) is None


def test_load_api_key_reads_unquoted_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=unquoted-value\n", encoding="utf-8")

    assert api.load_api_key(tmp_path) == "unquoted-value"


def test_load_api_key_returns_none_when_key_not_present_in_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text("SOME_OTHER_VAR=1\n", encoding="utf-8")

    assert api.load_api_key(tmp_path) is None


# ---------------------------------------------------------------------------
# Plugin contract loading (provenance)
# ---------------------------------------------------------------------------


def test_load_plugin_contract_happy_path(tmp_path: Path) -> None:
    hooks_dir = write_stub_plugin(tmp_path)

    contract = api.load_plugin_contract(hooks_dir)

    assert contract.system == "system prompt for tests"
    assert contract.findings_schema["required"] == ["findings"]
    assert len(contract.review_api_sha256) == 64
    assert len(contract.llm_sha256) == 64
    assert contract.plugin_version == "9.9.9"


def test_load_plugin_contract_missing_version_file(tmp_path: Path) -> None:
    hooks_dir = write_stub_plugin(tmp_path, with_version=False)

    contract = api.load_plugin_contract(hooks_dir)

    assert contract.plugin_version is None


def test_load_plugin_contract_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(api.PluginContractError, match="missing review_api.py"):
        api.load_plugin_contract(tmp_path / "does-not-exist")


def test_load_plugin_contract_missing_symbols(tmp_path: Path) -> None:
    hooks_dir = write_stub_plugin(tmp_path, valid=False)

    with pytest.raises(api.PluginContractError, match="did not define"):
        api.load_plugin_contract(hooks_dir)


def test_load_plugin_contract_raises_on_broken_review_api(tmp_path: Path) -> None:
    hooks_dir = write_stub_plugin(tmp_path)
    (hooks_dir / "review_api.py").write_text(
        "raise RuntimeError('broken module')\n", encoding="utf-8"
    )

    with pytest.raises(api.PluginContractError, match="failed importing"):
        api.load_plugin_contract(hooks_dir)


def test_load_plugin_contract_malformed_plugin_json_is_tolerated(tmp_path: Path) -> None:
    hooks_dir = write_stub_plugin(tmp_path)
    plugin_json = hooks_dir.parent / ".claude-plugin" / "plugin.json"
    plugin_json.write_text("{not valid json", encoding="utf-8")

    contract = api.load_plugin_contract(hooks_dir)

    assert contract.plugin_version is None


def test_load_plugin_contract_raises_when_spec_cannot_be_built(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hooks_dir = write_stub_plugin(tmp_path)
    monkeypatch.setattr(api.importlib.util, "spec_from_file_location", lambda *a, **k: None)

    with pytest.raises(api.PluginContractError, match="could not load review_api.py"):
        api.load_plugin_contract(hooks_dir)


def test_load_plugin_contract_reuses_hooks_dir_already_on_sys_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sys as _sys

    hooks_dir = write_stub_plugin(tmp_path)
    monkeypatch.syspath_prepend(str(hooks_dir))

    contract = api.load_plugin_contract(hooks_dir)

    assert contract.system == "system prompt for tests"
    assert str(hooks_dir) in _sys.path


@pytest.mark.skipif(
    not plugin_hooks_dir.is_dir(),
    reason="security-guidance plugin not installed locally; provenance check skipped",
)
def test_load_plugin_contract_against_real_installed_plugin() -> None:
    contract = api.load_plugin_contract(plugin_hooks_dir)

    assert "senior application-security engineer" in contract.system
    assert contract.findings_schema["required"] == ["findings"]
    assert contract.plugin_version == "2.0.8"


# ---------------------------------------------------------------------------
# post_messages: transport and retries
# ---------------------------------------------------------------------------


def test_post_messages_returns_parsed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, calls = make_fake_urlopen([{"content": [], "usage": {}}])
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = api.post_messages("key", "model", "system", [], [])

    assert result == {"content": [], "usage": {}}
    assert len(calls) == 1


def test_post_messages_retries_once_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, calls = make_fake_urlopen([http_error(429), {"content": [], "usage": {}}])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    slept = _record_sleeps(monkeypatch)

    result = api.post_messages("key", "model", "system", [], [])

    assert result == {"content": [], "usage": {}}
    assert len(calls) == 2
    assert len(slept) == 1


def test_post_messages_retries_once_on_5xx_then_raises_if_still_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake, calls = make_fake_urlopen([http_error(503), http_error(503)])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    slept = _record_sleeps(monkeypatch)

    with pytest.raises(urllib.error.HTTPError):
        api.post_messages("key", "model", "system", [], [])
    assert len(calls) == 2
    assert len(slept) == 1


def test_post_messages_does_not_retry_non_retryable_status(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, calls = make_fake_urlopen([http_error(400)])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    slept = _record_sleeps(monkeypatch)

    with pytest.raises(urllib.error.HTTPError):
        api.post_messages("key", "model", "system", [], [])
    assert len(calls) == 1
    assert slept == []


def test_post_messages_retries_once_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, calls = make_fake_urlopen(
        [urllib.error.URLError("connection reset"), {"content": [], "usage": {}}]
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    slept = _record_sleeps(monkeypatch)

    assert api.post_messages("key", "model", "system", [], []) == {"content": [], "usage": {}}
    assert len(calls) == 2
    assert len(slept) == 1


def _record_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(api.time, "sleep", slept.append)
    return slept


def _http_error_with_headers(code: int, headers: dict[str, str] | None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.anthropic.com/v1/messages", code, "err", cast(Any, headers), None
    )


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_http_error_with_headers(429, {"Retry-After": "7"}), 7.0),
        (_http_error_with_headers(429, {"Retry-After": " 999 "}), api.RETRY_MAX_DELAY_S),
        (_http_error_with_headers(503, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}), 2.0),
        (_http_error_with_headers(503, None), 2.0),
        (_http_error_with_headers(502, {}), 2.0),
        (urllib.error.URLError("dns"), 2.0),
        (TimeoutError("slow"), 2.0),
    ],
)
def test_retry_delay_s_for_retryable_errors(exc: Exception, expected: float) -> None:
    assert api.retry_delay_s(exc, jitter=0.5) == expected


@pytest.mark.parametrize(
    "exc", [_http_error_with_headers(400, {"Retry-After": "1"}), ValueError("not transport")]
)
def test_retry_delay_s_returns_none_for_non_retryable_errors(exc: Exception) -> None:
    assert api.retry_delay_s(exc, jitter=0.5) is None


def test_retry_delay_s_jitter_scales_the_base_delay() -> None:
    low = api.retry_delay_s(urllib.error.URLError("x"), jitter=0.0)
    high = api.retry_delay_s(urllib.error.URLError("x"), jitter=0.99)
    assert low == api.RETRY_BASE_DELAY_S * 0.5
    assert high is not None and high > api.RETRY_BASE_DELAY_S


# ---------------------------------------------------------------------------
# classify_failure: non-HTTP branches (network_error / timeout / generic)
# ---------------------------------------------------------------------------


def test_classify_failure_network_error() -> None:
    result = api.classify_failure(urllib.error.URLError("boom"))
    assert result == api.FailureClassification("network_error", None, False)


def test_classify_failure_timeout() -> None:
    result = api.classify_failure(TimeoutError())
    assert result == api.FailureClassification("timeout", None, False)


def test_classify_failure_generic_exception_uses_type_name() -> None:
    result = api.classify_failure(ValueError("x"))
    assert result == api.FailureClassification("error_ValueError", None, False)


# ---------------------------------------------------------------------------
# classify_failure / _classify_http_error: the documented error-body shape
# ---------------------------------------------------------------------------


def test_classify_http_error_parses_json_body_with_type_and_message() -> None:
    body = json.dumps(
        {
            "type": "error",
            "error": {"type": "invalid_request_error", "message": "bad request shape"},
        }
    ).encode()

    result = api.classify_failure(http_error(400, body))

    assert result.failure == "http_400:invalid_request_error"
    assert result.failure_detail == "bad request shape"
    assert result.infra_failure is False


def test_classify_http_error_non_json_body_falls_back_to_bare_code() -> None:
    result = api.classify_failure(http_error(502, b"<html>Bad Gateway</html>"))

    assert result.failure == "http_502"
    assert result.failure_detail is None
    assert result.infra_failure is False


def test_classify_http_error_no_body_falls_back_to_bare_code() -> None:
    result = api.classify_failure(http_error(500))

    assert result.failure == "http_500"
    assert result.failure_detail is None
    assert result.infra_failure is False


def test_classify_http_error_credit_balance_message_is_infra_regardless_of_status() -> None:
    """The reported live failure: HTTP 400 whose body is
    {"type":"error","error":{"type":"invalid_request_error","message":
    "Your credit balance is too low to access the Claude API. Please go to
    Plans & Billing to upgrade or purchase credits."}}. Neither the pre-Task-2
    bare classification nor the 401/402/403 status set alone would flag this
    as infrastructure; only the message-based fallback does.
    """
    body = json.dumps(
        {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Your credit balance is too low to access the Claude API. "
                "Please go to Plans & Billing to upgrade or purchase credits.",
            },
        }
    ).encode()

    result = api.classify_failure(http_error(400, body))

    assert result.failure == "http_400:invalid_request_error"
    assert result.infra_failure is True


@pytest.mark.parametrize("status", [401, 402, 403])
def test_classify_http_error_auth_and_billing_statuses_are_infra(status: int) -> None:
    result = api.classify_failure(http_error(status))
    assert result.infra_failure is True


def test_classify_http_error_normal_400_is_not_infra() -> None:
    body = json.dumps(
        {"type": "error", "error": {"type": "not_found_error", "message": "model not found"}}
    ).encode()

    result = api.classify_failure(http_error(400, body))

    assert result.infra_failure is False


def test_classify_http_error_message_truncated_to_200_chars() -> None:
    long_message = "x" * 500
    body = json.dumps(
        {"type": "error", "error": {"type": "invalid_request_error", "message": long_message}}
    ).encode()

    result = api.classify_failure(http_error(400, body))

    assert result.failure_detail is not None
    assert len(result.failure_detail) == 200


# ---------------------------------------------------------------------------
# _read_http_error_body: bounded, guarded read
# ---------------------------------------------------------------------------


def test_read_http_error_body_bounded_to_4kb() -> None:
    body = api._read_http_error_body(http_error(400, b"x" * 10_000))
    assert len(body) == api._MAX_ERROR_BODY_BYTES


def test_read_http_error_body_empty_when_fp_is_none() -> None:
    assert api._read_http_error_body(http_error(400)) == ""


def test_read_http_error_body_empty_when_read_raises() -> None:
    class _BoomFp:
        def read(self, _n: int) -> bytes:
            raise OSError("simulated read failure")

        def close(self) -> None:
            return None

    exc = urllib.error.HTTPError(
        "https://api.anthropic.com/v1/messages", 400, "err", cast(Any, {}), cast(Any, _BoomFp())
    )
    assert api._read_http_error_body(exc) == ""


# ---------------------------------------------------------------------------
# _parse_anthropic_error: malformed-shape branches
# ---------------------------------------------------------------------------


def test_parse_anthropic_error_returns_none_for_invalid_json() -> None:
    assert api._parse_anthropic_error("not json{{{") == (None, None)


def test_parse_anthropic_error_returns_none_for_non_dict_json() -> None:
    assert api._parse_anthropic_error("42") == (None, None)


def test_parse_anthropic_error_returns_none_when_error_field_missing() -> None:
    assert api._parse_anthropic_error(json.dumps({"type": "error"})) == (None, None)


def test_parse_anthropic_error_returns_none_when_error_field_not_a_dict() -> None:
    assert api._parse_anthropic_error(json.dumps({"error": "oops"})) == (None, None)


def test_parse_anthropic_error_returns_none_for_non_string_type_or_message() -> None:
    body = json.dumps({"error": {"type": 123, "message": None}})
    assert api._parse_anthropic_error(body) == (None, None)


def test_send_once_refuses_a_non_https_url(monkeypatch: pytest.MonkeyPatch) -> None:
    fake, calls = make_fake_urlopen([{"content": []}])
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    request = urllib.request.Request("file:///etc/passwd")

    with pytest.raises(ValueError, match="non-https"):
        api._send_once(request)
    assert calls == []
