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

import pytest

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
) -> evidence.FrontDoor:
    return evidence.FrontDoor(name, intents)


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


def test_a_resolver_that_raises_propagates_out_of_intents_reached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = _template(tmp_path, "name: a\nmetadata:\n  routing:\n    intents: [run a]")

    def resolve(request: str, roots: list[object]) -> dict[str, object]:
        raise RuntimeError("resolver broke")

    monkeypatch.setattr(
        evidence, "load_resolver", lambda repo_root: (SimpleNamespace(resolve=resolve), [])
    )

    with pytest.raises(RuntimeError, match="resolver broke"):
        evidence.intents_reached(tmp_path, {"a": template})


# --- read_front_door ---------------------------------------------------------


def _template(tmp_path: Path, frontmatter: str) -> Path:
    path = tmp_path / "x.SKILL.md.tmpl"
    path.write_text(f"---\n{frontmatter}\n---\n\n# X\n", encoding="utf-8")
    return path


def test_read_front_door_reads_string_intents_only(tmp_path: Path) -> None:
    template = _template(
        tmp_path,
        "name: x\nmetadata:\n  routing:\n    intents:\n      - do the thing\n      - 7\n",
    )

    door = evidence.read_front_door("x", template)

    assert door == evidence.FrontDoor("x", ("do the thing",))


def test_read_front_door_defaults_a_bare_skill_to_no_intents(tmp_path: Path) -> None:
    door = evidence.read_front_door("x", _template(tmp_path, "name: x"))

    assert door == evidence.FrontDoor("x", ())


def test_read_front_door_returns_none_for_unparseable_frontmatter(tmp_path: Path) -> None:
    assert evidence.read_front_door("x", _template(tmp_path, "name: [unclosed")) is None


# --- intents_reached ---------------------------------------------------------


def test_intents_reached_skips_loading_the_resolver_with_no_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(repo_root: Path) -> None:
        raise AssertionError("resolver loaded with nothing to check")

    monkeypatch.setattr(evidence, "load_resolver", fail)

    assert evidence.intents_reached(tmp_path, {}) == set()


def test_intents_reached_credits_only_skills_whose_intent_routes_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reached_path = _template(tmp_path, "name: a\nmetadata:\n  routing:\n    intents: [run a]")
    shadowed = tmp_path / "b.SKILL.md.tmpl"
    shadowed.write_text(
        "---\nname: b\nmetadata:\n  routing:\n    intents: [run b]\n---\n", encoding="utf-8"
    )
    routes = {
        "run a": _specialist("project-toolkit:a"),
        "run b": _specialist("project-toolkit:b", "project-toolkit:c"),
    }
    monkeypatch.setattr(evidence, "load_resolver", lambda repo_root: _fake_resolver(routes))

    reached = evidence.intents_reached(tmp_path, {"a": reached_path, "b": shadowed})

    assert reached == {"a"}
