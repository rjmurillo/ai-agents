"""skillopt apply refuses a candidate that adds a frontmatter lint MUST failure.

The lint is skillforge's lint_skill_frontmatter.py, loaded from the same plugin.
An optimizer may keep a failure the incumbent already had; it may not add one.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import _skillopt_lint
import pytest
import skillopt
from skillopt_helpers import Capture, valid_eval, write_json

_INCUMBENT = (
    "---\n"
    "name: demo\n"
    "description: Demo skill. Do NOT use for other work (use other-skill).\n"
    "metadata:\n"
    "  routing:\n"
    "    role: front-door\n"
    "---\n"
    "\n"
    "# Demo\n"
)


def _apply(tmp_path: Path, skill_text: str, patches: object, *extra: str) -> int:
    skill = tmp_path / "SKILL.md"
    skill.write_text(skill_text, encoding="utf-8")
    argv = [
        "apply",
        "--eval",
        str(valid_eval(tmp_path)),
        "--skill",
        str(skill),
        "--patches",
        str(write_json(tmp_path / "patches.json", patches)),
        "--budget",
        "2",
        *extra,
    ]
    return skillopt.main(argv)


def test_apply_refuses_a_candidate_that_adds_a_flow_mapping(
    tmp_path: Path, capsys: Capture
) -> None:
    patches = [{"op": "insert_after", "anchor": "metadata:", "text": "  capability: {kind: x}"}]

    code = _apply(tmp_path, _INCUMBENT, patches, "--out", str(tmp_path / "cand.md"))

    assert code == 2
    assert "candidate adds frontmatter lint failures: fm.subset-parse" in capsys.readouterr().err
    assert not (tmp_path / "cand.md").exists()


def test_dry_run_refuses_the_same_candidate(tmp_path: Path, capsys: Capture) -> None:
    patches = [{"op": "insert_after", "anchor": "metadata:", "text": "  capability: {kind: x}"}]

    code = _apply(tmp_path, _INCUMBENT, patches, "--dry-run")

    assert code == 2
    assert "fm.subset-parse" in capsys.readouterr().err


def test_apply_accepts_a_body_edit_that_keeps_the_lint_clean(
    tmp_path: Path, capsys: Capture
) -> None:
    patches = [{"op": "append", "text": "More guidance."}]

    code = _apply(tmp_path, _INCUMBENT, patches, "--out", str(tmp_path / "cand.md"))

    assert code == 0, capsys.readouterr().err
    assert (tmp_path / "cand.md").read_text(encoding="utf-8").endswith("More guidance.")


def test_apply_keeps_a_failure_the_incumbent_already_had(tmp_path: Path, capsys: Capture) -> None:
    broken = _INCUMBENT.replace("metadata:\n", "metadata:\n  capability: {kind: x}\n")
    patches = [{"op": "append", "text": "More guidance."}]

    code = _apply(tmp_path, broken, patches, "--out", str(tmp_path / "cand.md"))

    assert code == 0, capsys.readouterr().err


def test_apply_warns_on_a_new_should_finding_without_refusing(
    tmp_path: Path, capsys: Capture
) -> None:
    patches = [
        {
            "op": "replace",
            "anchor": "description: Demo skill. Do NOT use for other work (use other-skill).",
            "text": "description: Demo skill.",
        }
    ]

    code = _apply(tmp_path, _INCUMBENT, patches, "--out", str(tmp_path / "cand.md"))

    assert code == 0
    assert "WARNING: fm.description.redirect" in capsys.readouterr().err


def test_apply_says_lint_not_run_when_the_linter_is_absent(
    tmp_path: Path, capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "no-such-skillforge" / "lint_skill_frontmatter.py"
    assert not missing.exists()
    monkeypatch.setattr(_skillopt_lint, "_LINT", missing)
    patches = [{"op": "append", "text": "More guidance."}]

    code = _apply(tmp_path, _INCUMBENT, patches, "--out", str(tmp_path / "cand.md"))

    assert code == 0
    assert "NOT RUN" in capsys.readouterr().err
    assert (tmp_path / "cand.md").is_file()


def test_apply_refuses_a_candidate_that_a_must_rule_cannot_evaluate(
    tmp_path: Path, capsys: Capture
) -> None:
    incumbent = _INCUMBENT.replace(
        "metadata:\n", "metadata:\n  capability:\n    kind: orchestrator\n"
    )
    patches = [
        {"op": "insert_after", "anchor": "    role: front-door", "text": "    extra: {a: b}"}
    ]

    code = _apply(tmp_path, incumbent, patches, "--out", str(tmp_path / "cand.md"))

    assert code == 2
    assert "fm.capability.shape" in capsys.readouterr().err


def _fake_lint(results: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(lint_text=lambda _text: results, added_failures=lambda _b, _a: [])


def test_check_candidate_reports_a_not_evaluated_rule_as_not_run(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    rule = SimpleNamespace(id="fm.routing.phrases-routable", level="SHOULD")
    result = SimpleNamespace(
        rule=rule, status="NOT_EVALUATED", messages=("the resolver cannot load",)
    )
    monkeypatch.setattr(_skillopt_lint, "_load_lint", lambda: _fake_lint([result]))

    _skillopt_lint.check_candidate(_INCUMBENT, _INCUMBENT)

    assert (
        "WARNING: fm.routing.phrases-routable: NOT RUN (the resolver cannot load)\n"
        in capsys.readouterr().err
    )


def test_check_candidate_stays_silent_for_pass_and_not_applicable(
    capsys: Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    rule = SimpleNamespace(id="fm.size.headroom", level="SHOULD")
    results = [
        SimpleNamespace(rule=rule, status="PASS", messages=()),
        SimpleNamespace(rule=rule, status="NOT_APPLICABLE", messages=("n/a",)),
    ]
    monkeypatch.setattr(_skillopt_lint, "_load_lint", lambda: _fake_lint(results))

    _skillopt_lint.check_candidate(_INCUMBENT, _INCUMBENT)

    assert capsys.readouterr().err == ""
