"""Tests for scripts/eval/_providers.py, _copilot_cli.py, and provider dispatch.

Offline only: no network, no real SDK. The OpenAI-compatible provider is
exercised through a fake `openai` module injected into sys.modules, so the
tests run without `pip install openai` and without any API key.
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import pytest

# scripts/eval must be on sys.path so `_providers`, `_anthropic_api`, and
# `_eval_api_adapter` resolve (mirrors tests/test_eval_skill_overlap.py).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
_ORIGINAL_SYS_PATH = sys.path.copy()
sys.path.insert(0, str(_EVAL_DIR))
try:
    import _anthropic_api  # noqa: E402
    import _eval_api_adapter  # noqa: E402
    import _providers  # noqa: E402
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH

# Reach the extracted transport through the object `_providers` actually bound,
# not through a second import. A fresh import could resolve to a different
# module object depending on sys.path order, and a patch applied to one copy
# would silently miss the copy under test.
_copilot_cli = sys.modules[_providers._CopilotCLIProvider.__module__]

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
    def __init__(self, content: object, system_fingerprint: str | None = "fp-test") -> None:
        self.choices = [_FakeChoice(content)]
        if system_fingerprint is not None:
            self.system_fingerprint = system_fingerprint


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
    assert isinstance(sent, list)
    assert sent[0] == {"role": "system", "content": "be terse"}
    assert sent[1] == {"role": "user", "content": "hello"}


def test_openai_provider_returns_message_content(
    fake_openai: type[_FakeOpenAI],
) -> None:
    provider = _providers.resolve_provider("openai")

    result = provider.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o")

    assert result == "answer-for-gpt-4o"


def test_openai_provider_passes_seed_when_provided(
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
        seed=3475,
    )

    assert captured[0].recorder[0]["seed"] == 3475


def test_openai_provider_omits_seed_when_unset(
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

    assert "seed" not in captured[0].recorder[0]


def test_openai_provider_captures_system_fingerprint(
    fake_openai: type[_FakeOpenAI],
) -> None:
    provider = _providers.resolve_provider("openai")

    provider.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o")

    assert provider.system_fingerprint == "fp-test"


def test_openai_provider_tolerates_missing_system_fingerprint(
    fake_openai: type[_FakeOpenAI], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _return_without_fingerprint(self: _FakeCompletions, **kwargs: object) -> _FakeResponse:
        self._recorder.append(kwargs)
        return _FakeResponse("answer", system_fingerprint=None)

    monkeypatch.setattr(_FakeCompletions, "create", _return_without_fingerprint)
    provider = _providers.resolve_provider("openai")

    provider.complete(messages=[{"role": "user", "content": "hi"}], model="gpt-4o")

    assert provider.system_fingerprint is None


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


class TestAStatusOutranksATextHint:
    """A message carrying an HTTP status is classified by that status.

    The HTTP error shape appends the sanitized response body to the message,
    so an upstream body that happens to contain "timed out" used to be read as
    a timeout and retried three times, even on a 4xx the module documents as
    no-retry. Text hints describe the providers that report no status at all.
    """

    def test_a_4xx_whose_body_mentions_a_timeout_is_not_retried(self) -> None:
        exc = RuntimeError("Anthropic API returned HTTP 404: upstream timed out")

        category = _eval_api_adapter._categorize_error(exc)

        assert category == "client_error"
        assert not _eval_api_adapter._is_transient(category)

    def test_an_auth_status_outranks_a_timeout_hint_in_the_body(self) -> None:
        exc = RuntimeError("Anthropic API returned HTTP 401: session timed out")

        category = _eval_api_adapter._categorize_error(exc)

        assert category == "auth"
        assert not _eval_api_adapter._is_transient(category)

    def test_a_429_whose_body_mentions_a_timeout_reads_as_a_rate_limit(self) -> None:
        exc = RuntimeError("Anthropic API returned HTTP 429: retry, request timed out")

        category = _eval_api_adapter._categorize_error(exc)

        assert category == "rate_limit"
        assert _eval_api_adapter._is_transient(category)

    def test_a_408_still_reads_as_a_timeout_without_any_text_hint(self) -> None:
        exc = RuntimeError("Anthropic API returned HTTP 408: request took too long")

        assert _eval_api_adapter._categorize_error(exc) == "timeout"

    def test_a_message_with_no_status_still_reads_its_text_hint(self) -> None:
        exc = RuntimeError("Anthropic API request timed out after 120s.")

        assert _eval_api_adapter._categorize_error(exc) == "timeout"

    def test_a_rate_limit_hint_needs_no_status_to_be_recognized(self) -> None:
        exc = RuntimeError("copilot exited 1: Rate limit exceeded, try later")

        assert _eval_api_adapter._categorize_error(exc) == "rate_limit"

    def test_subprocess_auth_hint_is_narrow_and_status_still_wins(self) -> None:
        exc = RuntimeError(
            "Copilot CLI exited with code 1: authentication failed: token expired"
        )

        category = _eval_api_adapter._categorize_error(exc)

        assert category == "auth"
        assert not _eval_api_adapter._is_transient(category)
        status_exc = RuntimeError("Anthropic API returned HTTP 500: authentication failed")
        unrelated_exc = RuntimeError(
            "Copilot CLI exited with code 1: authorization cache failed"
        )
        assert _eval_api_adapter._categorize_error(status_exc) == "server_error"
        assert _eval_api_adapter._categorize_error(unrelated_exc) == "server_error"


class TestSubprocessAuthFailureIsPermanent:
    def test_call_model_does_not_retry_a_subprocess_auth_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        attempts = 0
        sleeps: list[float] = []

        def _raise_auth(_prompt: str, _model_id: str, _system: str) -> str:
            nonlocal attempts
            attempts += 1
            raise RuntimeError("Copilot CLI exited with code 1: authentication failed")

        monkeypatch.setattr(
            _eval_api_adapter, "_backoff_delay_seconds", lambda attempt: 0.0
        )
        adapter = _eval_api_adapter.AnthropicAPIAdapter(
            transport=_raise_auth,
            sleep=sleeps.append,
        )

        result = adapter.call_model("prompt", "model", "fixture", "variant", 0)

        assert result.error_category == "auth"
        assert result.attempts == 1
        assert attempts == 1
        assert sleeps == []


class TestEvalLogSchema:
    def test_emit_log_accepts_the_closed_schema_and_rejects_payload_fields(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _eval_api_adapter._emit_log(
            {
                "fixture_id": "fx",
                "variant": "baseline",
                "run_index": 0,
                "model_id": "model",
                "attempt": 1,
                "outcome": "success",
                "latency_ms": 12.3,
                "tokens_in": 4,
                "tokens_out": 5,
                "error_category": None,
            }
        )

        logged = json.loads(capsys.readouterr().err)

        assert logged["fixture_id"] == "fx"
        assert set(logged) == _eval_api_adapter._ALLOWED_LOG_FIELDS
        record = {
            "fixture_id": "fx",
            "variant": "baseline",
            "run_index": 0,
            "model_id": "model",
            "attempt": 1,
            "outcome": "error",
            "latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "error_category": "server_error",
            "payload": {"prompt": "secret"},
        }

        with pytest.raises(ValueError) as exc_info:
            _eval_api_adapter._emit_log(record)

        message = str(exc_info.value)
        assert "payload" in message
        assert "banned fields" in message
        assert capsys.readouterr().err == ""


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

        def __exit__(self, *_: object) -> None:
            return None

    payload = json.dumps({"content": [{"type": "text", "text": "URLLIB"}]}).encode()
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _Resp(payload))

    result = _anthropic_api.call_api("key", [{"role": "user", "content": "x"}], model="claude")

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

        def __exit__(self, *_: object) -> None:
            return None

    payload = json.dumps({"content": [{"type": "text", "text": "URLLIB"}]}).encode()
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _Resp(payload))

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
        'MATCHED="matched-value"\n'
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


# --- Copilot CLI provider -----------------------------------------------


@pytest.mark.parametrize("alias", ["copilot", "copilot-cli"])
def test_copilot_aliases_resolve_to_the_cli_provider(alias: str) -> None:
    provider = _providers.resolve_provider(alias)

    assert provider.name == "copilot-cli"


def test_known_provider_names_includes_copilot_aliases() -> None:
    names = _providers.known_provider_names()

    assert "copilot" in names
    assert "copilot-cli" in names


def test_strip_footer_removes_the_cli_stats_block() -> None:
    raw = (
        "PONG\n\n\n"
        "Changes    +0 -0\n"
        "AI Credits 68.3 (6s)\n"
        "Tokens     109.3k written\n"
        "Resume     copilot --resume=abc123\n"
    )

    assert _providers._CopilotCLIProvider._strip_footer(raw) == "PONG"


def test_strip_footer_preserves_multiline_answer_body() -> None:
    raw = "line one\nline two\n\nChanges    +1 -1\nResume     copilot --resume=x\n"

    assert _providers._CopilotCLIProvider._strip_footer(raw) == "line one\nline two"


def test_strip_footer_keeps_prose_that_merely_starts_with_a_footer_word() -> None:
    """Single-spaced prose is not the CLI's 2+-space column format."""
    raw = "Tokens are the unit of billing.\n\nChanges    +0 -0\n"

    assert _providers._CopilotCLIProvider._strip_footer(raw) == "Tokens are the unit of billing."


def test_strip_footer_keeps_prose_opening_with_a_long_footer_label() -> None:
    """A label longer than the value column satisfies the column test on its
    own, so prose starting with one was stripped off the end of real answers.

    ``Total duration`` is 14 characters against an 11-character column, which
    made the column check vacuous for every sentence beginning that way.
    """
    raw = "Total duration and latency are the two things to measure.\n"

    assert (
        _providers._CopilotCLIProvider._strip_footer(raw)
        == "Total duration and latency are the two things to measure."
    )


def test_strip_footer_still_removes_a_long_label_with_a_real_value() -> None:
    raw = "PONG\n\nTotal duration 1m2s\nWall time  2.4s\n"

    assert _providers._CopilotCLIProvider._strip_footer(raw) == "PONG"


def test_strip_footer_returns_empty_when_output_is_only_a_footer() -> None:
    raw = "\nChanges    +0 -0\nResume     copilot --resume=abc\n"

    assert _providers._CopilotCLIProvider._strip_footer(raw) == ""


class TestAmbiguousFooterIsRefused:
    @pytest.mark.parametrize(
        ("raw", "kept"),
        [
            (
                "Model answer:\nTokens     42\n\nTokens     1.2k\n",
                "Model answer:\nTokens     42",
            ),
            (
                "The count is:\nTokens     42\n\nChanges    +0 -0\n",
                "The count is:\nTokens     42",
            ),
        ],
        ids=["footer-follows-the-stats-shaped-answer-line", "footer-follows-answer"],
    )
    def test_strip_footer_keeps_a_stats_shaped_answer_line_when_footer_is_separated(
        self, raw: str, kept: str
    ) -> None:
        assert _providers._CopilotCLIProvider._strip_footer(raw) == kept

    @pytest.mark.parametrize(
        "raw",
        [
            "The count is:\nTokens     42\n",
            "Model answer:\nChanges    +0 -0\n",
        ],
        ids=["single-stats-shaped-line", "changes-shaped-line"],
    )
    def test_strip_footer_refuses_a_stats_shaped_answer_line_without_separator(
        self, raw: str
    ) -> None:
        with pytest.raises(RuntimeError, match="stats-shaped line"):
            _providers._CopilotCLIProvider._strip_footer(raw)


class _FakeCompleted:
    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _capture_run(monkeypatch: pytest.MonkeyPatch, result: object) -> dict:
    """Patch subprocess.run inside _copilot_cli and record how it was called."""
    seen: dict = {}

    def fake_run(argv: list[str], **kwargs: object) -> object:
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(_copilot_cli.subprocess, "run", fake_run)
    return seen


def _allow_unverified_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt in to a reply whose model the transcript never confirmed.

    These tests observe argv construction, footer stripping, or which source an
    answer came from. None of them is about the model check, and all of them
    reach the stdout fallback, which refuses by default. Opting in keeps each
    test on its own subject instead of silently re-testing the model gate.
    """
    monkeypatch.setenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", "1")


def test_copilot_complete_returns_stripped_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_unverified_model(monkeypatch)
    seen = _capture_run(
        monkeypatch,
        _FakeCompleted(stdout="the answer\n\nChanges    +0 -0\n"),
    )
    provider = _providers._CopilotCLIProvider()

    out = provider.complete(
        messages=[{"role": "user", "content": "the question"}],
        system="be terse",
        model="claude-opus-5",
    )

    assert out == "the answer"
    argv = seen["argv"]
    assert argv[0] == "copilot"
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "claude-opus-5"
    # System text is folded into the single prompt channel, ahead of the user turn.
    prompt = argv[argv.index("--prompt") + 1]
    assert prompt == "be terse\n\nthe question"


def test_copilot_complete_refuses_ambiguous_footer_shaped_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_unverified_model(monkeypatch)
    _capture_run(monkeypatch, _FakeCompleted(stdout="The count is:\nTokens     42\n"))
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError, match="stats-shaped line"):
        provider.complete(messages=[{"role": "user", "content": "q"}], model="m")


def test_copilot_complete_folds_supported_roles_into_one_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_unverified_model(monkeypatch)
    seen = _capture_run(monkeypatch, _FakeCompleted(stdout="ok\n"))
    provider = _providers._CopilotCLIProvider()

    provider.complete(
        messages=[
            {"role": "user", "content": "Question"},
            {"role": "system", "content": "Extra constraints"},
            {"role": "user", "content": "Follow-up"},
        ],
        model="m",
    )

    prompt = seen["argv"][seen["argv"].index("--prompt") + 1]
    assert prompt == "Question\n\nExtra constraints\n\nFollow-up"


def test_copilot_complete_isolates_cwd_and_disables_builtin_mcps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The repo's own instruction files are the variable under test; the CLI
    must not load them from the working directory."""
    _allow_unverified_model(monkeypatch)
    seen = _capture_run(monkeypatch, _FakeCompleted(stdout="ok\n"))
    provider = _providers._CopilotCLIProvider()

    provider.complete(messages=[{"role": "user", "content": "q"}], model="m")

    assert "--disable-builtin-mcps" in seen["argv"]
    cwd = seen["kwargs"]["cwd"]
    assert cwd != str(_REPO_ROOT)
    assert not (Path(cwd) / "AGENTS.md").exists()
    assert seen["kwargs"].get("shell", False) is False


def test_copilot_complete_disables_ambient_custom_instructions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sandboxing cwd only drops repo-level instruction files. User-level ones
    in ``~/.copilot/`` load regardless of working directory, and measured 13.5k
    input tokens on a live call: several times the size of the rule bodies
    these evals compare, overlapping them semantically. Without this flag every
    cell carries them and deltas compress toward zero."""
    _allow_unverified_model(monkeypatch)
    seen = _capture_run(monkeypatch, _FakeCompleted(stdout="ok\n"))
    provider = _providers._CopilotCLIProvider()

    provider.complete(messages=[{"role": "user", "content": "q"}], model="m")

    assert "--no-custom-instructions" in seen["argv"]


def test_copilot_complete_raises_on_empty_prompt() -> None:
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError, match="non-empty prompt"):
        provider.complete(messages=[{"role": "user", "content": "  "}], model="m")


def test_copilot_complete_allows_system_role_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_unverified_model(monkeypatch)
    seen = _capture_run(monkeypatch, _FakeCompleted(stdout="ok\n"))
    provider = _providers._CopilotCLIProvider()

    provider.complete(
        messages=[
            {"role": "system", "content": "extra constraints"},
            {"role": "user", "content": "question"},
        ],
        system="primary constraints",
        model="claude-opus-5",
    )

    argv = seen["argv"]
    prompt = argv[argv.index("--prompt") + 1]
    assert prompt == "primary constraints\n\nextra constraints\n\nquestion"


def test_copilot_complete_rejects_assistant_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Copilot CLI can only accept user and system messages when folding into
    a single prompt. Non-user roles must fail visibly before subprocess.run."""
    seen = _capture_run(monkeypatch, _FakeCompleted(stdout="should not reach"))
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(
        RuntimeError,
        match="Copilot CLI can only fold user/system messages into its single prompt channel",
    ) as exc_info:
        provider.complete(
            messages=[
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "response"},
            ],
            model="claude-opus-5",
        )

    assert "assistant" in str(exc_info.value)
    assert "argv" not in seen


def test_copilot_complete_nonzero_exit_reports_the_exit_code_not_an_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The message must say what the number is, and still categorize.

    An earlier version borrowed the Anthropic HTTP wording so that
    `_categorize_error` would classify the failure. A subprocess exit code is
    not an HTTP status, and POSIX truncates it to 0-255, so the borrowed shape
    was both wrong to read and unreachable at the codes it claimed to carry.
    Categorization now comes from the CLI's own stderr text.
    """
    _capture_run(
        monkeypatch,
        _FakeCompleted(stderr="rate limit exceeded", returncode=1),
    )
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete(messages=[{"role": "user", "content": "q"}], model="m")

    message = str(exc_info.value)
    assert "exited with code 1" in message
    assert "HTTP" not in message
    assert _eval_api_adapter._categorize_error(exc_info.value) == "rate_limit"


def test_copilot_exit_excerpt_strips_control_bytes_and_bounds_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both halves of the excerpt are load-bearing and neither was covered.

    The control-byte filter keeps an escape sequence out of a terminal that
    renders this message. The 200-character bound keeps a stderr dump out of
    the exception. The comment above the excerpt claimed both before any test
    held them.
    """
    _capture_run(
        monkeypatch,
        _FakeCompleted(stderr="\x1b[31mred\x07 " + "z" * 400, returncode=1),
    )
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete(messages=[{"role": "user", "content": "q"}], model="m")

    message = str(exc_info.value)
    assert "\x1b" not in message
    assert "\x07" not in message
    assert "red" in message
    assert message.count("z") == 200 - len("[31mred ")


def test_copilot_exit_excerpt_does_not_redact_a_short_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Characterization, not endorsement. See the comment above the excerpt.

    A token short enough to fit the bound is printable ascii, so it survives
    both filters intact. Nothing here makes that safe. The exposure is
    contained by the caller: the adapter keeps only `error_category` and
    reports `raw_response=None`, so this text reaches no artifact. This pins
    the limitation so that adding a redactor, or surfacing the message
    somewhere it would persist, is a visible change rather than a silent one.
    """
    secret = "ghp_" + "A" * 36
    _capture_run(
        monkeypatch,
        _FakeCompleted(stderr=f"authentication failed: token {secret}", returncode=1),
    )
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete(messages=[{"role": "user", "content": "q"}], model="m")

    assert secret in str(exc_info.value)


def test_copilot_complete_generic_exit_code_stays_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """255 is a common generic-failure code and is three digits.

    Under the borrowed HTTP wording it read as "HTTP 255", matched no status
    band, and categorized as non-transient `unknown`, so a retryable failure
    was recorded once and dropped.
    """
    _capture_run(
        monkeypatch,
        _FakeCompleted(stderr="unexpected failure", returncode=255),
    )
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete(messages=[{"role": "user", "content": "q"}], model="m")

    category = _eval_api_adapter._categorize_error(exc_info.value)
    assert category == "server_error"
    assert _eval_api_adapter._is_transient(category)


def test_copilot_complete_timeout_is_categorized_as_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_run(
        monkeypatch,
        _copilot_cli.subprocess.TimeoutExpired(cmd="copilot", timeout=900),
    )
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete(messages=[{"role": "user", "content": "q"}], model="m")

    assert "timed out" in str(exc_info.value)
    assert _eval_api_adapter._categorize_error(exc_info.value) == "timeout"


def test_copilot_complete_missing_executable_names_the_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_run(monkeypatch, FileNotFoundError("no such file"))
    provider = _providers._CopilotCLIProvider(executable="copilot-nope")

    with pytest.raises(RuntimeError, match="copilot-nope"):
        provider.complete(messages=[{"role": "user", "content": "q"}], model="m")


def test_copilot_complete_blank_stdout_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _capture_run(monkeypatch, _FakeCompleted(stdout="\nChanges    +0 -0\n"))
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError, match="no choices"):
        provider.complete(messages=[{"role": "user", "content": "q"}], model="m")


def test_copilot_factory_reads_timeout_and_binary_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COPILOT_CLI_TIMEOUT", "42")
    monkeypatch.setenv("COPILOT_CLI_BIN", "/opt/copilot")

    provider = _providers.resolve_provider("copilot-cli")

    assert provider._timeout == 42.0
    assert provider._executable == "/opt/copilot"


def test_copilot_factory_rejects_a_non_numeric_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COPILOT_CLI_TIMEOUT", "soon")

    with pytest.raises(RuntimeError, match="COPILOT_CLI_TIMEOUT"):
        _providers.resolve_provider("copilot-cli")


# ---------------------------------------------------------------------------
# Session transcript reading
#
# The CLI writes structured per-session events to session-state/*/events.jsonl,
# where assistant.message.content holds the reply and tool calls sit in a
# separate toolRequests field. Reading that beats scraping stdout, where tool
# traces and the stats footer interleave with the answer. Sessions are matched
# on the sandbox cwd, which is unique per call, so parallel runs cannot swap
# transcripts.
# ---------------------------------------------------------------------------


def _write_session(root, cwd: str, *, model: str, contents: list[object]) -> None:
    """Write one events.jsonl shaped like the CLI's, under a fresh session id."""
    import uuid

    session_dir = root / str(uuid.uuid4())
    session_dir.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "type": "session.start",
            "data": {"selectedModel": model, "context": {"cwd": cwd}},
        }
    ]
    for content in contents:
        events.append(
            {
                "type": "assistant.message",
                "data": {"content": content, "model": model, "toolRequests": []},
            }
        )
    (session_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


def _run_writing_session(
    monkeypatch: pytest.MonkeyPatch,
    root,
    *,
    model: str,
    contents: list[object],
    stdout: str = "stdout fallback text\n",
):
    """Patch subprocess.run so it records a session for the sandbox it is given."""

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompleted:
        _write_session(root, str(kwargs["cwd"]), model=model, contents=contents)
        return _FakeCompleted(stdout=stdout)

    monkeypatch.setattr(_copilot_cli.subprocess, "run", fake_run)
    monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(root))


def test_copilot_prefers_the_session_transcript_over_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _run_writing_session(
        monkeypatch,
        tmp_path,
        model="claude-opus-5",
        contents=["the real answer"],
        stdout="\u25cf tool trace\n  \u2502 ls -la\nthe real answer\n\nTokens     1.2k\n",
    )
    provider = _providers._CopilotCLIProvider()

    out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    assert out == "the real answer"


def test_copilot_transcript_joins_multiple_assistant_messages(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _run_writing_session(
        monkeypatch,
        tmp_path,
        model="claude-opus-5",
        contents=["first part", "second part"],
    )
    provider = _providers._CopilotCLIProvider()

    out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    assert out == "first part\n\nsecond part"


def test_copilot_transcript_skips_tool_only_messages(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # A turn that only issues a tool call carries content "".
    _run_writing_session(
        monkeypatch,
        tmp_path,
        model="claude-opus-5",
        contents=["", "   ", "only real content"],
    )
    provider = _providers._CopilotCLIProvider()

    out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    assert out == "only real content"


@pytest.mark.parametrize(
    ("bad_content", "type_name"),
    [
        ([{"type": "text", "text": "SECOND PART"}], "list"),
        (None, "NoneType"),
    ],
    ids=["structured-content-blocks", "explicit-null"],
)
def test_copilot_refuses_a_transcript_carrying_content_that_is_not_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path, bad_content: object, type_name: str
) -> None:
    """A shape this reader cannot decode must not be read past.

    Skipping the message drops its words and its `model` field together, so
    the remaining text would be graded as a whole answer and would arrive
    fully confirmed. The middle message is the one that is unreadable, so a
    silent skip would still produce a plausible two-part answer.
    """
    _run_writing_session(
        monkeypatch,
        tmp_path,
        model="claude-opus-5",
        contents=["first part", bad_content, "third part"],
    )
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError) as excinfo:
        provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    message = str(excinfo.value)
    assert "malformed" in message
    assert type_name in message


def test_the_malformed_transcript_refusal_survives_the_unverified_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Corruption and absence are different answers and take different exits.

    Returning None here would report a log this reader could not decode as a
    log that does not exist. The operator who set the opt-in accepted a
    missing transcript, not a corrupt one, so under that flag the fallback
    would grade raw stdout and discard the model confirmation this very log
    carries. The refusal has to outrank the flag.
    """
    monkeypatch.setenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", "1")
    _run_writing_session(
        monkeypatch,
        tmp_path,
        model="claude-opus-5",
        contents=["first part", None, "third part"],
        stdout="a clean stdout answer\n",
    )
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError) as excinfo:
        provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    message = str(excinfo.value)
    assert "malformed" in message
    assert "a clean stdout answer" not in message
    assert provider.system_fingerprint is None


def test_copilot_transcript_ignores_sessions_from_other_sandboxes(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompleted:
        _write_session(
            tmp_path,
            "/tmp/some-other-sandbox",
            model="claude-opus-5",
            contents=["someone else's answer"],
        )
        return _FakeCompleted(stdout="my stdout answer\n")

    _allow_unverified_model(monkeypatch)
    monkeypatch.setattr(_copilot_cli.subprocess, "run", fake_run)
    monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(tmp_path))
    provider = _providers._CopilotCLIProvider()

    out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    assert out == "my stdout answer"


def test_copilot_refuses_a_relative_session_state_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative override can never name the directory the CLI writes.

    The CLI inherits this variable and runs with cwd set to a per-call
    sandbox, so it resolves a relative value against that sandbox while this
    process resolves it against its own cwd. The two never agree, so every
    call would report a missing transcript. That refusal blames the transcript
    and reads as a reason to set the unverified-model opt-in, which grades raw
    stdout and drops the model check the transcript exists to perform. Naming
    the variable keeps a fixable config error from turning into a degraded run.
    """
    _capture_run(monkeypatch, _FakeCompleted(stdout="answer\n"))
    monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", "session-state")
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError) as exc_info:
        provider.complete(messages=[{"role": "user", "content": "q"}], model="m")

    message = str(exc_info.value)
    assert "COPILOT_SESSION_STATE_DIR" in message
    assert "absolute" in message
    assert "session-state" in message


def test_copilot_accepts_an_absolute_session_state_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Guard against over-refusing. The absolute path is the supported form."""
    _allow_unverified_model(monkeypatch)
    _capture_run(monkeypatch, _FakeCompleted(stdout="answer\n"))
    monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(tmp_path))
    provider = _providers._CopilotCLIProvider()

    out = provider.complete(messages=[{"role": "user", "content": "q"}], model="m")

    assert out == "answer"


def test_copilot_falls_back_to_stdout_when_session_root_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _allow_unverified_model(monkeypatch)
    _capture_run(monkeypatch, _FakeCompleted(stdout="stdout answer\n"))
    monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(tmp_path / "absent"))
    provider = _providers._CopilotCLIProvider()

    out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    assert out == "stdout answer"


def test_copilot_transcript_survives_malformed_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompleted:
        session_dir = tmp_path / "s1"
        session_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "not json at all",
            "[1, 2, 3]",
            json.dumps(
                {
                    "type": "session.start",
                    "data": {
                        "selectedModel": "claude-opus-5",
                        "context": {"cwd": kwargs["cwd"]},
                    },
                }
            ),
            json.dumps({"type": "assistant.message", "data": None}),
            json.dumps({"type": "assistant.message"}),
            json.dumps(
                {
                    "type": "assistant.message",
                    "data": {"content": "survived", "model": "claude-opus-5"},
                }
            ),
        ]
        (session_dir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return _FakeCompleted(stdout="stdout answer\n")

    monkeypatch.setattr(_copilot_cli.subprocess, "run", fake_run)
    monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(tmp_path))
    provider = _providers._CopilotCLIProvider()

    out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    assert out == "survived"


def test_copilot_raises_when_the_session_ran_a_different_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Silent model substitution would attribute one model's behavior to
    # another, which corrupts every downstream comparison.
    _run_writing_session(
        monkeypatch,
        tmp_path,
        model="gpt-5.6-sol",
        contents=["an answer"],
    )
    provider = _providers._CopilotCLIProvider()

    with pytest.raises(RuntimeError, match="ran gpt-5.6-sol instead"):
        provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")


def test_copilot_ignores_session_logs_written_before_this_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    stale = tmp_path / "stale"
    stale.mkdir(parents=True)
    events = stale / "events.jsonl"

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompleted:
        _write_session_stale(events, str(kwargs["cwd"]))
        return _FakeCompleted(stdout="stdout answer\n")

    def _write_session_stale(path, cwd: str) -> None:
        payload = [
            {
                "type": "session.start",
                "data": {
                    "selectedModel": "claude-opus-5",
                    "context": {"cwd": cwd},
                },
            },
            {"type": "assistant.message", "data": {"content": "stale answer"}},
        ]
        path.write_text("\n".join(json.dumps(e) for e in payload) + "\n", encoding="utf-8")
        # Backdate well past the `since` window this call uses.
        os.utime(path, (1_000_000, 1_000_000))

    _allow_unverified_model(monkeypatch)
    monkeypatch.setattr(_copilot_cli.subprocess, "run", fake_run)
    monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(tmp_path))
    provider = _providers._CopilotCLIProvider()

    out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    assert out == "stdout answer"


class TestTheStdoutFallbackWillNotGradeHarnessOutput:
    """The fallback reads raw stdout, where CLI traces precede the answer.

    `_strip_footer` anchors at the end of the output, so it removes the stats
    block and leaves a leading trace untouched. Grading that would score the
    harness rather than the model, and there is no reliable boundary between
    the trace and the reply, so the run is refused instead. Found by adversarial
    review round 32 against a surface no earlier round had read.
    """

    @staticmethod
    def _fallback(monkeypatch: pytest.MonkeyPatch, tmp_path, stdout: str):
        _allow_unverified_model(monkeypatch)
        _capture_run(monkeypatch, _FakeCompleted(stdout=stdout))
        monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(tmp_path / "absent"))
        return _providers._CopilotCLIProvider()

    def test_a_traced_stdout_is_refused_rather_than_graded(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        provider = self._fallback(
            monkeypatch,
            tmp_path,
            "\u25cf tool trace\n  \u2502 ls -la\nMODEL ANSWER\n\nTokens     1.2k\n",
        )

        with pytest.raises(RuntimeError, match="trace marker"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    @pytest.mark.parametrize("prefix", ["\u25cf", "\u2502", "\u251c", "\u2514"])
    def test_every_trace_prefix_the_cli_emits_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, prefix: str
    ) -> None:
        provider = self._fallback(monkeypatch, tmp_path, f"{prefix} trace\nMODEL ANSWER\n")

        with pytest.raises(RuntimeError, match="trace marker"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    def test_an_indented_trace_is_still_a_trace(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """The trace body is indented under its header, so matching must lstrip.

        The indented line is deliberately not the first one: `_strip_footer`
        ends with `.strip()`, which unindents line one and would let this pass
        without the lstrip actually being exercised.
        """
        provider = self._fallback(
            monkeypatch,
            tmp_path,
            "Working on it\n  \u2502 ls -la\nMODEL ANSWER\n",
        )

        with pytest.raises(RuntimeError, match="trace marker"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    def test_the_refusal_says_how_to_get_the_structured_transcript(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        provider = self._fallback(monkeypatch, tmp_path, "\u25cf trace\nMODEL ANSWER\n")

        with pytest.raises(RuntimeError) as excinfo:
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert "COPILOT_SESSION_STATE_DIR" in str(excinfo.value)

    def test_a_clean_fallback_still_answers(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """The refusal is scoped to traced output; graceful degradation stays."""
        provider = self._fallback(monkeypatch, tmp_path, "a clean answer\n")

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "a clean answer"

    def test_a_trace_character_used_inside_a_sentence_is_not_a_trace(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Anchoring at line start keeps a legitimate answer from being refused."""
        provider = self._fallback(
            monkeypatch, tmp_path, "Use the box char \u2502 to draw a table.\n"
        )

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "Use the box char \u2502 to draw a table."

    def test_the_detector_is_not_vacuous(self) -> None:
        """A detector that cannot fire has not been run."""
        provider = _providers._CopilotCLIProvider
        assert provider._may_carry_tool_trace("\u25cf tool trace\nanswer") is True
        assert provider._may_carry_tool_trace("just an answer") is False


class TestAReplyIsNotGradedForAModelNobodyConfirmed:
    """The CLI accepts `--model` without confirming it honored the request.

    On the transcript path a substitution is caught by comparing
    `session.start.data.selectedModel`. On the stdout fallback there is nothing
    to compare against, so a reply from another model is indistinguishable from
    the requested one. Every consumer of this transport publishes per-model
    results, so an unconfirmed reply is a score for an unknown model, which is
    the same defect class the rest of this campaign fixed elsewhere: a number
    attached to a population it was not measured on. Adversarial review round
    33; all eight archived runs predate the transcript reader and took this
    path, which is why the archive's provenance rests on filenames.
    """

    @staticmethod
    def _fallback(monkeypatch: pytest.MonkeyPatch, tmp_path):
        _capture_run(monkeypatch, _FakeCompleted(stdout="an answer\n"))
        monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(tmp_path / "absent"))
        return _providers._CopilotCLIProvider()

    def test_an_unconfirmed_model_is_refused_by_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.delenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", raising=False)
        provider = self._fallback(monkeypatch, tmp_path)

        with pytest.raises(RuntimeError, match="could not confirm which model"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    def test_the_refusal_names_both_ways_out(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.delenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", raising=False)
        provider = self._fallback(monkeypatch, tmp_path)

        with pytest.raises(RuntimeError) as excinfo:
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        message = str(excinfo.value)
        assert "COPILOT_SESSION_STATE_DIR" in message
        assert "EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL" in message

    def test_an_explicit_opt_in_accepts_the_loss(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        monkeypatch.setenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", "1")
        provider = self._fallback(monkeypatch, tmp_path)

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "an answer"

    def test_a_confirmed_model_needs_no_opt_in(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """The gate is scoped to the unverified path, not applied blanket."""
        monkeypatch.delenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", raising=False)
        _run_writing_session(
            monkeypatch,
            tmp_path,
            model="claude-opus-5",
            contents=["the real answer"],
        )
        provider = _providers._CopilotCLIProvider()

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "the real answer"

    def test_a_transcript_that_names_no_model_confirms_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """A readable session is not the same fact as a confirmed model."""
        monkeypatch.delenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", raising=False)

        def fake_run(argv: list[str], **kwargs: object) -> _FakeCompleted:
            session_dir = tmp_path / "s1"
            session_dir.mkdir(parents=True, exist_ok=True)
            events = [
                {"type": "session.start", "data": {"context": {"cwd": kwargs["cwd"]}}},
                {"type": "assistant.message", "data": {"content": "an answer"}},
            ]
            (session_dir / "events.jsonl").write_text(
                "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
            )
            return _FakeCompleted(stdout="an answer\n")

        monkeypatch.setattr(_copilot_cli.subprocess, "run", fake_run)
        monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(tmp_path))
        provider = _providers._CopilotCLIProvider()

        with pytest.raises(RuntimeError, match="could not confirm which model"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " 1 "])
    def test_an_affirmative_value_opts_in(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", value)

        assert _providers._CopilotCLIProvider._unverified_model_allowed() is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe"])
    def test_anything_else_fails_closed(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", value)

        assert _providers._CopilotCLIProvider._unverified_model_allowed() is False

    def test_an_absent_variable_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", raising=False)

        assert _providers._CopilotCLIProvider._unverified_model_allowed() is False

    def test_a_confirmed_model_is_published_as_the_fingerprint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """The provider reads the transcript to learn who spoke; it must keep it."""
        monkeypatch.delenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", raising=False)
        _run_writing_session(
            monkeypatch, tmp_path, model="claude-opus-5", contents=["the real answer"]
        )
        provider = _providers._CopilotCLIProvider()

        provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert provider.system_fingerprint == "claude-opus-5"

    def test_an_opted_in_unverified_reply_publishes_no_fingerprint(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """An accepted loss must stay distinguishable from a confirmed answer."""
        monkeypatch.setenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", "1")
        provider = self._fallback(monkeypatch, tmp_path)

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "an answer"
        assert provider.system_fingerprint is None

    def test_a_verified_call_does_not_vouch_for_a_later_unverified_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """The marker is per call. A stale value would forge the confirmation."""
        monkeypatch.delenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", raising=False)
        _run_writing_session(
            monkeypatch, tmp_path, model="claude-opus-5", contents=["the real answer"]
        )
        provider = _providers._CopilotCLIProvider()
        provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")
        assert provider.system_fingerprint == "claude-opus-5"

        monkeypatch.setenv("EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL", "1")
        self._fallback(monkeypatch, tmp_path / "second")
        provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert provider.system_fingerprint is None


# ---------------------------------------------------------------------------
# The session's opening `selectedModel` is not evidence about which model
# produced a reply. A `session.model_change` event can supersede it, and it is
# absent from most real session logs, so reading it both missed substitutions
# and refused the common case. `assistant.message` carries the model that
# generated that specific text, and every observed CLI version emits it.
# ---------------------------------------------------------------------------


def _run_writing_raw_session(
    monkeypatch: pytest.MonkeyPatch, root, build_events, *, stdout: str = "ignored\n"
):
    """Patch subprocess.run so it writes caller-shaped events for the sandbox."""
    import uuid

    def fake_run(argv: list[str], **kwargs: object) -> _FakeCompleted:
        session_dir = root / str(uuid.uuid4())
        session_dir.mkdir(parents=True, exist_ok=True)
        events = build_events(str(kwargs["cwd"]))
        (session_dir / "events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )
        return _FakeCompleted(stdout=stdout)

    monkeypatch.setattr(_copilot_cli.subprocess, "run", fake_run)
    monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(root))


def _start(cwd: str, **extra: object) -> dict:
    return {"type": "session.start", "data": {"context": {"cwd": cwd}, **extra}}


def _msg(content: str, **extra: object) -> dict:
    return {"type": "assistant.message", "data": {"content": content, **extra}}


class TestTheModelIsReadFromTheMessageThatAnswered:
    """The reply's own model is the evidence, not the session's first pick."""

    def test_a_session_without_selectedmodel_still_confirms_the_model(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # Most real session logs carry no `selectedModel` at all. Reading only
        # that field left the model unconfirmed and refused every such run,
        # discarding real data even though the message named the model.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [_start(cwd), _msg("the answer", model="claude-opus-5")],
        )
        provider = _providers._CopilotCLIProvider()

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "the answer"

    def test_the_message_model_overrides_a_stale_selected_model(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # The opening pick agrees with the request while the model that
        # actually answered does not. Trusting the pick would publish Sol's
        # output under Opus's name.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd, selectedModel="claude-opus-5"),
                _msg("the answer", model="gpt-5.6-sol"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        with pytest.raises(RuntimeError, match="ran gpt-5.6-sol instead"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    def test_a_midsession_model_change_is_caught_through_the_message(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # Shaped after a real log: `session.model_change` supersedes the
        # opening pick, and the message that follows carries the new model.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd, selectedModel="claude-opus-5"),
                {
                    "type": "session.model_change",
                    "data": {"newModel": "gpt-5.6-sol", "reasoningEffort": "high"},
                },
                _msg("the answer", model="gpt-5.6-sol"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        with pytest.raises(RuntimeError, match="ran gpt-5.6-sol instead"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    def test_two_models_in_one_answer_confirm_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # A blended answer has no single author, so no model earns the score.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                _msg("first half", model="claude-opus-5"),
                _msg("second half", model="gpt-5.6-sol"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        with pytest.raises(RuntimeError, match="could not confirm which model"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    def test_a_message_that_names_no_model_confirms_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        _run_writing_raw_session(
            monkeypatch, tmp_path, lambda cwd: [_start(cwd), _msg("the answer")]
        )
        provider = _providers._CopilotCLIProvider()

        with pytest.raises(RuntimeError, match="could not confirm which model"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    def test_a_message_holding_no_text_contributes_no_model(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # Only messages whose text reaches the judge may vouch for a model.
        # An empty message is dropped from the answer, so counting its model
        # would refuse a run on evidence the answer never used.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                _msg("   ", model="gpt-5.6-sol"),
                _msg("the answer", model="claude-opus-5"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "the answer"

    def test_a_repeated_model_across_messages_still_confirms_one_author(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                _msg("first", model="claude-opus-5"),
                _msg("second", model="claude-opus-5"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "first\n\nsecond"

    def test_text_from_an_unattributed_message_is_not_vouched_for(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # Both messages reach the judge, but only one says who wrote it.
        # Letting the attributed message speak for both would publish text
        # under a model that may not have produced it.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                _msg("verified part", model="claude-opus-5"),
                _msg("unverified part"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        with pytest.raises(RuntimeError, match="could not confirm which model"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    def test_an_unattributed_empty_message_does_not_taint_confirmation(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # An empty message contributes no text, so it cannot carry unattributed
        # text. Refusing on it would discard a run over evidence the answer
        # never used.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                _msg("  "),
                _msg("the answer", model="claude-opus-5"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "the answer"

    @pytest.mark.parametrize("bad", [123, None, "", {"name": "opus"}, ["opus"]])
    def test_a_lone_message_with_a_blank_model_reads_as_unattributed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, bad: object
    ) -> None:
        # An empty string is not the name of a model. Treating it as one would
        # report a substitution by a model called "", which sends the operator
        # hunting for a swap that never happened instead of fixing the missing
        # attribution. The single message keeps the blend check out of the way,
        # so the refusal can only come from the attribution check.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [_start(cwd), _msg("the answer", model=bad)],
        )
        provider = _providers._CopilotCLIProvider()

        with pytest.raises(RuntimeError, match="could not confirm which model"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    @pytest.mark.parametrize("bad", [123, None, "", {"name": "opus"}, ["opus"]])
    def test_a_message_whose_model_is_not_a_name_is_unattributed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path, bad: object
    ) -> None:
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                _msg("the answer", model=bad),
                _msg("second part", model="claude-opus-5"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        with pytest.raises(RuntimeError, match="could not confirm which model"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")


# ---------------------------------------------------------------------------
# A sub-agent runs its own model and writes into the parent session's log. One
# scan of 3777 session logs found 80498 messages carrying neither marker,
# 117008 carrying both, 2576 carrying `agentId` alone, and none carrying
# `parentToolCallId` alone. Both single-marker shapes are exercised below; the
# `parentToolCallId`-only shape has not been observed in the wild, so its test
# is the only thing holding that half of the disjunction.
# ---------------------------------------------------------------------------


class TestSubAgentOutputIsNotTheModelsAnswer:
    """Only the primary interaction is the reply the judge should score."""

    @staticmethod
    def _sub(content: str, *, model: str, by_agent_id: bool = False) -> dict[str, object]:
        data: dict[str, object] = {"content": content, "model": model}
        event: dict[str, object] = {"type": "assistant.message", "data": data}
        if by_agent_id:
            event["agentId"] = "agent-1"
        else:
            data["parentToolCallId"] = "tool-1"
        return event

    def test_subagent_text_is_kept_out_of_the_graded_answer(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                self._sub("SUBAGENT INTERNAL RESULT", model="claude-opus-5"),
                _msg("PRIMARY USER-FACING ANSWER", model="claude-opus-5"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "PRIMARY USER-FACING ANSWER"

    def test_a_subagent_on_another_model_does_not_refuse_a_good_run(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # Counting the sub-agent's model would read as a blended answer and
        # throw away a run whose user-facing reply came from one model.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                self._sub("side quest", model="gpt-5.6-sol"),
                _msg("the answer", model="claude-opus-5"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "the answer"

    def test_the_event_level_agent_marker_is_honoured_too(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                self._sub("side quest", model="gpt-5.6-sol", by_agent_id=True),
                _msg("the answer", model="claude-opus-5"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "the answer"

    def test_an_unattributed_subagent_message_does_not_veto_the_answer(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # The unattributed veto exists for text that reaches the judge. A
        # sub-agent's text never does, so it must not refuse the run.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                {
                    "type": "assistant.message",
                    "data": {"content": "side quest", "parentToolCallId": "tool-1"},
                },
                _msg("the answer", model="claude-opus-5"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "the answer"

    def test_a_session_of_only_subagent_messages_confirms_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # No primary reply means the transcript answers nothing, so the run
        # falls to stdout and is refused rather than graded on sub-agent text.
        _run_writing_raw_session(
            monkeypatch,
            tmp_path,
            lambda cwd: [
                _start(cwd),
                self._sub("side quest", model="gpt-5.6-sol"),
            ],
        )
        provider = _providers._CopilotCLIProvider()

        with pytest.raises(RuntimeError, match="could not confirm which model"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")


class TestTheTraceRefusalIsDeliberatelyConservative:
    """The trace check refuses a real answer that opens like a trace.

    That is the intended trade, not an oversight. On the stdout fallback there
    is no boundary between a trace and the reply, so the alternative to a
    visible refusal is silently scoring harness output as the model's answer.
    Anyone tempted to loosen the detector has to delete this test first.
    """

    @staticmethod
    def _fallback(monkeypatch: pytest.MonkeyPatch, tmp_path, stdout: str):
        _allow_unverified_model(monkeypatch)
        _capture_run(monkeypatch, _FakeCompleted(stdout=stdout))
        monkeypatch.setenv("COPILOT_SESSION_STATE_DIR", str(tmp_path / "absent"))
        return _providers._CopilotCLIProvider()

    def test_an_answer_that_opens_with_a_marker_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        provider = self._fallback(monkeypatch, tmp_path, "\u25cf a real answer\n")

        with pytest.raises(RuntimeError, match="trace marker"):
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

    def test_the_same_answer_without_the_marker_is_graded(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # Control: the refusal above is caused by the marker, not by the
        # fallback path itself. Without this the test above proves nothing.
        provider = self._fallback(monkeypatch, tmp_path, "a real answer\n")

        out = provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert out == "a real answer"

    def test_the_refusal_does_not_claim_a_trace_was_found(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        # The check cannot tell a trace from an answer that starts alike, so
        # the message must report the marker it saw, not a trace it cannot see.
        provider = self._fallback(monkeypatch, tmp_path, "\u25cf a real answer\n")

        with pytest.raises(RuntimeError) as caught:
            provider.complete(messages=[{"role": "user", "content": "q"}], model="claude-opus-5")

        assert "carries tool-call traces" not in str(caught.value)
        assert "opens with a CLI trace marker" in str(caught.value)
