"""`added_failures` and the resolver loader in skillforge's frontmatter lint.

The standalone linter exits 1 for a MUST rule that is NOT_EVALUATED, so the
skillopt candidate gate must treat a newly NOT_EVALUATED MUST rule the same way.
The routing-phrase rule loads autoplan's resolver; a missing or renamed
private name must report NOT_EVALUATED, never crash `evaluate`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.skills.skillforge.lint_support import _skill_text, lint

_VALID_CAPABILITY = "  capability:\n    kind: orchestrator\n"
_FLOW_CAPABILITY = "  capability: {kind: orchestrator}\n"
_ROUTING_PHRASE = 'Demo skill. Use when you say "ship the thing". Do NOT use for other work.'
_ROUTING_META = "  routing:\n    role: front-door\n    intents:\n      - ship the thing\n"


def _rule(rule_id: str) -> Any:
    return next(rule for rule in lint.RULES if rule.id == rule_id)


def _result(rule_id: str, status: str) -> Any:
    return lint.Result(_rule(rule_id), status, ("because",))


def _ids(results: list[Any]) -> list[str]:
    return [r.rule.id for r in results]


def test_must_rule_not_evaluated_after_passing_is_an_added_failure() -> None:
    before = [_result("fm.capability.shape", "PASS")]
    after = [_result("fm.capability.shape", "NOT_EVALUATED")]

    assert _ids(lint.added_failures(before, after)) == ["fm.capability.shape"]


def test_must_rule_failing_after_passing_is_an_added_failure() -> None:
    before = [_result("fm.capability.shape", "PASS")]
    after = [_result("fm.capability.shape", "FAIL")]

    assert _ids(lint.added_failures(before, after)) == ["fm.capability.shape"]


def test_inherited_not_evaluated_is_not_an_added_failure() -> None:
    before = [_result("fm.capability.shape", "NOT_EVALUATED")]
    after = [_result("fm.capability.shape", "NOT_EVALUATED")]

    assert lint.added_failures(before, after) == []


def test_a_new_violation_of_an_already_failing_rule_is_an_added_failure() -> None:
    rule = _rule("fm.artifacts.shape")
    before = [lint.Result(rule, "FAIL", ("old violation",))]
    after = [lint.Result(rule, "FAIL", ("old violation", "new violation"))]

    added = lint.added_failures(before, after)

    assert [r.messages for r in added] == [("new violation",)]


def test_new_failures_reports_a_second_bad_path_beside_an_inherited_one() -> None:
    incumbent = _skill_text("  outputs:\n    old-note:\n      path: /outside\n")
    candidate = _skill_text(
        "  outputs:\n    old-note:\n      path: /outside\n    new-note:\n      path: ../outside\n"
    )

    added = lint.new_failures(incumbent, candidate)

    assert _ids(added) == ["fm.artifacts.shape"]
    assert all("new-note" in message for message in added[0].messages)


def test_shrinking_an_oversized_skill_is_not_an_added_failure() -> None:
    incumbent = _skill_text(body="a" * 25000 + "\n")
    candidate = _skill_text(body="a" * 24900 + "\n")

    assert lint.new_failures(incumbent, candidate) == []


def test_growing_an_oversized_skill_is_an_added_failure() -> None:
    incumbent = _skill_text(body="a" * 25000 + "\n")
    candidate = _skill_text(body="a" * 40000 + "\n")

    assert _ids(lint.new_failures(incumbent, candidate)) == ["fm.size.bytes"]


def test_crossing_the_size_cap_is_an_added_failure() -> None:
    incumbent = _skill_text(body="a" * 100 + "\n")
    candidate = _skill_text(body="a" * 25000 + "\n")

    assert _ids(lint.new_failures(incumbent, candidate)) == ["fm.size.bytes"]


def test_inherited_fail_is_not_an_added_failure() -> None:
    before = [_result("fm.capability.shape", "FAIL")]
    after = [_result("fm.capability.shape", "FAIL")]

    assert lint.added_failures(before, after) == []


def test_should_rule_not_evaluated_after_passing_is_not_an_added_failure() -> None:
    before = [_result("fm.routing.phrases-routable", "PASS")]
    after = [_result("fm.routing.phrases-routable", "NOT_EVALUATED")]

    assert lint.added_failures(before, after) == []


def test_new_failures_reports_a_must_rule_the_candidate_cannot_evaluate() -> None:
    incumbent = _skill_text(_VALID_CAPABILITY)
    candidate = _skill_text(_FLOW_CAPABILITY)
    assert {r.rule.id: r.status for r in lint.lint_text(incumbent)}["fm.capability.shape"] == "PASS"

    added = {r.rule.id: r.status for r in lint.new_failures(incumbent, candidate)}

    assert added["fm.capability.shape"] == "NOT_EVALUATED"
    assert added["fm.subset-parse"] == "FAIL"


def test_new_failures_is_empty_for_an_unchanged_skill() -> None:
    text = _skill_text(_VALID_CAPABILITY)

    assert lint.new_failures(text, text) == []


# --- resolver loading ------------------------------------------------------


def _checks_globals() -> dict[str, object]:
    """The namespace of `_lint_frontmatter_checks`, reached through a rule check."""
    return _rule("fm.routing.phrases-routable").check.__globals__


def _install_resolver(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, source: str | None) -> Path:
    """Point the loader at a stub `resolve_route.py` and start with a cold cache."""
    script = tmp_path / "resolve_route.py"
    if source is not None:
        script.write_text(source, encoding="utf-8")
    namespace = _checks_globals()
    monkeypatch.setitem(namespace, "_RESOLVER_PATH", script)
    monkeypatch.setitem(namespace, "_resolver_cache", [])
    return script


def _routing_status() -> str:
    text = _skill_text(_ROUTING_META, description=_ROUTING_PHRASE)
    return {r.rule.id: r.status for r in lint.lint_text(text)}["fm.routing.phrases-routable"]


def test_resolver_missing_a_private_name_is_not_evaluated_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_resolver(
        monkeypatch, tmp_path, "def _matches_ordered(request, intent):\n    return True\n"
    )

    assert _routing_status() == "NOT_EVALUATED"


def test_resolver_that_fails_to_import_is_not_evaluated_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_resolver(monkeypatch, tmp_path, "raise RuntimeError('boom')\n")

    assert _routing_status() == "NOT_EVALUATED"


def test_resolver_absent_is_not_evaluated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_resolver(monkeypatch, tmp_path, None)

    assert _routing_status() == "NOT_EVALUATED"


def test_a_complete_resolver_decides_the_rule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = (
        "def _tokenize(text):\n    return text.split()\n"
        "def _matches_ordered(request, intent):\n    return request == intent\n"
    )
    _install_resolver(monkeypatch, tmp_path, source)

    assert _routing_status() == "PASS"


def test_resolver_loads_once_per_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    counter = tmp_path / "loads.txt"
    source = (
        f"open({str(counter)!r}, 'a').write('x')\n"
        "def _tokenize(text):\n    return text.split()\n"
        "def _matches_ordered(request, intent):\n    return request == intent\n"
    )
    _install_resolver(monkeypatch, tmp_path, source)

    _routing_status()
    _routing_status()

    assert counter.read_text(encoding="utf-8") == "x"
