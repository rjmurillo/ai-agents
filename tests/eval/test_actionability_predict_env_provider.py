"""The Anthropic key check follows the effective provider (review finding 7).

An explicit ``--provider`` and the ``EVAL_PROVIDER`` variable pick the same transport in
``call_api``, so the key precondition has to treat them alike.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.eval._actionability_arms_test_support import (
    FakeCallApi,
    aa,
    heldout_rows,
    install_call_api,
    predict_argv,
    write_corpus_file,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *extra: str) -> tuple[int, FakeCallApi]:
    fake = install_call_api(monkeypatch, FakeCallApi())
    corpus = write_corpus_file(tmp_path, heldout_rows(2))
    code = aa.main(predict_argv(corpus, tmp_path / "pred.jsonl", *extra))
    return code, fake


class TestEnvProvider:
    def test_an_alternate_env_provider_runs_without_an_anthropic_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """EVAL_PROVIDER=fake and no --provider used to exit 2 for a missing key."""
        monkeypatch.setenv("EVAL_PROVIDER", "fake")

        code, fake = _run(tmp_path, monkeypatch)

        assert code == 0
        assert len(fake.calls) == 2

    @pytest.mark.parametrize("name", ["anthropic", "Anthropic", " claude-api ", "anthropic-http"])
    def test_an_explicit_default_provider_without_a_key_exits_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        """The inverse: naming the default transport still needs its key."""
        code, fake = _run(tmp_path, monkeypatch, "--provider", name)

        assert code == 2
        assert fake.calls == []
        assert not (tmp_path / "pred.jsonl").exists()
        assert "ANTHROPIC_API_KEY" in capsys.readouterr().err

    def test_the_default_env_provider_without_a_key_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EVAL_PROVIDER", "anthropic")

        code, fake = _run(tmp_path, monkeypatch)

        assert code == 2
        assert fake.calls == []

    def test_the_flag_beats_the_env_provider(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--provider fake wins over EVAL_PROVIDER=anthropic, so no key is needed."""
        monkeypatch.setenv("EVAL_PROVIDER", "anthropic")

        code, _ = _run(tmp_path, monkeypatch, "--provider", "fake")

        assert code == 0
