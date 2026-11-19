"""Tests for the report-only resolver evidence helpers (DESIGN-036 amendment).

The resolver is an import boundary, so tests hand the helpers a fake resolver
tuple `(module, roots)`. The fake `resolve(request, roots)` answers from a table
of canned results, which keeps each test about the helper's own comparison and
counting rules.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import skill_routing_resolver_evidence as evidence

Routes = dict[str, dict[str, object]]


def _specialist(*candidates: str) -> dict[str, object]:
    return {"kind": "specialist", "candidates": list(candidates)}


def _fake_resolver(routes: Routes) -> tuple[SimpleNamespace, list[object]]:
    """Return a resolver tuple whose `resolve` answers from `routes`."""

    def resolve(request: str, roots: list[object]) -> dict[str, object]:
        return routes.get(request, {"kind": "none", "candidates": []})

    return SimpleNamespace(resolve=resolve), []


def _door(
    name: str,
    *,
    intents: tuple[str, ...] = ("do the thing",),
    description: str = "Use when you say `do the thing`.",
    shipped: bool = True,
) -> evidence.FrontDoor:
    return evidence.FrontDoor(name, shipped, intents, description)


# --- trigger_phrases --------------------------------------------------------


def test_trigger_phrases_returns_none_without_the_lead_in() -> None:
    assert evidence.trigger_phrases("Plans work. Triggers on `plan`.") is None


def test_trigger_phrases_extracts_backtick_and_double_quote_phrases() -> None:
    description = 'Use when you say `plan this` or "break it down". Do NOT use for `other`.'

    assert evidence.trigger_phrases(description) == ("plan this", "break it down")


def test_trigger_phrases_clause_stops_at_the_first_period_outside_quotes() -> None:
    description = "Use when you say `first`. Also `second`."

    assert evidence.trigger_phrases(description) == ("first",)


def test_trigger_phrases_period_inside_a_quoted_phrase_does_not_end_the_clause() -> None:
    description = 'Use when you say "fix v1.2 now" or `run tool.py`. Skip `later`.'

    assert evidence.trigger_phrases(description) == ("fix v1.2 now", "run tool.py")


def test_trigger_phrases_lead_in_is_case_insensitive() -> None:
    assert evidence.trigger_phrases("USE WHEN YOU SAY `go`.") == ("go",)


def test_trigger_phrases_returns_empty_tuple_when_the_clause_quotes_nothing() -> None:
    assert evidence.trigger_phrases("Use when you say anything at all.") == ()


def test_trigger_phrases_collapses_folded_whitespace() -> None:
    description = "Use when you say `plan\n  this`,\n`ship it`."

    assert evidence.trigger_phrases(description) == ("plan this", "ship it")


# --- intent_reachable -------------------------------------------------------


def test_intent_reachable_when_an_intent_routes_to_the_skill_alone() -> None:
    resolver = _fake_resolver({"do the thing": _specialist("project-toolkit:x")})

    assert evidence.intent_reachable(resolver, _door("x")) is True


def test_intent_reachable_accepts_an_explicit_route() -> None:
    resolver = _fake_resolver({"do the thing": {"kind": "explicit", "candidates": ["x"]}})

    assert evidence.intent_reachable(resolver, _door("x")) is True


def test_intent_reachable_is_true_when_any_one_intent_routes() -> None:
    resolver = _fake_resolver({"second intent": _specialist("project-toolkit:x")})
    door = _door("x", intents=("first intent", "second intent"))

    assert evidence.intent_reachable(resolver, door) is True


def test_intent_reachable_treats_an_ambiguous_result_as_unreachable() -> None:
    resolver = _fake_resolver(
        {"do the thing": {"kind": "ambiguous", "candidates": ["project-toolkit:x"]}}
    )

    assert evidence.intent_reachable(resolver, _door("x")) is False


def test_intent_reachable_is_false_when_another_skill_shares_the_route() -> None:
    resolver = _fake_resolver(
        {"do the thing": _specialist("project-toolkit:x", "project-toolkit:y")}
    )

    assert evidence.intent_reachable(resolver, _door("x")) is False


def test_intent_reachable_is_false_when_the_route_goes_to_another_skill() -> None:
    resolver = _fake_resolver({"do the thing": _specialist("project-toolkit:y")})

    assert evidence.intent_reachable(resolver, _door("x")) is False


def test_intent_reachable_matches_whole_names_not_suffixes() -> None:
    resolver = _fake_resolver({"do the thing": _specialist("project-toolkit:spec-generator")})

    assert evidence.intent_reachable(resolver, _door("generator")) is False


def test_intent_reachable_is_false_without_a_resolver() -> None:
    assert evidence.intent_reachable(None, _door("x")) is False


def test_intent_reachable_is_false_without_a_door() -> None:
    resolver = _fake_resolver({"do the thing": _specialist("project-toolkit:x")})

    assert evidence.intent_reachable(resolver, None) is False


def test_intent_reachable_is_false_for_a_door_with_no_intents() -> None:
    resolver = _fake_resolver({"do the thing": _specialist("project-toolkit:x")})

    assert evidence.intent_reachable(resolver, _door("x", intents=())) is False


# --- phrase_report ----------------------------------------------------------


def test_phrase_report_counts_every_phrase_and_lists_the_misses() -> None:
    resolver = _fake_resolver({"hit": _specialist("project-toolkit:x")})
    door = _door("x", description="Use when you say `hit` or `miss`.")

    report = evidence.phrase_report(resolver, [door])

    assert report.measured is True
    assert report.examined == 2
    assert report.misses == (("x", "miss"),)
    assert report.no_lead == ()
    assert report.without_intents == 0


def test_phrase_report_counts_an_ambiguous_result_as_a_miss() -> None:
    resolver = _fake_resolver(
        {"hit": {"kind": "ambiguous", "candidates": ["project-toolkit:x", "project-toolkit:y"]}}
    )
    door = _door("x", description="Use when you say `hit`.")

    report = evidence.phrase_report(resolver, [door])

    assert report.misses == (("x", "hit"),)


def test_phrase_report_strips_the_namespace_when_comparing_names() -> None:
    resolver = _fake_resolver({"hit": _specialist("other-namespace:x")})
    door = _door("x", description="Use when you say `hit`.")

    report = evidence.phrase_report(resolver, [door])

    assert report.misses == ()
    assert report.examined == 1


def test_phrase_report_excludes_repo_local_doors() -> None:
    resolver = _fake_resolver({})
    local = _door("local-door", shipped=False, description="Use when you say `never routed`.")
    local_without_intents = _door("quiet-local", shipped=False, intents=())

    report = evidence.phrase_report(resolver, [local, local_without_intents])

    assert report.examined == 0
    assert report.misses == ()
    assert report.without_intents == 0


def test_phrase_report_counts_shipped_doors_without_intents_and_skips_them() -> None:
    resolver = _fake_resolver({})
    silent = _door("silent", intents=(), description="Use when you say `never examined`.")

    report = evidence.phrase_report(resolver, [silent])

    assert report.without_intents == 1
    assert report.examined == 0
    assert report.misses == ()


def test_phrase_report_lists_doors_whose_description_has_no_lead_in() -> None:
    resolver = _fake_resolver({})
    door = _door("plain", description="Plans work without a lead-in.")

    report = evidence.phrase_report(resolver, [door])

    assert report.no_lead == ("plain",)
    assert report.examined == 0


def test_phrase_report_orders_misses_by_door_name() -> None:
    resolver = _fake_resolver({})
    doors = [
        _door("zeta", description="Use when you say `z`."),
        _door("alpha", description="Use when you say `a`."),
    ]

    report = evidence.phrase_report(resolver, doors)

    assert report.misses == (("alpha", "a"), ("zeta", "z"))


def test_phrase_report_without_a_resolver_is_not_measured_and_credits_nothing() -> None:
    doors = [
        _door("x", description="Use when you say `hit`."),
        _door("silent", intents=()),
        _door("local", shipped=False),
    ]

    report = evidence.phrase_report(None, doors)

    assert report.measured is False
    assert report.examined == 0
    assert report.misses == ()
    assert report.no_lead == ()
    assert report.without_intents == 1


# --- load_resolver ----------------------------------------------------------


def test_load_resolver_returns_none_when_the_catalog_is_absent(tmp_path: Path) -> None:
    assert evidence.load_resolver(tmp_path) is None


def test_load_resolver_returns_none_when_the_resolver_script_is_absent(tmp_path: Path) -> None:
    (tmp_path / evidence.CATALOG_DIR).mkdir(parents=True)

    assert evidence.load_resolver(tmp_path) is None


def test_load_resolver_loads_the_shipped_resolver_from_the_repository() -> None:
    resolver = evidence.load_resolver(_REPO_ROOT)

    assert resolver is not None
    module, roots = resolver
    assert callable(module.resolve)
    assert roots
