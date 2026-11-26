"""Guards for the agent success-criterion gate (ADR-065 Decision 2, issue #7639).

A router can only retry on a signal it can read, so every agent declares one
in a top-level ``success_criterion`` frontmatter key.

Coverage:

- positive: each machine kind with a valid value passes; ``human-judgment``
  with a real rationale passes; the real repository tree passes, and its regex
  criteria match the verdict lines their agents' bodies define.
- negative: a missing criterion, a non-mapping, an unknown kind, an unknown
  field, a machine kind with no value, ``human-judgment`` with a value, a
  regex that does not compile, an out-of-range exit code, an empty or short
  rationale, placeholder text, and a rationale copied across agents all fail.
- edge: boolean exit codes, a criterion nested under ``metadata``, malformed
  or missing frontmatter, a missing tree, an empty tree, and an invalid root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_agent_success_criterion as gate
import success_criterion as rules

_RATIONALE = "A design review is judged on trade-off quality, which no schema can score."


def _hj(rationale: str = _RATIONALE) -> dict[str, object]:
    return {"kind": "human-judgment", "rationale": rationale}


def _agent_text(criterion: object = None, *, metadata: object = "absent") -> str:
    frontmatter: dict[str, object] = {"name": "sample", "description": "A sample agent."}
    if metadata != "absent":
        frontmatter["metadata"] = metadata
    if criterion is not None:
        frontmatter["success_criterion"] = criterion
    return f"---\n{yaml.safe_dump(frontmatter, sort_keys=False)}---\n\n# Sample\n"


def _tree(tmp_path: Path, agents: dict[str, str]) -> Path:
    tree = tmp_path / gate.AGENT_TREE
    tree.mkdir(parents=True)
    for name, text in agents.items():
        (tree / f"{name}.md").write_text(text, encoding="utf-8")
    return tmp_path


class TestCriterionPasses:
    @pytest.mark.parametrize(
        ("kind", "value"),
        [
            ("exit-code", 0),
            ("exit-code", 255),
            ("regex", r"(?m)^VERDICT: (PASS|WARN)$"),
            ("schema", ".agents/schemas/report.schema.json"),
            ("test", "tests/test_sample.py::test_returns_report"),
        ],
    )
    def test_machine_kind_with_value(self, kind: str, value: object) -> None:
        criterion = {"kind": kind, "value": value, "rationale": _RATIONALE}
        assert rules.check_criterion(criterion) == []

    def test_human_judgment_with_rationale(self) -> None:
        assert rules.check_criterion(_hj()) == []


class TestCriterionFails:
    def test_missing(self) -> None:
        assert "no top-level success_criterion" in rules.check_criterion(None)[0]

    def test_not_a_mapping(self) -> None:
        assert "must be a mapping" in rules.check_criterion("human-judgment")[0]

    def test_unknown_kind(self) -> None:
        findings = rules.check_criterion({"kind": "vibes", "rationale": _RATIONALE})
        assert any("'kind' must be one of" in f for f in findings)

    def test_missing_kind(self) -> None:
        findings = rules.check_criterion({"rationale": _RATIONALE})
        assert any("'kind' must be one of" in f for f in findings)

    def test_unknown_field(self) -> None:
        findings = rules.check_criterion({**_hj(), "threshold": 3})
        assert findings == ["unknown field 'threshold' (allowed: kind, rationale, value)"]

    @pytest.mark.parametrize("kind", ["exit-code", "regex", "schema", "test"])
    def test_machine_kind_without_value(self, kind: str) -> None:
        findings = rules.check_criterion({"kind": kind, "rationale": _RATIONALE})
        assert findings == [f"kind '{kind}' requires a 'value'"]

    def test_human_judgment_with_value(self) -> None:
        findings = rules.check_criterion({**_hj(), "value": "anything"})
        assert any("takes no 'value'" in f for f in findings)

    def test_regex_that_does_not_compile(self) -> None:
        findings = rules.check_criterion({"kind": "regex", "value": "(", "rationale": _RATIONALE})
        assert any("does not compile" in f for f in findings)

    @pytest.mark.parametrize("value", [-1, 256, "0", True, 1.5])
    def test_bad_exit_code(self, value: object) -> None:
        findings = rules.check_criterion(
            {"kind": "exit-code", "value": value, "rationale": _RATIONALE}
        )
        assert any("integer from 0 to 255" in f for f in findings)

    @pytest.mark.parametrize("value", ["", "   ", 7, None])
    def test_empty_string_value(self, value: object) -> None:
        findings = rules.check_criterion(
            {"kind": "schema", "value": value, "rationale": _RATIONALE}
        )
        assert any("non-empty string value" in f for f in findings)

    def test_machine_kind_still_needs_rationale(self) -> None:
        findings = rules.check_criterion({"kind": "exit-code", "value": 0})
        assert findings == ["'rationale' must be a non-empty string"]

    @pytest.mark.parametrize("rationale", ["", "   ", None, 12])
    def test_empty_rationale(self, rationale: object) -> None:
        assert rules.check_criterion({"kind": "human-judgment", "rationale": rationale}) == [
            "'rationale' must be a non-empty string"
        ]

    def test_short_rationale(self) -> None:
        findings = rules.check_criterion(_hj("Judged by review."))
        assert any("too short" in f for f in findings)

    def test_long_single_word_rationale_is_short(self) -> None:
        findings = rules.check_criterion(_hj("x" * 60))
        assert any("too short" in f for f in findings)

    @pytest.mark.parametrize("word", ["TBD", "todo", "placeholder", "n/a"])
    def test_placeholder_rationale(self, word: str) -> None:
        findings = rules.check_criterion(
            _hj(f"The success signal for this agent is {word} for now.")
        )
        assert any("placeholder text" in f for f in findings)


class TestDuplicateRationales:
    def test_shared_text_is_reported_for_each_agent(self) -> None:
        shared = rules.duplicate_rationales(
            {"a": _RATIONALE, "b": f"  {_RATIONALE.upper()} ", "c": "x"}
        )
        assert shared == {"a": ["b"], "b": ["a"]}

    def test_distinct_text_is_clean(self) -> None:
        assert rules.duplicate_rationales({"a": _RATIONALE, "b": _RATIONALE + " Also."}) == {}


class TestTree:
    def test_clean_tree_passes(self, tmp_path: Path) -> None:
        root = _tree(
            tmp_path, {"one": _agent_text(_hj()), "two": _agent_text(_hj(_RATIONALE + " Two."))}
        )
        assert gate.find_criterion_findings(root) == []

    def test_copied_rationale_fails_both_agents(self, tmp_path: Path) -> None:
        root = _tree(tmp_path, {"one": _agent_text(_hj()), "two": _agent_text(_hj())})
        findings = gate.find_criterion_findings(root)
        assert findings == [
            ("one", "'rationale' is copied from two; write one for this agent"),
            ("two", "'rationale' is copied from one; write one for this agent"),
        ]

    def test_agent_without_metadata_fails(self, tmp_path: Path) -> None:
        root = _tree(tmp_path, {"one": _agent_text()})
        assert "no top-level success_criterion" in gate.find_criterion_findings(root)[0][1]

    def test_metadata_without_criterion_is_missing(self, tmp_path: Path) -> None:
        root = _tree(tmp_path, {"one": _agent_text(metadata={"role": "support"})})
        assert "no top-level success_criterion" in gate.find_criterion_findings(root)[0][1]

    def test_nested_criterion_is_reported(self, tmp_path: Path) -> None:
        nested = {"role": "support", "success_criterion": _hj()}
        root = _tree(tmp_path, {"one": _agent_text(metadata=nested)})
        findings = [text for _, text in gate.find_criterion_findings(root)]
        assert "success_criterion is nested under metadata; move it to the top level" in findings
        assert any("no top-level success_criterion" in text for text in findings)

    def test_nested_and_top_level_still_reports_the_nested_copy(self, tmp_path: Path) -> None:
        text = _agent_text(_hj(), metadata={"success_criterion": _hj()})
        root = _tree(tmp_path, {"one": text})
        assert gate.find_criterion_findings(root) == [
            ("one", "success_criterion is nested under metadata; move it to the top level")
        ]

    @pytest.mark.parametrize(
        ("text", "detail"),
        [
            ("# no frontmatter\n", "no YAML frontmatter block"),
            ("---\nname: one\n", "no YAML frontmatter block"),
            ("---\nname: [unclosed\n---\n", "not valid YAML"),
            ("---\n- a list\n---\n", "not a mapping"),
        ],
    )
    def test_unreadable_frontmatter_fails(self, tmp_path: Path, text: str, detail: str) -> None:
        root = _tree(tmp_path, {"one": text})
        ((name, finding),) = gate.find_criterion_findings(root)
        assert name == "one" and detail in finding

    def test_repeated_key_inside_criterion_fails(self, tmp_path: Path) -> None:
        text = (
            "---\nname: one\ndescription: d\nsuccess_criterion:\n  kind: regex\n"
            "  value: '('\n  value: '^PASS$'\n"
            f"  rationale: {_RATIONALE}\n---\n"
        )
        root = _tree(tmp_path, {"one": text})
        ((name, finding),) = gate.find_criterion_findings(root)
        assert name == "one" and "duplicate key 'value'" in finding

    def test_missing_tree_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            gate.find_criterion_findings(tmp_path)

    def test_empty_tree_raises(self, tmp_path: Path) -> None:
        (tmp_path / gate.AGENT_TREE).mkdir(parents=True)
        with pytest.raises(FileNotFoundError):
            gate.find_criterion_findings(tmp_path)


class TestEntryPoints:
    def test_clean_tree_exit_zero(self, tmp_path: Path) -> None:
        root = _tree(tmp_path, {"one": _agent_text(_hj())})
        assert gate.main([str(root)]) == 0

    def test_dirty_tree_exit_one_and_names_the_agent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _tree(tmp_path, {"lonely": _agent_text()})
        assert gate.main([str(root)]) == 1
        assert "lonely: no top-level success_criterion" in capsys.readouterr().err

    def test_empty_tree_exit_one(self, tmp_path: Path) -> None:
        (tmp_path / gate.AGENT_TREE).mkdir(parents=True)
        assert gate.main([str(tmp_path)]) == 1

    def test_missing_tree_exit_two(self, tmp_path: Path) -> None:
        assert gate.main([str(tmp_path)]) == 2

    def test_invalid_root_exit_two(self, tmp_path: Path) -> None:
        assert gate.main([str(tmp_path / "absent")]) == 2


class TestRealTree:
    def test_repository_tree_passes(self) -> None:
        assert gate.find_criterion_findings(REPO_ROOT) == []

    @pytest.mark.parametrize(
        ("agent", "good", "bad"),
        [
            ("code-reviewer", "Findings.\nVERDICT: WARN\n", "VERDICT: OK\n"),
            ("code-reviewer", "Findings.\nVERDICT: PASS", "VERDICT: PASS\nmore findings\n"),
            ("code-reviewer", "Findings.\nVERDICT: PASS\r\n\n", "VERDICT: PASS\n\nmore\n"),
            (
                "critic",
                "## Verdict\nNEEDS_REVISION - Confidence: MEDIUM\n",
                "LGTM - Confidence: HIGH\n",
            ),
        ],
    )
    def test_regex_criteria_match_their_verdict_lines(
        self, agent: str, good: str, bad: str
    ) -> None:
        pattern = _criterion_pattern(agent)
        assert pattern.search(good)
        assert not pattern.search(bad)

    def test_code_reviewer_criterion_matches_every_verdict_its_body_mandates(self) -> None:
        body = (REPO_ROOT / gate.AGENT_TREE / "code-reviewer.md").read_text(encoding="utf-8")
        tokens = re.search(r"`VERDICT: ([A-Z_]+(?:\|[A-Z_]+)+)`", body)
        assert tokens, "code-reviewer body no longer names its verdict tokens"
        pattern = _criterion_pattern("code-reviewer")
        for token in tokens.group(1).split("|"):
            assert pattern.search(f"Findings.\nVERDICT: {token}\n"), token

    def test_critic_criterion_matches_every_verdict_its_body_mandates(self) -> None:
        body = (REPO_ROOT / gate.AGENT_TREE / "critic.md").read_text(encoding="utf-8")
        verdicts = re.findall(r"^\| \*\*([A-Z_]+)\*\* \|", body, re.MULTILINE)
        levels = re.search(r"\[VERDICT\] - Confidence: \[([A-Z|]+)\]", body)
        assert verdicts and levels, "critic body no longer defines its verdict line"
        pattern = _criterion_pattern("critic")
        for verdict in verdicts:
            for level in levels.group(1).split("|"):
                assert pattern.search(f"## Verdict\n{verdict} - Confidence: {level}\n")


def _criterion_pattern(agent: str) -> re.Pattern[str]:
    criterion = gate.read_criterion(REPO_ROOT / gate.AGENT_TREE / f"{agent}.md")
    assert isinstance(criterion, dict) and criterion["kind"] == "regex"
    return re.compile(str(criterion["value"]))
