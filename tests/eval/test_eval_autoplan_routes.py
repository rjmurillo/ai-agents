"""Tests for the autoplan route eval (issue #5389, part 1).

Each executed family gets an intentional failure, so the suite proves it can
detect a regression in that family, not only pass on the happy path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_EVAL_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "eval" / "eval_autoplan_routes.py"
_spec = importlib.util.spec_from_file_location("eval_autoplan_routes", _EVAL_SCRIPT)
assert _spec is not None and _spec.loader is not None
ev = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ev
_spec.loader.exec_module(ev)


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
    path.write_text(
        json.dumps({"schema_version": 1, "scenarios": list(scenarios)}), encoding="utf-8"
    )
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
    assert "unresolved (none): 1/1" in out
    assert "orchestrator fallback: 0/1" in out
    assert "expected dx-review, observed None" in out


def test_unexpected_skill_is_named_in_the_diff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario = _scenario(
        expect={"kind": "specialist", "route": "dx-review", "routes_absent": ["dx-review"]}
    )
    code = ev.main(["--fixtures", str(_write(tmp_path, scenario))])
    assert code == ev.EXIT_FAIL
    out = capsys.readouterr().out
    assert "unexpected skills selected: local:dx-review" in out
    assert "expected kind=specialist route=dx-review; observed kind=specialist" in out


def test_bare_strips_namespace() -> None:
    assert ev.bare("local:dx-review") == "dx-review"
    assert ev.bare("dx-review") == "dx-review"
    assert ev.bare(None) is None


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        json.dumps([]),
        json.dumps({"schema_version": 1, "scenarios": []}),
        json.dumps({"schema_version": 1, "scenarios": ["x"]}),
        json.dumps({"schema_version": 1, "scenarios": [_scenario(id="")]}),
        json.dumps({"schema_version": 1, "scenarios": [_scenario(family="lifecycle")]}),
        json.dumps({"schema_version": 1, "scenarios": [_scenario(expect={"kind": "bogus"})]}),
        json.dumps({"schema_version": 1, "scenarios": [_scenario(expect={"kind": ["none"]})]}),
        json.dumps({"schema_version": 1, "scenarios": [_scenario(expect={"kind": {}})]}),
        json.dumps({"schema_version": 1, "scenarios": [_scenario(expect="none")]}),
        json.dumps(
            {"schema_version": 1, "scenarios": [_scenario(expect={"kind": "none", "route": 3})]}
        ),
        json.dumps(
            {
                "schema_version": 1,
                "scenarios": [_scenario(expect={"kind": "none", "routes_absent": "x"})],
            }
        ),
        json.dumps({"schema_version": 1, "scenarios": [_scenario(), _scenario()]}),
        json.dumps({"schema_version": 1, "scenarios": [_scenario(expect={"kind": "specialist"})]}),
        json.dumps(
            {
                "schema_version": 1,
                "scenarios": [_scenario(expect={"kind": "specialist", "route": None})],
            }
        ),
        json.dumps(
            {
                "schema_version": 1,
                "scenarios": [_scenario(expect={"kind": "specialist", "route": ""})],
            }
        ),
        json.dumps(
            {
                "schema_version": 1,
                "scenarios": [_scenario(expect={"kind": "none"})],
            }
        ),
        json.dumps(
            {
                "schema_version": 1,
                "scenarios": [_scenario(expect={"kind": "none", "route": "dx-review"})],
            }
        ),
        json.dumps(
            {
                "schema_version": 1,
                "scenarios": [_scenario(expect={"kind": "ambiguous", "route": "dx-review"})],
            }
        ),
        json.dumps({"scenarios": [_scenario()]}),
        json.dumps({"schema_version": 2, "scenarios": [_scenario()]}),
        json.dumps({"schema_version": "1", "scenarios": [_scenario()]}),
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


def _fake_main(stdout: str, code: int = 0) -> Any:
    def fake(_argv: list[str]) -> int:
        sys.stdout.write(stdout)
        return code

    return lambda: fake


def test_resolver_output_not_json_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ev, "_load_resolver_main", _fake_main("garbage"))
    with pytest.raises(ev.EvalConfigError, match="not JSON"):
        ev.run_resolver("x", [])


def test_resolver_output_without_kind_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ev, "_load_resolver_main", _fake_main("{}"))
    with pytest.raises(ev.EvalConfigError, match="no valid kind"):
        ev.run_resolver("x", [])


def test_resolver_systemexit_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def exits(_argv: list[str]) -> int:
        raise SystemExit(2)

    monkeypatch.setattr(ev, "_load_resolver_main", lambda: exits)
    with pytest.raises(ev.EvalConfigError, match="exited 2"):
        ev.run_resolver("x", [])


def test_resolver_systemexit_without_int_code_is_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def exits(_argv: list[str]) -> int:
        raise SystemExit("bad")

    monkeypatch.setattr(ev, "_load_resolver_main", lambda: exits)
    with pytest.raises(ev.EvalConfigError, match="exited 2"):
        ev.run_resolver("x", [])


def test_missing_resolver_file_is_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ev, "RESOLVER", tmp_path / "absent.py")
    with pytest.raises(ev.EvalConfigError, match="cannot load resolver"):
        ev.run_resolver("x", [])


def test_broken_resolver_module_is_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "broken.py"
    broken.write_text("def (:\n", encoding="utf-8")
    monkeypatch.setattr(ev, "RESOLVER", broken)
    with pytest.raises(ev.EvalConfigError, match="cannot load resolver"):
        ev.run_resolver("x", [])


def test_non_python_resolver_path_is_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ev, "RESOLVER", tmp_path / "resolver.txt")
    with pytest.raises(ev.EvalConfigError, match="cannot load resolver"):
        ev.run_resolver("x", [])


def test_orchestrator_handoff_counts_apart_from_unresolved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario = _scenario(request="Refactor the loader and the docs in parallel across services.")
    assert ev.main(["--fixtures", str(_write(tmp_path, scenario))]) == ev.EXIT_FAIL
    out = capsys.readouterr().out
    assert "orchestrator fallback: 1/1" in out
    assert "unresolved (none): 0/1" in out


@pytest.mark.parametrize(
    ("expected", "observed", "matches"),
    [
        ("dx-review", "local:dx-review", True),
        ("dx-review", "gstack:dx-review", True),
        ("local:dx-review", "local:dx-review", True),
        ("gstack:dx-review", "local:dx-review", False),
        ("dx-review", "local:other", False),
        (None, None, True),
        (None, "local:dx-review", False),
        ("dx-review", None, False),
    ],
)
def test_route_matches_pins_a_qualified_namespace(
    expected: str | None, observed: str | None, matches: bool
) -> None:
    assert ev.route_matches(expected, observed) is matches


def test_wrong_namespace_fails_when_the_fixture_is_qualified() -> None:
    scenario = ev.Scenario("s", "explicit-skill", "r", "explicit", "gstack:dx-review", ())
    observed = {"kind": "explicit", "route": "local:dx-review", "candidates": ["local:dx-review"]}
    problems = ev.score(scenario, observed)
    assert problems[0].startswith("expected kind=explicit route=gstack:dx-review")
    assert "route: expected gstack:dx-review, observed local:dx-review" in problems


def test_qualified_routes_absent_only_blocks_that_namespace() -> None:
    scenario = ev.Scenario(
        "s", "explicit-skill", "r", "explicit", "dx-review", ("gstack:dx-review",)
    )
    ok = {"kind": "explicit", "route": "local:dx-review", "candidates": ["local:dx-review"]}
    bad = {"kind": "explicit", "route": "gstack:dx-review", "candidates": ["gstack:dx-review"]}
    assert ev.score(scenario, ok) == []
    assert "unexpected skills selected: gstack:dx-review" in ev.score(scenario, bad)


def test_resolver_kind_of_wrong_type_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ev, "_load_resolver_main", _fake_main('{"kind": ["x"]}'))
    with pytest.raises(ev.EvalConfigError, match="no valid kind"):
        ev.run_resolver("x", [])


def test_resolver_kind_outside_vocabulary_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ev, "_load_resolver_main", _fake_main('{"kind": "bogus"}'))
    with pytest.raises(ev.EvalConfigError, match="no valid kind"):
        ev.run_resolver("x", [])


@pytest.mark.parametrize("candidates", ['"x"', '{"a": 1}', "[1]", "null"])
def test_resolver_candidates_of_wrong_shape_is_config_error(
    monkeypatch: pytest.MonkeyPatch, candidates: str
) -> None:
    stdout = '{"kind": "none", "route": null, "candidates": ' + candidates + "}"
    monkeypatch.setattr(ev, "_load_resolver_main", _fake_main(stdout))
    with pytest.raises(ev.EvalConfigError, match="candidates must be a list of strings"):
        ev.run_resolver("x", [])


def test_resolver_without_callable_main_is_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    no_main = tmp_path / "no_main.py"
    no_main.write_text("main = 3\n", encoding="utf-8")
    monkeypatch.setattr(ev, "RESOLVER", no_main)
    ev._RESOLVER_CACHE.clear()
    with pytest.raises(ev.EvalConfigError, match="no callable main"):
        ev.run_resolver("x", [])


def test_resolver_main_is_loaded_once() -> None:
    ev._RESOLVER_CACHE.clear()
    first = ev._load_resolver_main()
    assert ev._load_resolver_main() is first


@pytest.mark.parametrize(
    ("stdout", "match"),
    [
        ('{"kind": "none"}', "lacks route, candidates"),
        ('{"kind": "none", "route": null}', "lacks candidates"),
        ('{"kind": "none", "candidates": []}', "lacks route"),
        ('{"kind": "specialist", "route": {}, "candidates": []}', "route must be a string or null"),
        ('{"kind": "specialist", "route": 3, "candidates": []}', "route must be a string or null"),
    ],
)
def test_incomplete_or_malformed_resolver_payload_is_config_error(
    monkeypatch: pytest.MonkeyPatch, stdout: str, match: str
) -> None:
    monkeypatch.setattr(ev, "_load_resolver_main", _fake_main(stdout))
    with pytest.raises(ev.EvalConfigError, match=match):
        ev.run_resolver("x", [])


def test_incomplete_payload_fails_a_none_scenario_as_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = _write(tmp_path, _scenario(expect={"kind": "none", "route": None}))
    monkeypatch.setattr(ev, "_load_resolver_main", _fake_main('{"kind": "none"}'))
    assert ev.main(["--fixtures", str(fixtures)]) == ev.EXIT_CONFIG
    assert "ERROR" in capsys.readouterr().err


def test_single_domain_specialist_resolved_to_the_orchestrator_fails_and_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = _write(tmp_path, _scenario(request="developer friction audit please"))
    payload = '{"kind": "orchestrator", "route": "orchestrator", "candidates": ["orchestrator"]}'
    monkeypatch.setattr(ev, "_load_resolver_main", _fake_main(payload))
    code = ev.main(["--fixtures", str(fixtures)])
    out = capsys.readouterr().out
    assert code == ev.EXIT_FAIL
    assert "orchestrator fallback: 1/1" in out
    assert "unresolved (none): 0/1" in out
    assert "kind: expected specialist, observed orchestrator" in out
