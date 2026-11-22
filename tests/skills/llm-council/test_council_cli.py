"""Tests for the council.py script route, driven through main(argv).

The model call is replaced by a fake, so no test reaches a model or the gh CLI.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "llm_council_support", Path(__file__).with_name("_support.py")
)
if _SUPPORT_SPEC is None or _SUPPORT_SPEC.loader is None:
    raise ImportError("llm-council _support.py is missing")
support = importlib.util.module_from_spec(_SUPPORT_SPEC)
_SUPPORT_SPEC.loader.exec_module(support)

council = support.load_script("council.py", "council_cli_t")

RANKING = (
    "Looks fine.\n\nFINAL RANKING:\n1. Response A\n2. Response B\n3. Response C\n4. Response D\n"
)


def _fake(fail=(), empty=()):
    calls = []

    def fake_call_model(token, model, prompt, **kw):
        calls.append((model, prompt[:40]))
        if model in fail:
            raise RuntimeError(f"{model} is down")
        if model in empty:
            return "   "
        if prompt.startswith("You are evaluating"):
            return RANKING
        if prompt.startswith("You are the Chairman"):
            return "Chairman verdict."
        return f"answer from {model}"

    return fake_call_model, calls


@pytest.fixture(autouse=True)
def _no_gh(monkeypatch):
    def boom():
        raise AssertionError("gh token fetched for a Copilot-only council")

    monkeypatch.setattr(council, "gh_token", boom)


def test_full_run_writes_artifact_and_prints_synthesis(tmp_path, monkeypatch, capsys):
    fake, calls = _fake()
    monkeypatch.setattr(council, "call_model", fake)
    out = tmp_path / "run.md"

    code = council.main(["Should we ship?", "--mode", "design", "--out", str(out), "--quiet"])

    assert code == 0
    assert capsys.readouterr().out.strip() == "Chairman verdict."
    md = out.read_text(encoding="utf-8")
    assert "# LLM Council: design mode" in md
    assert "## Borda Ranking (lower = better)" in md
    models = [m for m, _ in calls]
    assert models.count("gpt-6.2-astra") == 3  # councillor, ranker, chairman
    assert len(models) == 4 + 4 + 1


def test_too_few_answers_exits_2(tmp_path, monkeypatch):
    fake, _ = _fake(fail=("gpt-6.2-sol", "claude-opus-5.5"))
    monkeypatch.setattr(council, "call_model", fake)

    code = council.main(["Q?", "--out", str(tmp_path / "r.md"), "--quiet"])

    assert code == 2
    assert not (tmp_path / "r.md").exists()


def test_failed_and_empty_councillors_are_reported_in_artifact(tmp_path, monkeypatch):
    fake, _ = _fake(fail=("gpt-6.2-sol",), empty=("grok-4.7",))
    monkeypatch.setattr(council, "call_model", fake)
    out = tmp_path / "r.md"

    code = council.main(["Q?", "--out", str(out), "--min-responses", "2", "--quiet"])

    md = out.read_text(encoding="utf-8")
    assert code == 0
    assert "`gpt-6.2-sol`: gpt-6.2-sol is down" in md
    assert "`grok-4.7`: empty response" in md


def test_min_responses_clamps_to_council_size(tmp_path, monkeypatch):
    fake, _ = _fake()
    monkeypatch.setattr(council, "call_model", fake)

    code = council.main(
        [
            "Q?",
            "--models",
            "gpt-6.2-sol,claude-opus-5.5",
            "--out",
            str(tmp_path / "r.md"),
            "--quiet",
        ]
    )

    assert code == 0


def test_chairman_failure_still_writes_artifact(tmp_path, monkeypatch):
    fake, _ = _fake()

    def chair_fails(token, model, prompt, **kw):
        if prompt.startswith("You are the Chairman"):
            raise RuntimeError("chair down")
        return fake(token, model, prompt, **kw)

    monkeypatch.setattr(council, "call_model", chair_fails)
    out = tmp_path / "r.md"

    assert council.main(["Q?", "--out", str(out), "--quiet"]) == 0
    assert "[Chairman synthesis failed: chair down]" in out.read_text(encoding="utf-8")


def test_github_models_member_without_gh_exits_1(tmp_path, monkeypatch):
    def no_gh():
        raise FileNotFoundError("gh")

    monkeypatch.setattr(council, "gh_token", no_gh)

    with pytest.raises(SystemExit) as exc:
        council.main(["Q?", "--cheap", "--out", str(tmp_path / "r.md"), "--quiet"])
    assert exc.value.code == 1


def test_default_artifact_path_uses_artifact_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(tmp_path))
    fake, _ = _fake()
    monkeypatch.setattr(council, "call_model", fake)

    assert council.main(["Q?", "--quiet"]) == 0
    assert len(list((tmp_path / "council" / "runs").glob("*.md"))) == 1


def test_help_runs_as_a_script():
    script = (
        Path(__file__).resolve().parents[3] / "src/claude/skills/llm-council/scripts/council.py"
    )

    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert proc.returncode == 0, proc.stderr
    assert "--min-responses" in proc.stdout


# --min-responses floor and member slug collisions


@pytest.mark.parametrize("value", ["0", "-1", "-5"])
def test_min_responses_below_one_exits_2_before_any_model_call(
    tmp_path, monkeypatch, capsys, value
):
    fake, calls = _fake()
    monkeypatch.setattr(council, "call_model", fake)
    out = tmp_path / "run.md"

    code = council.main(["q", "--min-responses", value, "--out", str(out), "--quiet"])

    assert code == 2
    assert f"--min-responses must be at least 1, got {value}" in capsys.readouterr().err
    assert calls == []
    assert not out.exists()


def test_min_responses_of_one_is_accepted(tmp_path, monkeypatch):
    fake, _ = _fake(fail=("gpt-6.2-sol", "claude-opus-5.5", "grok-4.7"))
    monkeypatch.setattr(council, "call_model", fake)

    code = council.main(
        [
            "q",
            "--min-responses",
            "1",
            "--mode",
            "design",
            "--out",
            str(tmp_path / "r.md"),
            "--quiet",
        ]
    )

    assert code == 0


def test_colliding_member_slugs_exit_2_naming_both_ids(tmp_path, monkeypatch, capsys):
    fake, calls = _fake()
    monkeypatch.setattr(council, "call_model", fake)
    out = tmp_path / "run.md"

    code = council.main(
        ["q", "--models", "openai/gpt-4.1,openai_gpt-4.1", "--out", str(out), "--quiet"]
    )

    assert code == 2
    err = capsys.readouterr().err
    assert "'openai/gpt-4.1'" in err
    assert "'openai_gpt-4.1'" in err
    assert calls == []
    assert not out.exists()


@pytest.mark.parametrize("models", [",", " , ,", "   "])
def test_models_naming_no_ids_exit_2_before_any_call(tmp_path, monkeypatch, capsys, models):
    fake, calls = _fake()
    monkeypatch.setattr(council, "call_model", fake)
    out = tmp_path / "run.md"

    code = council.main(["q", "--models", models, "--out", str(out), "--quiet"])

    assert code == 2
    assert "the council is empty" in capsys.readouterr().err
    assert calls == []
    assert not out.exists()


def test_distinct_member_slugs_are_accepted(tmp_path, monkeypatch):
    fake, _ = _fake()
    monkeypatch.setattr(council, "call_model", fake)

    code = council.main(
        [
            "q",
            "--models",
            "claude-opus-5.5,gpt-6.2-sol",
            "--chairman",
            "gpt-6.2-astra",
            "--out",
            str(tmp_path / "r.md"),
            "--quiet",
        ]
    )

    assert code == 0
