"""Scenario S2 caps a component import, never a correct rejection.

S2 asks for an analyzer rule page outline on a plain Markdown repository. Per
the owner's decision, its forbidden patterns match only an import statement
that pulls an Astro or Starlight component module. Prose that names a
component or package, including to reject it, is left to the judge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval.test_eval_rule_activation import eval_mod

SCENARIOS = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "evals"
    / "skill-scenarios"
    / "technical-writing.json"
)


@pytest.fixture
def s2() -> dict[str, Any]:
    data = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    return next(s for s in data["scenarios"] if s["id"] == "S2")


@pytest.mark.parametrize(
    "response",
    [
        "Don't import @astrojs/starlight components.",
        "Avoid any import of @astrojs/starlight components.",
        "No import from @components/ belongs on a plain Markdown page.",
        "Do not import { Aside } from '@astrojs/starlight/components'.",
        "Never import X from '@components/Foo.astro'.",
        "Use GitHub alerts instead of <Aside> from '@astrojs/starlight/components'.",
        "This repo does not use MDX, so imports from '@astrojs/starlight' will not render.",
        "Don't use <Aside>.",
        "- <Aside> is Starlight-only; use a blockquote.",
        'Use a blockquote instead of <Aside type="tip">.',
    ],
)
def test_correct_rejection_is_not_capped(s2: dict[str, Any], response: str) -> None:
    assert eval_mod._forbidden_claim_hits(s2, response) == []


@pytest.mark.parametrize(
    "response",
    [
        "import { Aside } from '@astrojs/starlight/components';",
        'import { Tabs, TabItem } from "@astrojs/starlight/components";',
        "import {\n  Tabs,\n  TabItem,\n} from '@astrojs/starlight/components';",
        "import OsAwareTabs from '@components/OsAwareTabs.astro';",
        "Add this line: `import { Aside } from '@astrojs/starlight/components';`",
    ],
)
def test_component_import_is_capped(s2: dict[str, Any], response: str) -> None:
    assert eval_mod._forbidden_claim_hits(s2, response)
