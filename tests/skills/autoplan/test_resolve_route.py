#!/usr/bin/env python3
"""Tests for the autoplan long-tail resolver (REQ-039, DESIGN-037).

Every fixture-table row from issue #5385 gets a positive test against the
REAL rendered `.claude/skills` catalog (not a synthetic stand-in), so a
change to a skill's `description` or `intents` that breaks reachability
fails here, not only in `check_skill_routing_roles.py --report`'s
unresolved list. Synthetic `tmp_path` catalogs cover shapes the real
catalog cannot exercise on demand: a scoring tie, a non-front-door skill
carrying `intents` (a defect the routing-role gate refuses, but the
resolver must independently never select it), a `deprecated` skill, and
the mixed-catalog identity contract against a foreign `gstack:autoplan`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if _TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

REPO_ROOT = Path(__file__).resolve().parents[3]
RESOLVER_SCRIPT = REPO_ROOT / ".claude" / "skills" / "autoplan" / "scripts" / "resolve_route.py"
REAL_SKILLS_ROOT = REPO_ROOT / ".claude" / "skills"

resolver = import_skill_script(".claude/skills/autoplan/scripts/resolve_route.py")


def _real_roots() -> list[object]:
    """The real, rendered `.claude/skills` catalog as the resolver's home root."""
    namespace = resolver._default_namespace(REAL_SKILLS_ROOT)
    return [resolver.Root(path=REAL_SKILLS_ROOT, namespace=namespace)]


REAL_NAMESPACE = resolver._default_namespace(REAL_SKILLS_ROOT)


def _write_skill(
    root: Path,
    dirname: str,
    *,
    frontmatter_name: str | None = None,
    role: str | None = "front-door",
    intents: list[str] | None = None,
    no_routing: bool = False,
) -> Path:
    """Write a minimal `SKILL.md` under `root/dirname` for a synthetic catalog.

    `no_routing` omits `metadata.routing` entirely, modeling a foreign skill
    (such as gstack's own `autoplan`) that carries no DESIGN-036/037
    declaration at all.
    """
    skill_dir = root / dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {frontmatter_name or dirname}"]
    if not no_routing:
        lines += [
            "metadata:",
            "  routing:",
            f"    role: {role}",
            "    invoker: autoplan",
            "    trigger: t",
            "    user-facing: true",
        ]
        if intents is not None:
            lines.append("    intents:")
            lines.extend(f"      - {intent}" for intent in intents)
    lines += ["---", "", "Body."]
    (skill_dir / "SKILL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return skill_dir


# ---------------------------------------------------------------------------
# Issue #5385 fixture table: positive rows against the REAL rendered catalog
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("request_text", "expected_skill"),
    [
        ("Evaluate our business model against a new competitive strategy.", "business-strategy"),
        ("Turn the book Deep Work into a reusable skill.", "book-to-skill"),
        (
            "Diagnose why the agent's assumptions about the world model keep failing.",
            "world-model-diagnostic",
        ),
        ("Audit our CLI onboarding workflow for developer friction.", "dx-review"),
        (
            "Is there an existing library for parsing YAML before we build one?",
            "programming-advisor",
        ),
        (
            "Compare build vs buy vs partner vs defer with total cost of ownership.",
            "buy-vs-build-framework",
        ),
        (
            "Is there already a library or SaaS that parses cron expressions?",
            "programming-advisor",
        ),
        (
            "Does an internal component already solve rate limiting for us?",
            "programming-advisor",
        ),
        ("Should we build or partner for search? Give me the TCO.", "buy-vs-build-framework"),
        ("Make or buy decision for our identity provider.", "buy-vs-build-framework"),
    ],
)
def test_fixture_table_positive_rows_resolve_against_real_catalog(
    request_text: str, expected_skill: str
) -> None:
    result = resolver.resolve(request_text, _real_roots())
    assert result["kind"] == "specialist"
    assert result["route"] == f"{REAL_NAMESPACE}:{expected_skill}"
    assert result["candidates"] == [f"{REAL_NAMESPACE}:{expected_skill}"]


def test_multi_domain_migration_routes_to_orchestrator() -> None:
    result = resolver.resolve(
        "Migrate the billing service across teams in parallel with the notifications team.",
        _real_roots(),
    )
    assert result["kind"] == "orchestrator"
    assert result["route"] == "orchestrator"


def test_explicit_named_skill_bypasses_intent_rerouting() -> None:
    """AC7: an explicit name wins even when the rest of the text matches another skill's intents."""
    result = resolver.resolve(
        "/dx-review please, is there an existing library for parsing YAML",
        _real_roots(),
    )
    assert result["kind"] == "explicit"
    assert result["route"] == f"{REAL_NAMESPACE}:dx-review"


def test_unknown_or_unsafe_request_returns_none_never_a_fabricated_name() -> None:
    result = resolver.resolve("Do something dangerous and unclear.", _real_roots())
    assert result["kind"] == "none"
    assert result["route"] is None
    assert result["candidates"] == []


def test_explicit_unknown_skill_reference_is_never_returned() -> None:
    result = resolver.resolve("/frobnicate this please", _real_roots())
    assert result["kind"] != "explicit"
    assert result["route"] != "frobnicate"
    assert all("frobnicate" not in candidate for candidate in result["candidates"])
    assert "frobnicate" in result["rationale"]


def test_new_capability_generic_phrase_has_no_specialist_and_falls_through() -> None:
    """A bare 'new capability' phrase names no library, so the resolver defers
    to the lifecycle chain (kind `none`), not a fabricated specialist match."""
    result = resolver.resolve("Add a new caching module to the service.", _real_roots())
    assert result["kind"] == "none"


def test_autoplan_skill_md_composes_programming_advisor_before_spec() -> None:
    """The New capability row runs programming-advisor before buy-vs-build-framework."""
    text = (REAL_SKILLS_ROOT / "autoplan" / "SKILL.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| New capability"))
    assert "programming-advisor" in row
    assert "buy-vs-build-framework" in row
    assert row.index("programming-advisor") < row.index("buy-vs-build-framework")
    assert row.index("programming-advisor") < row.index("/spec")


# ---------------------------------------------------------------------------
# programming-advisor vs buy-vs-build-framework: non-overlapping negative pairs
# ---------------------------------------------------------------------------


def test_programming_advisor_positive_never_matches_buy_vs_build() -> None:
    result = resolver.resolve(
        "Is there an existing library for parsing YAML before we build one?", _real_roots()
    )
    assert result["route"] != f"{REAL_NAMESPACE}:buy-vs-build-framework"


def test_buy_vs_build_positive_never_matches_programming_advisor() -> None:
    result = resolver.resolve(
        "Compare build vs buy vs partner vs defer with total cost of ownership.", _real_roots()
    )
    assert result["route"] != f"{REAL_NAMESPACE}:programming-advisor"


# ---------------------------------------------------------------------------
# Synthetic catalogs: shapes the real catalog cannot exercise on demand
# ---------------------------------------------------------------------------


def test_tied_specialists_return_ambiguous(tmp_path: Path) -> None:
    _write_skill(tmp_path, "alpha", intents=["alpha widget"])
    _write_skill(tmp_path, "beta", intents=["beta widget"])
    roots = [resolver.Root(path=tmp_path, namespace="ns")]

    result = resolver.resolve("configure the alpha widget and the beta widget", roots)

    assert result["kind"] == "ambiguous"
    assert result["route"] is None
    assert result["candidates"] == ["ns:alpha", "ns:beta"]


def test_non_front_door_skill_with_intents_is_never_returned(tmp_path: Path) -> None:
    """The routing-role gate refuses this shape upstream; the resolver must
    independently never select it, so a gate regression cannot silently
    reroute traffic to a non-front-door skill."""
    _write_skill(tmp_path, "helper", role="nested-helper", intents=["special sauce"])
    roots = [resolver.Root(path=tmp_path, namespace="ns")]

    result = resolver.resolve("give me the special sauce", roots)

    assert result["kind"] == "none"
    assert result["route"] is None


def test_deprecated_skill_with_intents_is_excluded(tmp_path: Path) -> None:
    _write_skill(tmp_path, "old", role="deprecated", intents=["gone away"])
    roots = [resolver.Root(path=tmp_path, namespace="ns")]

    result = resolver.resolve("the gone away thing", roots)

    assert result["kind"] == "none"
    assert result["route"] is None


def test_router_is_never_returned_and_resolution_continues(tmp_path: Path) -> None:
    """REQ-039 criterion 9: a request naming the router drops the self-reference
    and keeps resolving the rest of the text."""
    _write_skill(tmp_path, "autoplan", role="front-door", intents=None)
    _write_skill(tmp_path, "dx-helper", intents=["dx review"])
    roots = [resolver.Root(path=tmp_path, namespace="ns")]

    result = resolver.resolve("/autoplan dx review my CLI", roots)

    assert result["route"] != "ns:autoplan"
    assert result["kind"] == "specialist"
    assert result["route"] == "ns:dx-helper"
    assert "dropped self-reference" in result["rationale"]


def test_router_alone_in_request_resolves_to_none(tmp_path: Path) -> None:
    _write_skill(tmp_path, "autoplan", intents=None)
    roots = [resolver.Root(path=tmp_path, namespace="ns")]

    result = resolver.resolve("/autoplan", roots)

    assert result["kind"] == "none"
    assert result["route"] is None


def test_missing_skills_root_via_resolve_route_cli_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "does-not-exist"
    exit_code = resolver.main(["--request", "anything", "--skills-root", str(missing)])

    assert exit_code == 2
    assert str(missing) in capsys.readouterr().err


def test_missing_request_argument_exits_2_via_argparse() -> None:
    with pytest.raises(SystemExit) as excinfo:
        resolver.main([])
    assert excinfo.value.code == 2


def test_missing_yaml_module_exits_2_and_names_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(resolver, "yaml", None)
    exit_code = resolver.main(["--request", "anything"])

    assert exit_code == 2
    assert "yaml" in capsys.readouterr().err.lower()


def test_valid_cli_run_exits_0_and_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = resolver.main(
        ["--request", "audit our CLI onboarding workflow for developer friction"]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "specialist"


def test_resolve_is_deterministic_across_repeated_calls() -> None:
    request_text = "Audit our CLI onboarding workflow for developer friction."
    first = resolver.resolve(request_text, _real_roots())
    second = resolver.resolve(request_text, _real_roots())

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_resolve_route_cli_is_byte_identical_across_two_processes() -> None:
    """REQ-039 criterion 3: same request and catalog give byte-identical JSON."""
    args = [
        sys.executable,
        str(RESOLVER_SCRIPT),
        "--request",
        "Audit our CLI onboarding workflow for developer friction.",
    ]
    first = subprocess.run(args, capture_output=True, check=True, text=True)
    second = subprocess.run(args, capture_output=True, check=True, text=True)

    assert first.stdout == second.stdout
    assert first.returncode == second.returncode == 0


# ---------------------------------------------------------------------------
# Mixed catalog: this router's identity vs. a foreign gstack `autoplan`
# ---------------------------------------------------------------------------


def _mixed_catalog_roots(tmp_path: Path) -> list[object]:
    project_toolkit_root = tmp_path / "project-toolkit-skills"
    gstack_root = tmp_path / "gstack-skills"
    _write_skill(project_toolkit_root, "autoplan", role="front-door", intents=None)
    _write_skill(project_toolkit_root, "dx-helper", intents=["dx review"])
    # gstack's own `autoplan` carries no DESIGN-036/037 routing declaration at
    # all, matching DESIGN-037's Identity section: "A foreign autoplan has no
    # intents, so intent matching can never select it."
    _write_skill(gstack_root, "autoplan", no_routing=True)
    return [
        resolver.Root(path=project_toolkit_root, namespace="project-toolkit"),
        resolver.Root(path=gstack_root, namespace="gstack"),
    ]


def test_mixed_catalog_routing_request_never_selects_gstack_autoplan(tmp_path: Path) -> None:
    roots = _mixed_catalog_roots(tmp_path)

    result = resolver.resolve("please dx review my onboarding CLI", roots)

    assert result["route"] != "gstack:autoplan"
    assert "gstack:autoplan" not in result["candidates"]


def test_mixed_catalog_qualified_gstack_reference_selects_it_explicitly(tmp_path: Path) -> None:
    roots = _mixed_catalog_roots(tmp_path)

    result = resolver.resolve("/gstack:autoplan", roots)

    assert result["kind"] == "explicit"
    assert result["route"] == "gstack:autoplan"


def test_mixed_catalog_bare_autoplan_never_returns_the_router(tmp_path: Path) -> None:
    roots = _mixed_catalog_roots(tmp_path)

    result = resolver.resolve("/autoplan", roots)

    assert result["route"] != "project-toolkit:autoplan"
    assert result["route"] != "gstack:autoplan"
    assert result["kind"] == "none"


# ---------------------------------------------------------------------------
# Recursion regression: the orchestrator never invokes autoplan
# ---------------------------------------------------------------------------


def test_orchestrator_shared_source_never_invokes_autoplan() -> None:
    text = (REPO_ROOT / "templates" / "agents" / "orchestrator.shared.md").read_text(
        encoding="utf-8"
    )
    assert not any(
        marker in text for marker in ('Skill(skill="autoplan"', "Skill(skill='autoplan'")
    )
    assert "You never invoke `autoplan`" in text
