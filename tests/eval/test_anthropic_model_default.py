"""Tests for the shared eval model default and preflight (issues #2857, #2858).

Offline only: the Anthropic HTTP layer is exercised through a monkeypatched
``urllib.request.urlopen``; no network and no real key.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import TracebackType

import pytest

# scripts/eval must be on sys.path so `_anthropic_api` resolves
# (mirrors tests/eval/test_providers.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
_ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(_EVAL_DIR))
try:
    import _anthropic_api
    import _eval_common

    # verify_model_available lazily does `from _providers import ...` at
    # runtime. Import it here so it is cached in sys.modules and resolves
    # even after sys.path is restored below (mirrors test_providers.py).
    import _providers  # noqa: F401
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH


class _Resp(io.BytesIO):
    def __enter__(self) -> _Resp:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        return None


def _models_payload(ids: list[str]) -> bytes:
    return json.dumps({"data": [{"id": i, "type": "model"} for i in ids]}).encode()


# --- Default id ---------------------------------------------------------


def test_default_model_is_live_id() -> None:
    assert _anthropic_api.DEFAULT_MODEL == "claude-sonnet-4-6"


def test_default_model_is_priced() -> None:
    # The default MUST have a pricing row so cost estimation never KeyErrors.
    assert _anthropic_api.DEFAULT_MODEL in _eval_common.MODEL_PRICING_RATES_USD_PER_1K_TOKENS


def test_call_api_default_model_is_shared_constant() -> None:
    import inspect

    sig = inspect.signature(_anthropic_api.call_api)
    assert sig.parameters["model"].default == _anthropic_api.DEFAULT_MODEL


def test_no_dead_id_default_in_eval_scripts() -> None:
    # Guard against reintroducing the dead id as a default anywhere in the
    # harness. The legacy cost-table key and the explanatory comment are the
    # only permitted mentions.
    dead = "claude-sonnet-4-20250514"
    offenders: list[str] = []
    for path in _EVAL_DIR.glob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if dead not in line:
                continue
            if path.name == "_eval_common.py" and line.lstrip().startswith(f'"{dead}"'):
                continue  # legacy pricing key, intentional
            if line.lstrip().startswith("#"):
                continue  # explanatory comment, intentional
            offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "dead model id used outside allowed sites:\n" + "\n".join(offenders)


# --- list_available_models ---------------------------------------------


def test_list_available_models_parses_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _models_payload(["claude-sonnet-4-6", "claude-opus-4-8"])
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _Resp(payload))
    result = _anthropic_api.list_available_models("key")
    assert result == ["claude-sonnet-4-6", "claude-opus-4-8"]


def test_list_available_models_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    def _boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"nope"))

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    with pytest.raises(RuntimeError, match="HTTP 401"):
        _anthropic_api.list_available_models("key")


# --- verify_model_available --------------------------------------------


def test_verify_skips_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_SKIP_MODEL_PREFLIGHT", "1")

    def _boom(req, timeout=None):
        raise AssertionError("must not probe when preflight is skipped")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    _anthropic_api.verify_model_available("key", "anything")  # no raise, no probe


def test_verify_skips_for_non_anthropic_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_SKIP_MODEL_PREFLIGHT", raising=False)

    def _boom(req, timeout=None):
        raise AssertionError("must not probe for a non-anthropic provider")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    _anthropic_api.verify_model_available("key", "gpt-4o", provider="openai")


def test_verify_passes_when_model_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_SKIP_MODEL_PREFLIGHT", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    payload = _models_payload(["claude-sonnet-4-6", "claude-opus-4-8"])
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _Resp(payload))
    _anthropic_api.verify_model_available("key", "claude-sonnet-4-6")  # no raise


def test_verify_fails_closed_on_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_SKIP_MODEL_PREFLIGHT", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    requested = "ghp_" + "M" * 36
    reachable = "private model prompt fragment"
    payload = _models_payload([reachable])
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _Resp(payload))
    with pytest.raises(RuntimeError) as exc:
        _anthropic_api.verify_model_available("key", requested)
    message = str(exc.value)
    assert requested not in message
    assert reachable not in message
    assert message == (
        "Requested model is not reachable with this API key. "
        "Query the models endpoint and pass a reachable model ID."
    )


def test_verify_fails_open_on_infra_error(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("EVAL_SKIP_MODEL_PREFLIGHT", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    import urllib.error

    def _boom(req, timeout=None):
        raise urllib.error.URLError("dns down")

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    # Infra error must NOT raise; it warns and proceeds (fail-open doctrine).
    _anthropic_api.verify_model_available("key", "claude-sonnet-4-6")
    assert "preflight skipped" in capsys.readouterr().err


def test_verify_fails_closed_on_empty_model_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_SKIP_MODEL_PREFLIGHT", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    # Probe succeeds (HTTP 200) but returns zero models -> provably unreachable.
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=None: _Resp(_models_payload([]))
    )
    with pytest.raises(RuntimeError, match="Requested model is not reachable"):
        _anthropic_api.verify_model_available("key", "claude-sonnet-4-6")


def test_verify_fails_open_on_malformed_shape(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("EVAL_SKIP_MODEL_PREFLIGHT", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    # Valid JSON, wrong shape (a bare list). Must NOT crash with AttributeError;
    # list_available_models raises RuntimeError -> verify fails open (warns).
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _Resp(json.dumps([1, 2, 3]).encode()),
    )
    _anthropic_api.verify_model_available("key", "claude-sonnet-4-6")
    assert "preflight skipped" in capsys.readouterr().err


def test_list_available_models_rejects_non_dict_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _Resp(json.dumps("not-an-object").encode()),
    )
    with pytest.raises(RuntimeError, match="unexpected payload shape"):
        _anthropic_api.list_available_models("key")


def test_list_available_models_rejects_non_list_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _Resp(json.dumps({"data": {"id": "x"}}).encode()),
    )
    with pytest.raises(RuntimeError, match="unexpected 'data' shape"):
        _anthropic_api.list_available_models("key")


def test_list_available_models_rejects_non_string_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _Resp(json.dumps({"data": [{"id": 123}]}).encode()),
    )
    with pytest.raises(RuntimeError, match="malformed model entry"):
        _anthropic_api.list_available_models("key")


def test_verify_fails_open_on_non_string_id(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("EVAL_SKIP_MODEL_PREFLIGHT", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    # A non-string id must not crash verify with a TypeError in the join;
    # it is a malformed response -> RuntimeError -> fail open (warn, proceed).
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=None: _Resp(json.dumps({"data": [{"id": 123}]}).encode()),
    )
    _anthropic_api.verify_model_available("key", "claude-sonnet-4-6")
    assert "preflight skipped" in capsys.readouterr().err


# --- 404 enrichment in call_api ----------------------------------------


def test_call_api_404_does_not_disclose_model_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    import urllib.error

    calls = {"n": 0}
    requested = "ghp_" + "R" * 36
    reachable = "private fixture model fragment"

    def _dispatch(req, timeout=None):
        # First call is the POST /v1/messages -> 404; second is the
        # enrichment GET /v1/models -> reachable list.
        if req.full_url.endswith("/v1/messages"):
            calls["n"] += 1
            raise urllib.error.HTTPError(
                req.full_url, 404, "Not Found", {}, io.BytesIO(b"not_found_error")
            )
        return _Resp(_models_payload([reachable]))

    monkeypatch.setattr("urllib.request.urlopen", _dispatch)
    with pytest.raises(RuntimeError) as exc:
        _anthropic_api.call_api(
            "key",
            [{"role": "user", "content": "x"}],
            model=requested,
        )
    msg = str(exc.value)
    assert "HTTP 404" in msg
    assert requested not in msg
    assert reachable not in msg
    assert "Requested model is unavailable" in msg
    assert calls["n"] == 1


# --- load_api_key_for_selected_provider (#3924) -------------------------


class TestLoadApiKeyForSelectedProvider:
    """Tests for load_api_key_for_selected_provider (#3924).

    Default-Anthropic providers must load the real key; all others return "".
    """

    def test_default_empty_string_loads_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EVAL_PROVIDER", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        result = _anthropic_api.load_api_key_for_selected_provider()
        assert result == "sk-test-key"

    def test_explicit_anthropic_loads_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        result = _anthropic_api.load_api_key_for_selected_provider("anthropic")
        assert result == "sk-test-key"

    def test_anthropic_http_loads_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        result = _anthropic_api.load_api_key_for_selected_provider("anthropic-http")
        assert result == "sk-test-key"

    def test_anthropic_urllib_loads_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        result = _anthropic_api.load_api_key_for_selected_provider("anthropic-urllib")
        assert result == "sk-test-key"

    def test_openai_provider_returns_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = _anthropic_api.load_api_key_for_selected_provider("openai")
        assert result == ""

    def test_github_models_provider_returns_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = _anthropic_api.load_api_key_for_selected_provider("github-models")
        assert result == ""

    def test_codex_provider_returns_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = _anthropic_api.load_api_key_for_selected_provider("codex")
        assert result == ""

    def test_eval_provider_env_openai_returns_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EVAL_PROVIDER", "openai")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = _anthropic_api.load_api_key_for_selected_provider()
        assert result == ""

    def test_eval_provider_env_anthropic_sdk_returns_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # anthropic-sdk is NOT in the default-Anthropic set; it is a separate provider
        monkeypatch.setenv("EVAL_PROVIDER", "anthropic-sdk")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = _anthropic_api.load_api_key_for_selected_provider()
        assert result == ""

    def test_missing_key_for_default_anthropic_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("EVAL_PROVIDER", raising=False)
        # load_api_key() also searches .env files; patch Path.exists to block them
        monkeypatch.setattr("pathlib.Path.exists", lambda self: False)
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY not found"):
            _anthropic_api.load_api_key_for_selected_provider()

    def test_provider_arg_takes_precedence_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Even if EVAL_PROVIDER=anthropic, an explicit keyless provider arg wins.
        monkeypatch.setenv("EVAL_PROVIDER", "anthropic")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = _anthropic_api.load_api_key_for_selected_provider("openai")
        assert result == ""

    def test_case_insensitive_provider_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        result = _anthropic_api.load_api_key_for_selected_provider("ANTHROPIC")
        assert result == "sk-test-key"
