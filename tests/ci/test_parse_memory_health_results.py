"""Tests for the memory health result parser (#3541, reworked for #3971).

The previous revision of this file pinned a ``summary`` schema that the
surviving ``memory_enhancement`` implementation never emits. It passed because
it built its own fixtures in that shape, so it proved only that the parser was
self-consistent, never that it agreed with the producer.

The two ``TestProducerContract`` and ``TestWorkflowInvocations`` classes exist
to close that gap: they measure the real producer and the real workflow rather
than a fixture, so the drift that broke #3971 cannot recur silently.
"""

from __future__ import annotations

import argparse
import ast
import json
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci import parse_memory_health_results as parser

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
MEMORY_HEALTH_YML = WORKFLOWS / "memory-health.yml"

#: A report in the shape ``memory_enhancement health --json`` emits.
HEALTHY_REPORT: dict[str, Any] = {
    "total_memories": 12,
    "total_citations": 8,
    "valid_citations": 8,
    "stale_citations": 0,
    "broken_citations": 0,
    "unverified_citations": 0,
    "health_score": 1.0,
    "stale_memories": [],
    "recommendations": [],
}


def _report(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "health-report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "gh-output"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def _parsed(out: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines() if line)


def _with(**overrides: Any) -> dict[str, Any]:
    return {**HEALTHY_REPORT, **overrides}


class TestHealthyReport:
    """A clean report produces every documented output."""

    def test_all_fields_are_emitted(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: the workflow reads ten outputs and all ten must appear."""
        out = _outputs(tmp_path, monkeypatch)
        rc = parser.main(["--results", str(_report(tmp_path, HEALTHY_REPORT))])
        assert rc == 0
        assert _parsed(out) == {
            "total_memories": "12",
            "total_citations": "8",
            "valid_citations": "8",
            "stale_citations": "0",
            "broken_citations": "0",
            "unverified_citations": "0",
            "stale_memories": "0",
            "recommendations": "0",
            "health_score": "100%",
            "has_issues": "false",
        }

    def test_list_fields_become_lengths(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: the workflow renders counts, so lists must be measured."""
        out = _outputs(tmp_path, monkeypatch)
        payload = _with(stale_memories=["a.md", "b.md"], recommendations=["x"])
        parser.main(["--results", str(_report(tmp_path, payload))])
        assert _parsed(out)["stale_memories"] == "2"
        assert _parsed(out)["recommendations"] == "1"


class TestHasIssues:
    """``has_issues`` must mirror the producer's own exit-code predicate."""

    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({}, "false"),
            ({"broken_citations": 1}, "true"),
            ({"stale_citations": 1}, "true"),
            ({"stale_memories": ["a.md"]}, "true"),
            ({"unverified_citations": 5}, "false"),
            ({"recommendations": ["do a thing"]}, "false"),
        ],
    )
    def test_predicate_matches_the_producer(
        self, tmp_path: Path, monkeypatch, overrides: dict[str, Any], expected: str
    ) -> None:
        """Edge: only the three fields the producer counts may raise the flag."""
        out = _outputs(tmp_path, monkeypatch)
        parser.main(["--results", str(_report(tmp_path, _with(**overrides)))])
        assert _parsed(out)["has_issues"] == expected

    def test_predicate_is_not_derived_from_health_score(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: a vacuous 100% score must not mask a stale memory."""
        out = _outputs(tmp_path, monkeypatch)
        payload = _with(health_score=1.0, stale_memories=["a.md"])
        parser.main(["--results", str(_report(tmp_path, payload))])
        assert _parsed(out)["health_score"] == "100%"
        assert _parsed(out)["has_issues"] == "true"


class TestCrashIsVisible:
    """A crashed health command must not post a green banner (#2808)."""

    def test_missing_report_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Negative: the previous tolerance is what hid #3971 for months."""
        _outputs(tmp_path, monkeypatch)
        rc = parser.main(["--results", str(tmp_path / "absent.json")])
        assert rc == 1
        assert "missing or empty" in capsys.readouterr().out

    def test_empty_report_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Negative: a zero-byte file is what a crashed redirect leaves behind."""
        _outputs(tmp_path, monkeypatch)
        path = tmp_path / "health-report.json"
        path.write_text("", encoding="utf-8")
        rc = parser.main(["--results", str(path)])
        assert rc == 1
        assert "missing or empty" in capsys.readouterr().out

    def test_corrupt_report_fails(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Negative: truncated JSON is a crash, not a clean run."""
        _outputs(tmp_path, monkeypatch)
        path = tmp_path / "health-report.json"
        path.write_text('{"total_memories":', encoding="utf-8")
        rc = parser.main(["--results", str(path)])
        assert rc == 1
        assert "Could not read" in capsys.readouterr().out

    def test_no_outputs_are_written_on_failure(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: a partial write would let the comment step read stale keys."""
        out = _outputs(tmp_path, monkeypatch)
        parser.main(["--results", str(tmp_path / "absent.json")])
        assert out.read_text(encoding="utf-8") == ""


class TestSchemaMismatchIsLoud:
    """Drift between producer and consumer must fail, never default."""

    def test_summary_shaped_report_is_rejected(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Negative: this is the exact payload shape that caused #3971."""
        _outputs(tmp_path, monkeypatch)
        payload = {"summary": {"total": 5, "healthy": 5, "stale": 0}}
        rc = parser.main(["--results", str(_report(tmp_path, payload))])
        assert rc == 1
        assert "does not match the schema" in capsys.readouterr().out

    @pytest.mark.parametrize("missing", sorted({*parser.COUNT_FIELDS, *parser.LENGTH_FIELDS}))
    def test_each_required_key_is_enforced(
        self, tmp_path: Path, monkeypatch, capsys, missing: str
    ) -> None:
        """Negative: every field the workflow renders must be individually required."""
        _outputs(tmp_path, monkeypatch)
        payload = {k: v for k, v in HEALTHY_REPORT.items() if k != missing}
        rc = parser.main(["--results", str(_report(tmp_path, payload))])
        assert rc == 1
        assert missing in capsys.readouterr().out

    def test_missing_health_score_is_enforced(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: health_score is rendered too, so it is required."""
        _outputs(tmp_path, monkeypatch)
        payload = {k: v for k, v in HEALTHY_REPORT.items() if k != "health_score"}
        assert parser.main(["--results", str(_report(tmp_path, payload))]) == 1

    @pytest.mark.parametrize("bad", ["3", None, True, -1, 1.5])
    def test_non_integer_counter_is_rejected(
        self, tmp_path: Path, monkeypatch, bad: object
    ) -> None:
        """Edge: a string counter would silently render and compare wrongly."""
        _outputs(tmp_path, monkeypatch)
        payload = _report(tmp_path, _with(broken_citations=bad))
        assert parser.main(["--results", str(payload)]) == 1

    @pytest.mark.parametrize("bad", [0, "a.md", None, {"a": 1}])
    def test_non_list_length_field_is_rejected(
        self, tmp_path: Path, monkeypatch, bad: object
    ) -> None:
        """Edge: len() on a str would silently report a character count."""
        _outputs(tmp_path, monkeypatch)
        payload = _report(tmp_path, _with(stale_memories=bad))
        assert parser.main(["--results", str(payload)]) == 1

    @pytest.mark.parametrize("payload", [[], "text", 3, None])
    def test_non_object_payload_is_rejected(
        self, tmp_path: Path, monkeypatch, payload: object
    ) -> None:
        """Edge: jq tolerated non-objects; that tolerance hid the drift."""
        _outputs(tmp_path, monkeypatch)
        assert parser.main(["--results", str(_report(tmp_path, payload))]) == 1

    @pytest.mark.parametrize("bad", ["1.0", None, True])
    def test_non_numeric_health_score_is_rejected(
        self, tmp_path: Path, monkeypatch, bad: object
    ) -> None:
        """Edge: a string score would render without the percent conversion."""
        _outputs(tmp_path, monkeypatch)
        payload = _report(tmp_path, _with(health_score=bad))
        assert parser.main(["--results", str(payload)]) == 1


class TestScoreRendering:
    """The score is a 0..1 ratio and the comment shows a percentage."""

    @pytest.mark.parametrize(
        ("score", "rendered"),
        [(1.0, "100%"), (0.0, "0%"), (0.5, "50%"), (0.756, "76%"), (1, "100%")],
    )
    def test_score_renders_as_percent(
        self, tmp_path: Path, monkeypatch, score: object, rendered: str
    ) -> None:
        """Positive: a raw 0.756 in the PR comment would read as a bug."""
        out = _outputs(tmp_path, monkeypatch)
        parser.main(["--results", str(_report(tmp_path, _with(health_score=score)))])
        assert _parsed(out)["health_score"] == rendered


class TestOutputHandling:
    """Outputs go to GITHUB_OUTPUT when set and stdout otherwise."""

    def test_falls_back_to_stdout(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Edge: local runs have no GITHUB_OUTPUT and must still be readable."""
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        rc = parser.main(["--results", str(_report(tmp_path, HEALTHY_REPORT))])
        assert rc == 0
        assert "has_issues=false" in capsys.readouterr().out

    def test_appends_rather_than_truncates(self, tmp_path: Path, monkeypatch) -> None:
        """Negative: truncating would drop outputs written by earlier steps."""
        out = _outputs(tmp_path, monkeypatch)
        out.write_text("preexisting=1\n", encoding="utf-8")
        parser.main(["--results", str(_report(tmp_path, HEALTHY_REPORT))])
        assert _parsed(out)["preexisting"] == "1"


def _cli_parser() -> argparse.ArgumentParser:
    """Build the real ``memory_enhancement`` parser without running a command."""
    from scripts.memory_enhancement.__main__ import _build_parser

    return _build_parser()


def _module_invocations(text: str) -> list[list[str]]:
    """Return argv lists for every ``-m memory_enhancement`` call in a run block."""
    found: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if "memory_enhancement" not in line or line.startswith("#"):
            continue
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            continue
        if "-m" not in tokens:
            continue
        index = tokens.index("-m")
        if index + 1 >= len(tokens) or tokens[index + 1] != "memory_enhancement":
            continue
        argv: list[str] = []
        for token in tokens[index + 2 :]:
            if token in (">", ">>", "|", "||", "&&", ";"):
                break
            argv.append(token)
        found.append(argv)
    return found


def _workflow_run_blocks() -> list[tuple[str, str]]:
    """Return ``(workflow name, run block)`` pairs across every workflow."""
    blocks: list[tuple[str, str]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in (document.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                run = step.get("run")
                if isinstance(run, str):
                    blocks.append((path.name, run))
    return blocks


class TestWorkflowInvocations:
    """Every workflow call must be accepted by the real CLI parser.

    Issue #3971 shipped ``health --json --repo-root .`` while ``--repo-root``
    was defined on the top-level parser. argparse rejected it with rc=2 on
    every run for months. Parsing the real grammar is the only check that
    catches an argument in the wrong position.
    """

    def test_at_least_one_invocation_is_discovered(self) -> None:
        """Negative control: a scanner that finds nothing proves nothing."""
        found = [argv for _, run in _workflow_run_blocks() for argv in _module_invocations(run)]
        assert found, "no memory_enhancement invocations found; the scanner is broken"

    def test_every_invocation_parses(self) -> None:
        """Positive: an unparseable argv is a guaranteed production failure."""
        cli = _cli_parser()
        failures: list[str] = []
        for name, run in _workflow_run_blocks():
            for argv in _module_invocations(run):
                try:
                    cli.parse_args(argv)
                except SystemExit:
                    failures.append(f"{name}: {' '.join(argv)}")
        assert not failures, f"workflow invocations rejected by the CLI: {failures}"

    def test_the_broken_form_would_be_caught(self) -> None:
        """Negative control: the gate must reject the exact #3971 argv."""
        cli = _cli_parser()
        with pytest.raises(SystemExit):
            cli.parse_args(["health", "--json", "--repo-root", "."])

    def test_the_fixed_form_is_accepted(self) -> None:
        """Positive control: the replacement argv must parse."""
        assert _cli_parser().parse_args(["--repo-root", ".", "health", "--json"])


def _emitted_health_keys() -> set[str]:
    """Return the JSON keys ``_cmd_health`` emits, read from its source."""
    source = (REPO_ROOT / "scripts" / "memory_enhancement" / "__main__.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "_cmd_health":
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Dict) and inner.keys:
                keys = {
                    key.value
                    for key in inner.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                }
                if keys:
                    return keys
    raise AssertionError("could not read the health payload keys from _cmd_health")


class TestProducerContract:
    """The consumer's required keys must exist in the producer's payload.

    This is the gate that would have caught #3971 at the commit that deleted
    the old implementation, rather than months later in an unrelated PR.
    """

    def test_producer_keys_are_discoverable(self) -> None:
        """Negative control: an empty read would make the next test vacuous."""
        assert len(_emitted_health_keys()) >= 5

    def test_every_required_key_is_emitted(self) -> None:
        """Positive: consumer requirements must be a subset of the payload."""
        required = {*parser.COUNT_FIELDS, *parser.LENGTH_FIELDS, "health_score"}
        assert required <= _emitted_health_keys()

    def test_the_deleted_schema_is_not_referenced(self) -> None:
        """Negative: the old ``summary`` contract must be gone, not bypassed."""
        assert "summary" not in _emitted_health_keys()


class TestWorkflowWiring:
    """The workflow must consume exactly the outputs the script emits."""

    def test_memory_health_calls_the_parser(self) -> None:
        """Positive: extraction is only real once the YAML points here."""
        assert "scripts/ci/parse_memory_health_results.py" in MEMORY_HEALTH_YML.read_text(
            encoding="utf-8"
        )

    def test_every_referenced_output_is_emitted(self) -> None:
        """Positive: a typo'd output renders as an empty string in the comment."""
        text = MEMORY_HEALTH_YML.read_text(encoding="utf-8")
        referenced = set(_referenced_parse_outputs(text))
        emitted = {
            *parser.COUNT_FIELDS,
            *parser.LENGTH_FIELDS,
            "health_score",
            "has_issues",
        }
        assert referenced, "no steps.parse.outputs references found; scanner is broken"
        assert referenced <= emitted, f"workflow reads unemitted outputs: {referenced - emitted}"

    def test_the_deleted_summary_fields_are_gone(self) -> None:
        """Negative: leaving one behind would render an empty bullet forever."""
        text = MEMORY_HEALTH_YML.read_text(encoding="utf-8")
        for dead in ("outputs.has_stale", "outputs.healthy", "outputs.exempt"):
            assert dead not in text

    def test_no_inert_pythonpath_prefix(self) -> None:
        """Negative: the path it set was deleted in 2aeb4fddd."""
        text = MEMORY_HEALTH_YML.read_text(encoding="utf-8")
        assert ".claude/skills/memory-enhancement/src" not in text

    def test_path_filters_point_at_paths_that_exist(self) -> None:
        """Negative: a filter on a deleted directory can never match."""
        text = MEMORY_HEALTH_YML.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- '") or not stripped.endswith("'"):
                continue
            pattern = stripped[3:-1]
            root = pattern.split("*", 1)[0].rstrip("/")
            if not root or not root[0].isalnum() and not root.startswith("."):
                continue
            assert (REPO_ROOT / root).exists(), f"path filter references missing {root}"


def _referenced_parse_outputs(text: str) -> list[str]:
    """Return every ``steps.parse.outputs.<name>`` referenced in a workflow."""
    marker = "steps.parse.outputs."
    names: list[str] = []
    start = text.find(marker)
    while start != -1:
        cursor = start + len(marker)
        end = cursor
        while end < len(text) and (text[end].isalnum() or text[end] == "_"):
            end += 1
        names.append(text[cursor:end])
        start = text.find(marker, end)
    return names


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
