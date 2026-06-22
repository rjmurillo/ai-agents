"""Tests for scripts/eval/_providers.py and the call_api provider dispatch.

Offline only: no network, no real SDK. The OpenAI-compatible provider is
exercised through a fake `openai` module injected into sys.modules, so the
tests run without `pip install openai` and without any API key.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# scripts/eval must be on sys.path so `_providers`, `_anthropic_api`, and
# `_eval_api_adapter` resolve (mirrors tests/test_eval_skill_overlap.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import _anthropic_api  # noqa: E402
import _eval_api_adapter  # noqa: E402
import _providers  # noqa: E402

# --- Registry resolution ------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("openai", "openai"),
        ("codex", "openai"),
        ("github", "github"),
        ("github-models", "github"),
        ("anthropic-sdk", "anthropic-sdk"),
    ],
)
def test_resolve_provider_returns_expected_provider(name: str, expected: str) -> None:
    provider = _providers.resolve_provider(name)

    assert provider.name == expected


def test_resolve_provider_raises_on_unknown() -> None:
    with pytest.raises(RuntimeError, match="Unknown EVAL_PROVIDER 'bogus'"):
        _providers.resolve_provider("bogus")


def test_resolve_provider_rejects_default_anthropic_name() -> None:
    with pytest.raises(RuntimeError, match="built-in urllib Anthropic transport"):
        _providers.resolve_provider("anthropic")


@pytest.mark.parametrize("name", ["", "anthropic", "anthropic-http", "ANTHROPIC"])
def test_is_default_anthropic_true_for_default_names(name: str) -> None:
    assert _providers.is_default_anthropic(name) is True


@pytest.mark.parametrize("name", ["openai", "github", "anthropic-sdk"])
def test_is_default_anthropic_false_for_routed_names(name: str) -> None:
    assert _providers.is_default_anthropic(name) is False


def test_known_provider_names_includes_defaults_and_registry() -> None:
    names = _providers.known_provider_names()

    assert "anthropic" in names
    assert {"openai", "codex", "github", "github-models", "anthropic-sdk"} <= set(names)


# --- OpenAI-compatible provider (fake SDK) ------------------------------


class _FakeMessage:
    def __init__(self, content: object) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: object) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: object) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, recorder: list[dict[str, object]]) -> None:
        self._recorder = recorder

    def create(self, **kwargs: object) -> _FakeResponse:
        self._recorder.append(kwargs)
        return _FakeResponse(f"answer-for-{kwargs['model']}")


class _FakeOpenAI:
    def __init__(self, **kwargs: object) -> None:
        self.init_kwargs = kwargs
        self.recorder: list[dict[str, object]] = []
        self.chat = types.SimpleNamespace(completions=_FakeCompletions(self.recorder))


@pytest.fixture()
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> type[_FakeOpenAI]:
    module = types.ModuleType("openai")
    module.__dict__["OpenAI"] = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return _FakeOpenAI


def test_openai_provider_folds_system_into_leading_message(
    fake_openai: type[_FakeOpenAI], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[_FakeOpenAI] = []
    original_init = _FakeOpenAI.__init__

    def _record_init(self: _FakeOpenAI, **kwargs: object) -> None:
        original_init(self, **kwargs)
        captured.append(self)

    monkeypatch.setattr(_FakeOpenAI, "__init__", _record_init)
    provider = _providers.resolve_provider("openai")

    provider.complete(
        messages=[{"role": "user", "content": "hello"}],
        system="be terse",
        model="gpt-4o",
    )

    sent = captured[0].recorder[0]["messages"]
    assert sent[0] == {"role": "system", "content": "be terse"}
    assert sent[1] == {"role": "user", "content": "hello"}


def test_openai_provider_returns_message_content(
    fake_openai: type[_FakeOpenAI],
) -> None:
    provider = _providers.resolve_provider("openai")

    result = provider.complete(
        messages=[{"role": "user", "content": "hi"}], model="gpt-4o"
    )

    assert result == "answer-for-gpt-4o"


def test_openai_provider_raises_on_non_text_content(
    fake_openai: type[_FakeOpenAI], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _return_non_text(self: _FakeCompletions, **kwargs: object) -> _FakeResponse:
        self._recorder.append(kwargs)
        return _FakeResponse([{"type": "text", "text": "not chat text"}])

    monkeypatch.setattr(_FakeCompletions, "create", _return_non_text)
    provider = _providers.resolve_provider("openai")

    with pytest.raises(RuntimeError, match="OpenAI API returned non-text content"):
        provider.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o")


def test_openai_provider_sets_timeout_and_disables_sdk_retries(
    fake_openai: type[_FakeOpenAI], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[_FakeOpenAI] = []
    original_init = _FakeOpenAI.__init__

    def _record_init(self: _FakeOpenAI, **kwargs: object) -> None:
        original_init(self, **kwargs)
        captured.append(self)

    monkeypatch.setattr(_FakeOpenAI, "__init__", _record_init)
    provider = _providers.resolve_provider("openai")

    provider.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o")

    assert captured[0].init_kwargs["timeout"] == 120.0
    assert captured[0].init_kwargs["max_retries"] == 0


def test_github_provider_uses_models_base_url(
    fake_openai: type[_FakeOpenAI], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_MODELS_BASE_URL", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    captured: list[_FakeOpenAI] = []
    original_init = _FakeOpenAI.__init__

    def _record_init(self: _FakeOpenAI, **kwargs: object) -> None:
        original_init(self, **kwargs)
        captured.append(self)

    monkeypatch.setattr(_FakeOpenAI, "__init__", _record_init)
    provider = _providers.resolve_provider("github")

    provider.complete(messages=[{"role": "user", "content": "hi"}], model="openai/gpt-4o")

    assert captured[0].init_kwargs["base_url"] == _providers.GITHUB_MODELS_BASE_URL


# --- Error normalization maps to the adapter taxonomy -------------------


class _StatusError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_normalize_http_status_is_categorized_rate_limit() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        _providers._normalize_and_raise("OpenAI", _StatusError("slow down", 429))

    assert "HTTP 429" in str(exc_info.value)
    assert _eval_api_adapter._categorize_error(exc_info.value) == "rate_limit"


def test_normalize_timeout_is_categorized_timeout() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        _providers._normalize_and_raise("OpenAI", TimeoutError("request timed out"))

    assert "timed out" in str(exc_info.value)
    assert _eval_api_adapter._categorize_error(exc_info.value) == "timeout"


# --- call_api dispatch --------------------------------------------------


def test_call_api_routes_to_resolve_provider_for_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class _Stub:
        name = "openai"

        def complete(self, **kwargs: object) -> str:
            seen.update(kwargs)
            return "routed"

    monkeypatch.setattr(_providers, "resolve_provider", lambda name: _Stub())

    result = _anthropic_api.call_api(
        "ignored-key",
        [{"role": "user", "content": "x"}],
        system="S",
        model="gpt-4o",
        provider="openai",
    )

    assert result == "routed"
    assert seen["model"] == "gpt-4o"
    assert seen["system"] == "S"


def test_call_api_default_uses_urllib_not_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)

    def _boom(_name: str) -> object:
        raise AssertionError("resolve_provider must not be called on the default path")

    monkeypatch.setattr(_providers, "resolve_provider", _boom)

    import io
    import json

    class _Resp(io.BytesIO):
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_: object) -> bool:
            return False

    payload = json.dumps({"content": [{"type": "text", "text": "URLLIB"}]}).encode()
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=None: _Resp(payload)
    )

    result = _anthropic_api.call_api(
        "key", [{"role": "user", "content": "x"}], model="claude"
    )

    assert result == "URLLIB"


def test_call_api_anthropic_name_uses_urllib(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        _providers,
        "resolve_provider",
        lambda name: (_ for _ in ()).throw(AssertionError("must not route")),
    )

    import io
    import json

    class _Resp(io.BytesIO):
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_: object) -> bool:
            return False

    payload = json.dumps({"content": [{"type": "text", "text": "URLLIB"}]}).encode()
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout=None: _Resp(payload)
    )

    result = _anthropic_api.call_api(
        "key", [{"role": "user", "content": "x"}], model="claude", provider="anthropic"
    )

    assert result == "URLLIB"


# --- Key resolution -----------------------------------------------------


def test_read_env_key_returns_first_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRIMARY_KEY", " primary-value\n")

    assert _providers._read_env_key(["PRIMARY_KEY", "FALLBACK_KEY"]) == "primary-value"


def test_read_env_key_strips_only_matching_env_file_quotes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_module = tmp_path / "repo" / "scripts" / "eval" / "_providers.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("# fake", encoding="utf-8")
    repo_root = fake_module.parents[2]
    (repo_root / ".env").write_text(
        "MATCHED=\"matched-value\"\n"
        "LEADING='keeps-leading-double-quote\n"
        "TRAILING=keeps-trailing-single-quote'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(_providers, "__file__", str(fake_module))
    monkeypatch.delenv("MATCHED", raising=False)
    monkeypatch.delenv("LEADING", raising=False)
    monkeypatch.delenv("TRAILING", raising=False)

    assert _providers._read_env_key(["MATCHED"]) == "matched-value"
    assert _providers._read_env_key(["LEADING"]) == "'keeps-leading-double-quote"
    assert _providers._read_env_key(["TRAILING"]) == "keeps-trailing-single-quote'"


def test_read_env_key_raises_naming_candidates_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZZ_NOPE_ONE", raising=False)
    monkeypatch.delenv("ZZ_NOPE_TWO", raising=False)

    with pytest.raises(RuntimeError, match="ZZ_NOPE_ONE, ZZ_NOPE_TWO"):
        _providers._read_env_key(["ZZ_NOPE_ONE", "ZZ_NOPE_TWO"])


def test_read_env_key_rejects_symlinked_module_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_module = tmp_path / "_providers.py"
    monkeypatch.setattr(_providers, "__file__", str(fake_module))
    monkeypatch.delenv("ZZ_NOPE_ONE", raising=False)

    original_is_symlink = Path.is_symlink

    def _is_symlink(self: Path) -> bool:
        return self == fake_module or original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", _is_symlink)

    with pytest.raises(RuntimeError, match="refusing to resolve symlinked module path"):
        _providers._read_env_key(["ZZ_NOPE_ONE"])


def test_default_transport_factory_validates_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVAL_PROVIDER", " bogus ")

    with pytest.raises(RuntimeError, match="Unknown EVAL_PROVIDER 'bogus'"):
        _eval_api_adapter._default_transport_factory()


def test_known_provider_names_omits_empty_default_alias() -> None:
    assert "" not in _providers.known_provider_names()


def test_default_transport_factory_closes_over_resolved_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    class _Stub:
        name = "openai"

        def complete(self, **kwargs: object) -> str:
            seen.update(kwargs)
            return "direct"

    def _should_not_call_api(**_: object) -> str:
        raise AssertionError("default provider transport must not re-enter call_api")

    monkeypatch.setenv("EVAL_PROVIDER", " openai ")
    monkeypatch.setattr(_eval_api_adapter, "call_api", _should_not_call_api)
    monkeypatch.setattr(
        sys.modules["_providers"],
        "resolve_provider",
        lambda name: _Stub(),
    )

    transport = _eval_api_adapter._default_transport_factory()
    result = transport("prompt", "gpt-4o", "system")

    assert result == "direct"
    assert seen == {
        "messages": [{"role": "user", "content": "prompt"}],
        "system": "system",
        "model": "gpt-4o",
        "max_tokens": 1024,
        "temperature": 0.0,
    }


@pytest.mark.parametrize(
    "model,expected",
    [
        ("openai/gpt-5", True),
        ("openai/gpt-5-mini", True),
        ("gpt-5", True),
        ("openai/o1", True),
        ("openai/o3", True),
        ("openai/o4-mini", True),
        ("o3-mini", True),
        ("openai/gpt-4o", False),
        ("openai/gpt-4.1", False),
        ("meta/llama-3.3-70b-instruct", False),
        ("", False),
    ],
)
def test_is_reasoning_model(model: str, expected: bool) -> None:
    assert _providers._is_reasoning_model(model) is expected


def test_reasoning_model_uses_max_completion_tokens_no_temperature(
    fake_openai: type[_FakeOpenAI], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[_FakeOpenAI] = []
    original_init = _FakeOpenAI.__init__

    def _record_init(self: _FakeOpenAI, **kwargs: object) -> None:
        original_init(self, **kwargs)
        captured.append(self)

    monkeypatch.setattr(_FakeOpenAI, "__init__", _record_init)
    provider = _providers.resolve_provider("openai")
    provider.complete(
        messages=[{"role": "user", "content": "hi"}],
        model="openai/gpt-5",
        max_tokens=4000,
    )

    sent = captured[0].recorder[0]
    assert sent["max_completion_tokens"] == 4000
    assert "max_tokens" not in sent
    assert "temperature" not in sent  # reasoning models reject a custom temperature


def test_normal_model_keeps_max_tokens_and_temperature(
    fake_openai: type[_FakeOpenAI], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[_FakeOpenAI] = []
    original_init = _FakeOpenAI.__init__

    def _record_init(self: _FakeOpenAI, **kwargs: object) -> None:
        original_init(self, **kwargs)
        captured.append(self)

    monkeypatch.setattr(_FakeOpenAI, "__init__", _record_init)
    provider = _providers.resolve_provider("openai")
    provider.complete(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o",
        max_tokens=512,
        temperature=0.0,
    )

    sent = captured[0].recorder[0]
    assert sent["max_tokens"] == 512
    assert sent["temperature"] == 0.0
    assert "max_completion_tokens" not in sent
