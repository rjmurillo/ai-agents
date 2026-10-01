"""Tests for the natural-language structural debt ratchet (issue #5397).

Fixtures build trees in `tmp_path`. Each negative case asserts the exit code and
the message, so a test cannot pass for the wrong reason.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION) not in sys.path:
    sys.path.insert(0, str(_VALIDATION))

import check_nl_structural_debt as gate
import nl_cardinality as card

_POLICY = "\n".join(
    f"Every reviewer must confirm that policy line number {n} holds before merging."
    for n in range(6)
)


def _tree(root: Path) -> None:
    for subdir in ("templates/skills", "templates/agents", "templates/rules"):
        (root / subdir).mkdir(parents=True, exist_ok=True)


def _write(root: Path, rel: str, body: str, frontmatter: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: x\n{frontmatter}---\n{body}\n", encoding="utf-8")


def _baseline(root: Path, dup: dict | None = None, count: dict | None = None) -> None:
    path = root / gate.BASELINE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"duplicate_blocks": dup or {}, "cardinality": count or {}}))


def _cap(owns: str, depends: str | None = None) -> str:
    """Render a capability block that owns one name and optionally depends on one."""
    lines = ["metadata:", "  capability:", "    kind: reusable-primitive", f"    owns: [{owns}]"]
    if depends:
        lines.append(f"    depends-on: [{depends}]")
    return "\n".join([*lines, "    status: active", ""])


def _graph_fillers(root: Path) -> None:
    """The capability graph refuses trees with no skill or agent template."""
    _write(root, "templates/skills/filler.SKILL.md.tmpl", "Filler skill body line.")
    _write(root, "templates/agents/filler.md", "Filler agent body line.")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _tree(tmp_path)
    _write(tmp_path, "templates/rules/a.md", "Alpha intro.\n" + _POLICY)
    _baseline(tmp_path)
    return tmp_path


def test_clean_tree_passes(repo: Path) -> None:
    assert gate.run(repo, update=False) == 0


def test_simplify_removes_only_the_flagged_number_and_ignores_non_claims() -> None:
    assert card.simplify("In 2 steps, run the three filters: a, b, c, d.") == (
        "In 2 steps, run the filters: a, b, c, d."
    )
    assert card.simplify("No claim here.") == "No claim here."


def test_three_filters_is_flagged_and_simplified() -> None:
    claims = card.derived_count_claims("Run the three filters: lint, format, types, tests.")
    assert [(c.stated, c.actual) for c in claims] == [(3, 4)]
    assert card.simplify(claims[0].text) == "Run the filters: lint, format, types, tests."


def test_bulleted_enumeration_contradicting_count_is_flagged() -> None:
    text = "Run the three filters:\n\n- a\n- b\n- c\n- d\n"
    assert [(c.stated, c.actual) for c in card.derived_count_claims(text)] == [(3, 4)]


@pytest.mark.parametrize(
    "line",
    [
        "Run exactly three filters: lint, format, types, tests.",
        "Keep at least two gates: build, test, lint.",
        "Run the three filters: lint, format, types.",
        "Run the three filters.",
        "| 4 | Gate | a, b, c |",
        "Spend 10-15 minutes: read, write, test.",
    ],
)
def test_contractual_matching_or_unproven_counts_are_retained(line: str) -> None:
    assert card.derived_count_claims(line) == []


def test_fenced_code_is_ignored() -> None:
    assert card.derived_count_claims("```\nthe three filters: a, b, c, d\n```") == []


def test_stale_count_fails_with_simplification(repo: Path) -> None:
    _write(repo, "templates/rules/b.md", "Run the three filters: lint, format, types, tests.")
    assert gate.run(repo, update=False) == 1


def test_stale_count_message_names_the_fix(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, "templates/rules/b.md", "Run the three filters: lint, format, types, tests.")
    gate.run(repo, update=False)
    err = capsys.readouterr().err
    assert "Run the filters: lint, format, types, tests." in err
    assert "Do not resync copies" in err


def test_duplicate_authored_block_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(repo, "templates/rules/b.md", "Beta intro.\n" + _POLICY)
    assert gate.run(repo, update=False) == 1
    assert "templates/rules/a.md|templates/rules/b.md" in capsys.readouterr().err


def test_short_overlap_is_not_a_block(repo: Path) -> None:
    _write(repo, "templates/rules/b.md", "\n".join(_POLICY.splitlines()[:4]))
    assert gate.run(repo, update=False) == 0


def test_generated_projection_is_not_independent_duplication(repo: Path) -> None:
    for mirror in (
        ".claude/rules/a.md",
        "src/claude/rules/a.md",
        ".github/instructions/a.instructions.md",
    ):
        _write(repo, mirror, "Alpha intro.\n" + _POLICY)
    assert gate.run(repo, update=False) == 0
    assert gate.measure(repo)["duplicate_blocks"] == {}


def test_projection_exclusion_is_load_bearing(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation: scanning the mirror as authored turns a clean tree red."""
    _write(repo, ".claude/rules/a.md", "Alpha intro.\n" + _POLICY)
    real = gate.authored_files
    monkeypatch.setattr(
        gate, "authored_files", lambda root: [*real(root), root / ".claude/rules/a.md"]
    )
    assert gate.run(repo, update=False) == 1


def test_baseline_is_load_bearing(repo: Path) -> None:
    """Mutation: the same defect passes with a baseline entry and fails without it."""
    _write(repo, "templates/rules/b.md", "Beta intro.\n" + _POLICY)
    pair = "templates/rules/a.md|templates/rules/b.md"
    _baseline(repo, dup={pair: gate.measure(repo)["duplicate_blocks"][pair]})
    assert gate.run(repo, update=False) == 0
    _baseline(repo)
    assert gate.run(repo, update=False) == 1


def test_grown_overlap_exceeds_baseline(repo: Path) -> None:
    _write(repo, "templates/rules/b.md", "Beta intro.\n" + _POLICY)
    pair = "templates/rules/a.md|templates/rules/b.md"
    _baseline(repo, dup={pair: 1})
    assert gate.run(repo, update=False) == 1


def test_shrunk_debt_demands_baseline_update(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _baseline(repo, dup={"templates/rules/a.md|templates/rules/gone.md": 2})
    assert gate.run(repo, update=False) == 1
    assert "--update-baseline" in capsys.readouterr().err
    assert gate.run(repo, update=True) == 0
    assert json.loads((repo / gate.BASELINE_PATH).read_text())["duplicate_blocks"] == {}
    assert gate.run(repo, update=False) == 0


def test_update_baseline_refuses_growth(repo: Path) -> None:
    _write(repo, "templates/rules/b.md", "Beta intro.\n" + _POLICY)
    assert gate.run(repo, update=True) == 1
    assert json.loads((repo / gate.BASELINE_PATH).read_text())["duplicate_blocks"] == {}


def test_update_baseline_creates_a_missing_baseline(repo: Path) -> None:
    (repo / gate.BASELINE_PATH).unlink()
    assert gate.run(repo, update=True) == 0
    assert (repo / gate.BASELINE_PATH).is_file()


def test_empty_scan_is_a_config_error(tmp_path: Path) -> None:
    _tree(tmp_path)
    _baseline(tmp_path)
    assert gate.run(tmp_path, update=False) == 2


def test_missing_baseline_is_a_config_error(repo: Path) -> None:
    (repo / gate.BASELINE_PATH).unlink()
    assert gate.run(repo, update=False) == 2


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '{"duplicate_blocks": {}}',
        '{"duplicate_blocks": [], "cardinality": {}}',
        '{"duplicate_blocks": {"a|b": "x"}, "cardinality": {}}',
        '{"duplicate_blocks": {"a|b": true}, "cardinality": {}}',
        '{"duplicate_blocks": {"a|b": 0}, "cardinality": {}}',
        '{"duplicate_blocks": {}, "cardinality": {"k": 3}}',
    ],
)
def test_invalid_baseline_is_a_config_error(repo: Path, content: str) -> None:
    (repo / gate.BASELINE_PATH).write_text(content)
    assert gate.run(repo, update=False) == 2


def test_normal_run_prints_examined_and_violation_counts(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.run(repo, update=False) == 0
    assert "0 increases, 1 authored artifacts examined" in capsys.readouterr().out


def test_report_json_carries_examined_count(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _graph_fillers(repo)
    _write(repo, "templates/rules/owner.md", "Owner.", frontmatter=_cap("policy-x"))
    assert gate.run(repo, update=False, report=True) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["examined"] == len(gate.authored_files(repo))
    assert {"duplicate_blocks", "cardinality", "amplification"} <= set(out)


def test_tilde_fenced_example_is_not_a_live_claim() -> None:
    text = "~~~\nRun the three filters: a, b, c, d.\n~~~\n"
    assert card.derived_count_claims(text) == []
    assert len(card.derived_count_claims("Run the three filters: a, b, c, d.")) == 1


def test_threshold_pins_four_shared_lines_and_short_lines_are_not_duplicates() -> None:
    four = "\n".join(
        f"Every reviewer must confirm that policy line number {n} holds." for n in range(4)
    )
    short = "\n".join(f"Run step {n} now." for n in range(8))
    files = {"a.md": four + "\n" + short, "b.md": four + "\n" + short}
    assert gate.duplicate_blocks(files) == {}
    five = "\n".join(
        f"Every reviewer must confirm that policy line number {n} holds." for n in range(5)
    )
    assert gate.duplicate_blocks({"a.md": five, "b.md": five}) == {"a.md|b.md": 1}


def test_missing_canonical_tree_is_a_config_error(tmp_path: Path) -> None:
    _baseline(tmp_path)
    assert gate.run(tmp_path, update=False) == 2


def test_cli_rejects_invalid_root(tmp_path: Path) -> None:
    assert gate.main([str(tmp_path / "missing")]) == 2


def test_validate_entry_point_matches_pre_pr_contract(repo: Path) -> None:
    assert gate.validate_nl_structural_debt(repo) is True
    _write(repo, "templates/rules/b.md", "Run the three filters: a, b, c, d.")
    assert gate.validate_nl_structural_debt(repo) is False


def test_skill_references_are_authored_and_untemplated_skills_count(repo: Path) -> None:
    _write(repo, ".claude/skills/solo/SKILL.md", "Solo skill.\n" + _POLICY)
    _write(repo, ".claude/skills/solo/references/r.md", "Reference.\n" + _POLICY)
    paths = {p.relative_to(repo).as_posix() for p in gate.authored_files(repo)}
    assert ".claude/skills/solo/SKILL.md" in paths
    assert ".claude/skills/solo/references/r.md" in paths
    pairs = gate.measure(repo)["duplicate_blocks"]
    assert any(".claude/skills/solo/references/r.md" in key for key in pairs)
    assert any(".claude/skills/solo/SKILL.md" in key for key in pairs)


def test_partials_and_hand_maintained_prompts_are_authored(repo: Path) -> None:
    _write(repo, "templates/agents/partials/p.mustache", "Partial.\n" + _POLICY)
    _write(repo, "templates/skills/partials/q.mustache", "Partial.\n" + _POLICY)
    _write(repo, ".github/prompts/hand.md", "Prompt.\n" + _POLICY)
    _write(repo, ".github/prompts/pr-quality-gate-x.md", "Generated.\n" + _POLICY)
    paths = {p.relative_to(repo).as_posix() for p in gate.authored_files(repo)}
    assert {
        "templates/agents/partials/p.mustache",
        "templates/skills/partials/q.mustache",
        ".github/prompts/hand.md",
    } <= paths
    assert ".github/prompts/pr-quality-gate-x.md" not in paths
    pairs = gate.measure(repo)["duplicate_blocks"]
    assert any("templates/agents/partials/p.mustache" in key for key in pairs)
    assert any(".github/prompts/hand.md" in key for key in pairs)


def test_templated_skill_projection_is_not_authored(repo: Path) -> None:
    _write(repo, "templates/skills/tpl.SKILL.md.tmpl", "Template.\n" + _POLICY)
    _write(repo, ".claude/skills/tpl/SKILL.md", "Template.\n" + _POLICY)
    paths = {p.relative_to(repo).as_posix() for p in gate.authored_files(repo)}
    assert ".claude/skills/tpl/SKILL.md" not in paths
    assert "templates/skills/tpl.SKILL.md.tmpl" in paths


def test_byte_corpus_authored_sources_are_scanned(repo: Path) -> None:
    for rel in (
        "templates/agents/x.claude.md.tmpl",
        "templates/agents/x.copilot.md.tmpl",
        ".agents/governance/g.md",
        "AGENTS.md",
        "CLAUDE.md",
    ):
        _write(repo, rel, "Authored.\n" + _POLICY)
    _write(repo, ".claude/rules/projection.md", "Projection.\n" + _POLICY)
    paths = {p.relative_to(repo).as_posix() for p in gate.authored_files(repo)}
    assert {
        "templates/agents/x.claude.md.tmpl",
        "templates/agents/x.copilot.md.tmpl",
        ".agents/governance/g.md",
        "AGENTS.md",
        "CLAUDE.md",
    } <= paths
    assert ".claude/rules/projection.md" not in paths


def test_scan_set_is_the_corpus_classification_plus_documented_extras() -> None:
    from scripts.validation.instruction_bytes_corpus import canonical_paths

    scanned = {p.relative_to(_REPO_ROOT).as_posix() for p in gate.authored_files(_REPO_ROOT)}
    corpus = {r for r in canonical_paths(_REPO_ROOT) if r.endswith(gate.NL_SUFFIXES)}
    assert corpus <= scanned
    assert "AGENTS.md" in scanned


@pytest.mark.parametrize(
    "setup",
    ["missing_dependency", "duplicate_owner", "cycle"],
)
def test_report_refuses_an_invalid_capability_graph(
    repo: Path, capsys: pytest.CaptureFixture[str], setup: str
) -> None:
    _graph_fillers(repo)
    if setup == "missing_dependency":
        _write(repo, "templates/rules/a1.md", "A.", frontmatter=_cap("pa", "ghost"))
    elif setup == "duplicate_owner":
        _write(repo, "templates/rules/a1.md", "A.", frontmatter=_cap("pa"))
        _write(repo, "templates/rules/a2.md", "B.", frontmatter=_cap("pa"))
    else:
        _write(repo, "templates/rules/a1.md", "A.", frontmatter=_cap("pa", "pb"))
        _write(repo, "templates/rules/a2.md", "B.", frontmatter=_cap("pb", "pa"))
    _baseline(repo, dup=gate.measure(repo)["duplicate_blocks"])
    assert gate.run(repo, update=False, report=True) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "capability graph has" in captured.err


def test_report_lists_amplification_per_owner(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _graph_fillers(repo)
    cap = _cap("policy-x")
    _write(repo, "templates/rules/owner.md", "Owner.\n" + _POLICY, frontmatter=cap)
    dep = _cap("policy-y", "policy-x")
    _write(repo, "templates/rules/user.md", "User.", frontmatter=dep)
    _baseline(repo, dup=gate.measure(repo)["duplicate_blocks"])
    assert gate.run(repo, update=False, report=True) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["amplification"]["policy-x"] == {"amplification": 2, "dependents": 1}
    assert out["amplification"]["policy-y"] == {"amplification": 1, "dependents": 0}


def test_copied_dependency_owned_policy_is_detected_by_the_capability_gate(repo: Path) -> None:
    import check_capability_graph as graph

    _graph_fillers(repo)
    cap = _cap("policy-x")
    _write(repo, "templates/rules/owner.md", "Owner.\n" + _POLICY, frontmatter=cap)
    dep = _cap("policy-y", "policy-x")
    _write(repo, "templates/rules/user.md", "User.\n" + _POLICY, frontmatter=dep)
    findings = graph.survey(repo)[2]
    assert any("repeats a block of `policy-x`" in f for f in findings)
    assert gate.run(repo, update=False) == 1


def test_real_tree_matches_its_baseline() -> None:
    assert gate.run(_REPO_ROOT, update=False) == 0
