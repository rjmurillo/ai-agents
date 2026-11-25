"""skillforge finds skills in the other Hermes packs installed beside its own.

Hermes installs each Project Toolkit pack as a separate plugin in one folder.
Skillforge ships in the authoring pack, so skill discovery and the trigger-phrase
lint must look in the sibling packs too. A plugin root not named like a pack,
such as the Claude or Copilot tree, gets no sibling roots.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.skills.skillforge.lint_support import _skill_text, lint

_REPO = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO / "src" / "claude" / "skills" / "skillforge" / "scripts"

_ROUTING_PHRASE = 'Demo skill. Use when you say "ship the thing". Do NOT use for other work.'
_ROUTING_META = "  routing:\n    role: front-door\n    intents:\n      - ship the thing\n"
_RESOLVER = (
    "def _tokenize(text):\n    return text.split()\n"
    "def _matches_ordered(request, intent):\n    return request == intent\n"
)


def _load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_packs = _load("skillforge_packs_under_test", "_packs.py")
ds = _load("skillforge_discover_skills_packs", "discover_skills.py")


def _pack(plugins: Path, name: str, skills: tuple[str, ...] = ()) -> Path:
    root = plugins / name
    (root / "skills").mkdir(parents=True)
    (root / "plugin.json").write_text(f'{{"name": "{name}"}}\n', encoding="utf-8")
    for skill in skills:
        (root / "skills" / skill).mkdir()
        (root / "skills" / skill / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: The {skill} skill.\n---\n", encoding="utf-8"
        )
    return root


def _script_in(pack: Path) -> Path:
    return pack / "skills" / "skillforge" / "scripts" / "discover_skills.py"


# sibling_pack_roots


def test_siblings_are_the_other_packs_sorted_by_name(tmp_path: Path) -> None:
    authoring = _pack(tmp_path, "project-toolkit-authoring")
    knowledge = _pack(tmp_path, "project-toolkit-knowledge")
    delivery = _pack(tmp_path, "project-toolkit-delivery")

    assert _packs.sibling_pack_roots(authoring) == [delivery, knowledge]


def test_a_folder_without_skills_manifest_or_prefix_is_not_a_sibling(tmp_path: Path) -> None:
    authoring = _pack(tmp_path, "project-toolkit-authoring")
    (tmp_path / "project-toolkit-empty").mkdir()
    (tmp_path / "project-toolkit-no-manifest" / "skills").mkdir(parents=True)
    _pack(tmp_path, "other-plugin")

    assert _packs.sibling_pack_roots(authoring) == []


def test_a_root_not_named_like_a_pack_has_no_siblings(tmp_path: Path) -> None:
    claude = _pack(tmp_path, "claude")
    _pack(tmp_path, "project-toolkit-knowledge")

    assert _packs.sibling_pack_roots(claude) == []


def test_an_unreadable_plugins_folder_gives_no_siblings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    authoring = _pack(tmp_path, "project-toolkit-authoring")

    def refuse(self: Path) -> Any:
        raise PermissionError(str(self))

    monkeypatch.setattr(Path, "iterdir", refuse)

    assert _packs.sibling_pack_roots(authoring) == []


# discover_skills


def test_discovery_lists_the_sibling_packs_skills_roots(tmp_path: Path) -> None:
    authoring = _pack(tmp_path, "project-toolkit-authoring", ("skillforge",))
    knowledge = _pack(tmp_path, "project-toolkit-knowledge", ("memory",))

    roots = ds._runtime_roots(None, {}, _script_in(authoring))

    assert ("pack-project-toolkit-knowledge", knowledge / "skills") in roots
    names = [name for name, _ in roots]
    assert names.index("plugin-local") < names.index("pack-project-toolkit-knowledge")


def test_discovery_in_a_claude_tree_adds_no_pack_roots(tmp_path: Path) -> None:
    claude = _pack(tmp_path, "claude", ("skillforge",))
    _pack(tmp_path, "project-toolkit-knowledge", ("memory",))

    roots = ds._runtime_roots(None, {}, _script_in(claude))

    assert not [name for name, _ in roots if name.startswith("pack-")]


# trigger-phrase lint resolver


def _routing_status(
    monkeypatch: pytest.MonkeyPatch, plugin_root: Path, beside: Path, description: str
) -> str:
    rule = next(r for r in lint.RULES if r.id == "fm.routing.phrases-routable")
    namespace = rule.check.__globals__
    monkeypatch.setitem(namespace, "_RESOLVER_PATH", beside)
    monkeypatch.setitem(namespace, "_PLUGIN_ROOT", plugin_root)
    monkeypatch.setitem(namespace, "_resolver_cache", [])
    text = _skill_text(_ROUTING_META, description=description)
    return {r.rule.id: r.status for r in lint.lint_text(text)}["fm.routing.phrases-routable"]


def _authoring_with_knowledge_resolver(tmp_path: Path) -> tuple[Path, Path]:
    authoring = _pack(tmp_path, "project-toolkit-authoring", ("skillforge",))
    knowledge = _pack(tmp_path, "project-toolkit-knowledge")
    resolver = knowledge / "skills" / "autoplan" / "scripts" / "resolve_route.py"
    resolver.parent.mkdir(parents=True)
    resolver.write_text(_RESOLVER, encoding="utf-8")
    beside = authoring / "skills" / "autoplan" / "scripts" / "resolve_route.py"
    return authoring, beside


def test_the_lint_loads_autoplan_from_a_sibling_pack(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    authoring, beside = _authoring_with_knowledge_resolver(tmp_path)

    assert _routing_status(monkeypatch, authoring, beside, _ROUTING_PHRASE) == "PASS"


def test_a_sibling_resolver_still_flags_a_phrase_that_matches_no_intent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    authoring, beside = _authoring_with_knowledge_resolver(tmp_path)
    phrase = 'Demo skill. Use when you say "find the thing". Do NOT use for other work.'

    assert _routing_status(monkeypatch, authoring, beside, phrase) not in ("PASS", "NOT_EVALUATED")


def test_with_no_resolver_anywhere_the_rule_is_not_evaluated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    authoring = _pack(tmp_path, "project-toolkit-authoring", ("skillforge",))
    _pack(tmp_path, "project-toolkit-knowledge")
    beside = authoring / "skills" / "autoplan" / "scripts" / "resolve_route.py"

    assert _routing_status(monkeypatch, authoring, beside, _ROUTING_PHRASE) == "NOT_EVALUATED"
