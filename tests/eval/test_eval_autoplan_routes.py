"""Tests for the autoplan route eval (issue #5389, part 1).

Each executed family gets an intentional failure, so the suite proves it can
detect a regression in that family, not only pass on the happy path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import eval_autoplan_routes as ev  # noqa: E402


def _scenario(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "s1",
        "family": "long-tail-single-domain",
        "request": "Audit our CLI onboarding workflow for developer friction.",
        "expect": {"kind": "specialist", "route": "dx-review", "routes_absent": []},
    }
    base.update(over)
    return base


def _write(tmp_path: Path, *scenarios: dict[str, Any]) -> Path:
    path = tmp_path / "routes.json"
    path.write_text(json.dumps({"scenarios": list(scenarios)}), encoding="utf-8")
    return path


def _catalog(tmp_path: Path, name: str, intents: list[str]) -> Path:
    root = tmp_path / "skills"
    skill = root / name
    skill.mkdir(parents=True)
    lines = ["---", f"name: {name}", "metadata:", "  routing:", "    role: front-door"]
    lines += ["    invoker: autoplan", "    trigger: t", "    user-facing: true", "    intents:"]
    lines += [f"      - {i}" for i in intents]
    lines += ["---", "", "Body."]
    (skill / "SKILL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def test_shipped_fixtures_all_pass(capsys: pytest.CaptureFixture[str]) -> None:
    assert ev.main([]) == ev.EXIT_OK
    out = capsys.readouterr().out
    assert "orchestrator fallback: 0/" in out
    for family in ev.NOT_EXECUTED_FAMILIES:
        assert f"not executed {family}" in out


def test_shipped_fixtures_cover_every_executed_family() -> None:
    families = {s.family for s in ev.load_scenarios(ev.DEFAULT_FIXTURES)}
    assert families == set(ev.EXECUTED_FAMILIES)


def test_shipped_fixtures_name_the_issue_skills() -> None:
    routes = {ev.bare(s.route) for s in ev.load_scenarios(ev.DEFAULT_FIXTURES)}
    assert {
        "business-strategy",
        "dx-review",
        "world-model-diagnostic",
        "programming-advisor",
        "buy-vs-build-framework",
    } <= routes


def test_report_is_byte_stable(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    ev.main(["--output", str(first)])
    ev.main(["--output", str(second)])
    assert first.read_bytes() == second.read_bytes()


FAILING = {
    "explicit-skill": _scenario(
        family="explicit-skill",
        request="run /dx-review on this change",
        expect={"kind": "explicit", "route": "build", "routes_absent": []},
    ),
    "long-tail-single-domain": _scenario(
        expect={"kind": "specialist", "route": "business-strategy", "routes_absent": []},
    ),
    "multi-domain-handoff": _scenario(
        family="multi-domain-handoff",
        request="Refactor the loader and update the docs in parallel across services.",
        expect={"kind": "specialist", "route": "dx-review", "routes_absent": []},
    ),
    "negative-noise": _scenario(
        family="negative-noise",
        expect={"kind": "none", "route": None, "routes_absent": ["dx-review"]},
    ),
    "failure-fallback": _scenario(
        family="failure-fallback",
        request="use the nonexistent-skill skill",
        expect={"kind": "specialist", "route": "dx-review", "routes_absent": []},
    ),
}


@pytest.mark.parametrize("family", sorted(FAILING))
def test_intentional_failure_per_family(
    family: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = ev.main(["--fixtures", str(_write(tmp_path, FAILING[family]))])
    out = capsys.readouterr().out
    assert code == ev.EXIT_FAIL
    assert f"FAIL s1 [{family}]" in out
    assert "expected" in out and "observed" in out


def test_failing_families_match_executed_families() -> None:
    assert set(FAILING) == set(ev.EXECUTED_FAMILIES)


def test_specialist_falling_through_to_orchestrator_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _catalog(tmp_path, "unrelated-skill", ["something else entirely"])
    fixtures = _write(tmp_path, _scenario(request="developer friction audit please"))
    code = ev.main(["--fixtures", str(fixtures), "--skills-root", str(root)])
    out = capsys.readouterr().out
    assert code == ev.EXIT_FAIL
    assert "orchestrator fallback: 1/1" in out
    assert "expected dx-review, observed None" in out


def test_unexpected_skill_is_named_in_the_diff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario = _scenario(
        expect={"kind": "specialist", "route": "dx-review", "routes_absent": ["dx-review"]}
    )
    code = ev.main(["--fixtures", str(_write(tmp_path, scenario))])
    assert code == ev.EXIT_FAIL
    assert "unexpected skills selected: dx-review" in capsys.readouterr().out


def test_bare_strips_namespace() -> None:
    assert ev.bare("local:dx-review") == "dx-review"
    assert ev.bare("dx-review") == "dx-review"
    assert ev.bare(None) is None


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        json.dumps([]),
        json.dumps({"scenarios": []}),
        json.dumps({"scenarios": ["x"]}),
        json.dumps({"scenarios": [_scenario(id="")]}),
        json.dumps({"scenarios": [_scenario(family="lifecycle")]}),
        json.dumps({"scenarios": [_scenario(expect={"kind": "bogus"})]}),
        json.dumps({"scenarios": [_scenario(expect={"kind": "none", "route": 3})]}),
        json.dumps({"scenarios": [_scenario(expect={"kind": "none", "routes_absent": "x"})]}),
        json.dumps({"scenarios": [_scenario(), _scenario()]}),
    ],
)
def test_bad_fixtures_are_config_errors(
    payload: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "routes.json"
    path.write_text(payload, encoding="utf-8")
    assert ev.main(["--fixtures", str(path)]) == ev.EXIT_CONFIG
    assert "ERROR" in capsys.readouterr().err


def test_missing_fixture_file_is_config_error(tmp_path: Path) -> None:
    assert ev.main(["--fixtures", str(tmp_path / "nope.json")]) == ev.EXIT_CONFIG


def test_resolver_config_error_is_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = _write(tmp_path, _scenario())
    code = ev.main(["--fixtures", str(fixtures), "--skills-root", str(tmp_path / "absent")])
    assert code == ev.EXIT_CONFIG
    assert "resolver exited 2" in capsys.readouterr().err


def test_unwritable_output_is_config_error(tmp_path: Path) -> None:
    code = ev.main(["--output", str(tmp_path / "no-dir" / "r.json")])
    assert code == ev.EXIT_CONFIG


def test_resolver_output_not_json_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Proc:
        returncode = 0
        stdout = "garbage"
        stderr = ""

    monkeypatch.setattr(ev.subprocess, "run", lambda *a, **k: Proc())
    with pytest.raises(ev.EvalConfigError, match="not JSON"):
        ev.run_resolver("x", [])


def test_resolver_output_without_kind_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Proc:
        returncode = 0
        stdout = "{}"
        stderr = ""

    monkeypatch.setattr(ev.subprocess, "run", lambda *a, **k: Proc())
    with pytest.raises(ev.EvalConfigError, match="no valid kind"):
        ev.run_resolver("x", [])


def test_resolver_spawn_failure_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> None:
        raise OSError("no exec")

    monkeypatch.setattr(ev.subprocess, "run", boom)
    with pytest.raises(ev.EvalConfigError, match="did not run"):
        ev.run_resolver("x", [])
