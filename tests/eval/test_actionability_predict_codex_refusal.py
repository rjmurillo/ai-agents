"""predict refuses the Codex CLI transport, which cannot turn tools off (review finding 10)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tests.eval._actionability_arms_test_support import (
    FakeCallApi,
    aa,
    heldout_rows,
    install_call_api,
    pm,
    predict_argv,
    write_corpus_file,
)

_EVAL_DIR = str(Path(__file__).resolve().parents[2] / "scripts" / "eval")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


def _run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *extra: str
) -> tuple[int, FakeCallApi, Path]:
    fake = install_call_api(monkeypatch, FakeCallApi())
    corpus = write_corpus_file(tmp_path, heldout_rows(2))
    out = tmp_path / "pred.jsonl"
    return aa.main(predict_argv(corpus, out, *extra)), fake, out


class TestCodexRefusal:
    @pytest.mark.parametrize("name", ["codex-cli", "codex-subscription", " Codex-CLI "])
    def test_the_flag_is_refused_before_any_call_or_write(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        name: str,
    ) -> None:
        code, fake, out = _run(tmp_path, monkeypatch, "--provider", name)

        assert code == 2
        assert fake.calls == []
        assert not out.exists()
        assert "disables its shell and file tools" in capsys.readouterr().err

    def test_the_env_provider_is_refused_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The same transport selected through EVAL_PROVIDER."""
        monkeypatch.setenv("EVAL_PROVIDER", "codex-cli")

        code, fake, _ = _run(tmp_path, monkeypatch)

        assert code == 2
        assert fake.calls == []

    @pytest.mark.parametrize("name", ["fake", "claude-cli", "copilot-cli", "codex-api", "openai"])
    def test_other_providers_are_not_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
    ) -> None:
        """No over-fire: only the Codex CLI cell is refused, including the metered codex-api."""
        code, fake, _ = _run(tmp_path, monkeypatch, "--provider", name)

        assert code == 0
        assert len(fake.calls) == 2

    def test_the_refused_names_match_the_provider_registry(self) -> None:
        """Every registry row that builds the Codex CLI provider is in the refused set."""
        if _EVAL_DIR not in sys.path:
            sys.path.insert(0, _EVAL_DIR)
        providers = importlib.import_module("_providers")
        in_registry = {
            name
            for name, factory in providers._REGISTRY.items()
            if factory is providers._make_codex_cli
        }

        assert in_registry == set(pm.CODEX_CLI_PROVIDERS)
