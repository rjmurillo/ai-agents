"""The sampler forces lefthook's summary output on (issue #6734).

``lefthook.yml`` leaves ``summary`` out of its ``output`` setting. Lefthook then
prints no summary block, ``parse_summary`` finds no jobs, and a report silently degrades
to the hook wall clock alone. The sampler overrides ``LEFTHOOK_OUTPUT`` for the
measured subprocess, so these tests pin the override, its precedence over an
inherited value, and that the rest of the environment still reaches the hook.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.metrics import gate_latency_sampler as gls_sampler
from tests.metrics.gate_latency_helpers import _FakeCompleted

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_SUMMARY_STDOUT = "summary: (done in 0.19 seconds)\n✓ security-suppressions-staged (0.19 seconds)\n"


def _env_capturing_fake(seen: dict[str, object]) -> object:
    def _fake(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        if cmd and cmd[0] == "git":
            return _FakeCompleted(0, "")
        seen["env"] = kwargs.get("env")
        return _FakeCompleted(0, _SUMMARY_STDOUT)

    return _fake


def test_positive_the_lefthook_call_forces_summary_output(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(subprocess, "run", _env_capturing_fake(seen))

    run = gls_sampler._run_repetition(repo, ["lefthook"], "pre-push", (), 0)

    env = seen["env"]
    assert isinstance(env, dict)
    assert "summary" in env["LEFTHOOK_OUTPUT"].split(",")
    assert run.jobs_parsed == 1


def test_negative_an_inherited_setting_that_hides_the_summary_is_overridden(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setenv("LEFTHOOK_OUTPUT", "failure")
    monkeypatch.setattr(subprocess, "run", _env_capturing_fake(seen))

    gls_sampler._run_repetition(repo, ["lefthook"], "pre-commit", (), 0)

    env = seen["env"]
    assert isinstance(env, dict)
    assert env["LEFTHOOK_OUTPUT"] == gls_sampler._LEFTHOOK_OUTPUT


def test_edge_the_rest_of_the_environment_still_reaches_the_hook(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setenv("GATE_LATENCY_PROBE_MARKER", "kept")
    monkeypatch.setattr(subprocess, "run", _env_capturing_fake(seen))

    gls_sampler._run_repetition(repo, ["lefthook"], "pre-push", (), 0)

    env = seen["env"]
    assert isinstance(env, dict)
    assert env["GATE_LATENCY_PROBE_MARKER"] == "kept"


def test_premise_lefthook_config_still_hides_the_summary() -> None:
    """If this fails, the override may be dead weight; re-read the docstring."""
    config = yaml.safe_load((_PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    output = config.get("output")
    hidden = output is False or (isinstance(output, list) and "summary" not in output)
    assert hidden, f"lefthook.yml output={output!r} now prints the summary"
