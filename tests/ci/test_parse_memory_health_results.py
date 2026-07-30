"""Tests for the memory health result parser (#3541, #3971).

The shell this replaces derived a ``has_stale`` flag from a ``jq`` read and
tolerated both a missing report and a missing key. Those two tolerances are
the reason the downstream comment step never breaks, so they are pinned here.

Issue #3971 found the parser reading a ``summary`` object that the surviving
producer never emits. The tests below pin the real schema, and the gates in
``TestProducerContract`` are class-level: they catch the next drift of this
shape rather than only the keys that drifted this time.
"""

from __future__ import annotations

import contextlib
import io
import json
import shlex
from pathlib import Path

import pytest
import yaml

from scripts.ci import parse_memory_health_results as parser

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

_HEALTHY: dict[str, object] = {
    "total_memories": 9,
    "total_citations": 12,
    "valid_citations": 12,
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


def _healthy(**overrides: object) -> dict[str, object]:
    return {**_HEALTHY, **overrides}


def _outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "gh-output"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def _parsed(out: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in out.read_text(encoding="utf-8").splitlines()
        if line
    )


class TestMissingReport:
    """A missing report is not a failure."""

    def test_missing_report_succeeds(self, tmp_path: Path, monkeypatch) -> None:
        """Positive: the step exits zero so the comment step still runs."""
        out = _outputs(tmp_path, monkeypatch)
        rc = parser.main(["--results", str(tmp_path / "absent.json")])
        assert rc == 0
        assert _parsed(out) == {"has_stale": "false", "total_memories": "0"}

    def test_missing_report_emits_no_other_fields(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Negative: the remaining fields must stay absent, not empty."""
        out = _outputs(tmp_path, monkeypatch)
        parser.main(["--results", str(tmp_path / "absent.json")])
        assert "valid_citations=" not in out.read_text(encoding="utf-8")


class TestStaleFlag:
    """``has_stale`` drives whether the comment reports Warning or Pass."""

    def test_positive_stale_citation_count_sets_the_flag(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Positive: any stale citation raises the flag."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, _healthy(stale_citations=3))
        assert parser.main(["--results", str(results)]) == 0
        assert _parsed(out)["has_stale"] == "true"

    def test_broken_citations_alone_set_the_flag(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Positive: a broken citation is an issue even with none stale."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, _healthy(broken_citations=1))
        parser.main(["--results", str(results)])
        assert _parsed(out)["has_stale"] == "true"

    def test_stale_memories_alone_set_the_flag(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Positive: the producer exits 1 on these, so the comment must agree.

        This is the state the repository is actually in. Reading only the
        citation counts reported Pass while the tool itself returned 1.
        """
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, _healthy(stale_memories=["a", "b"]))
        parser.main(["--results", str(results)])
        parsed = _parsed(out)
        assert parsed["has_stale"] == "true"
        assert parsed["stale_memory_count"] == "2"

    def test_a_healthy_report_clears_the_flag(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Negative: a healthy corpus must report Pass."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, _healthy())
        parser.main(["--results", str(results)])
        assert _parsed(out)["has_stale"] == "false"

    def test_all_comment_fields_are_emitted(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Positive: every value the comment step reads is present."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(
            tmp_path,
            _healthy(
                total_memories=9,
                total_citations=12,
                valid_citations=6,
                stale_citations=3,
                broken_citations=2,
                unverified_citations=1,
                health_score=0.5,
                stale_memories=["m1"],
            ),
        )
        parser.main(["--results", str(results)])
        parsed = _parsed(out)
        assert parsed["total_memories"] == "9"
        assert parsed["total_citations"] == "12"
        assert parsed["valid_citations"] == "6"
        assert parsed["stale_citations"] == "3"
        assert parsed["broken_citations"] == "2"
        assert parsed["unverified_citations"] == "1"
        assert parsed["health_score"] == "0.5"
        assert parsed["stale_memory_count"] == "1"

    def test_a_missing_stale_key_is_not_stale(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Edge: a missing key rendered as null and read as not stale."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, {"total_memories": 9})
        assert parser.main(["--results", str(results)]) == 0
        parsed = _parsed(out)
        assert parsed["has_stale"] == "false"
        assert parsed["stale_citations"] == "null"

    def test_a_non_numeric_stale_value_is_not_stale(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Edge: a string count must not crash the step."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, {"stale_citations": "many"})
        assert parser.main(["--results", str(results)]) == 0
        assert _parsed(out)["has_stale"] == "false"

    def test_a_boolean_stale_value_is_not_stale(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Edge: ``True`` is an int in Python but was never a count."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, {"stale_citations": True})
        parser.main(["--results", str(results)])
        assert _parsed(out)["has_stale"] == "false"

    def test_a_negative_stale_count_is_not_stale(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Edge: the shell used ``-gt 0``, not "non-zero"."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, {"stale_citations": -1})
        parser.main(["--results", str(results)])
        assert _parsed(out)["has_stale"] == "false"

    def test_a_non_list_stale_memories_value_counts_as_zero(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Edge: a scalar where a list belongs must not crash the step."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, _healthy(stale_memories="oops"))
        assert parser.main(["--results", str(results)]) == 0
        parsed = _parsed(out)
        assert parsed["stale_memory_count"] == "0"
        assert parsed["has_stale"] == "false"

    @pytest.mark.parametrize("payload", [[], "x", 1, None, True])
    def test_a_non_object_shape_reads_as_absent(
        self, tmp_path: Path, monkeypatch, payload
    ) -> None:
        """Edge: a report that is not an object reads as null, not a crash."""
        out = _outputs(tmp_path, monkeypatch)
        results = _report(tmp_path, payload)
        assert parser.main(["--results", str(results)]) == 0
        parsed = _parsed(out)
        assert parsed["total_memories"] == "null"
        assert parsed["has_stale"] == "false"


class TestFailureModes:
    """Only an unreadable report is an error."""

    def test_malformed_json_fails_loudly(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Negative: a truncated report must not read as zero stale."""
        _outputs(tmp_path, monkeypatch)
        path = tmp_path / "health-report.json"
        path.write_text("{not json", encoding="utf-8")
        assert parser.main(["--results", str(path)]) == 1
        assert "::error::" in capsys.readouterr().out

    def test_the_error_names_the_report(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Edge: the annotation must identify which file failed."""
        _outputs(tmp_path, monkeypatch)
        path = tmp_path / "health-report.json"
        path.write_text("{not json", encoding="utf-8")
        parser.main(["--results", str(path)])
        assert "health-report.json" in capsys.readouterr().out


class TestOutputHandling:
    """Step outputs append; they never truncate."""

    def test_existing_output_content_is_preserved(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Edge: a prior step's outputs must survive."""
        out = _outputs(tmp_path, monkeypatch)
        out.write_text("earlier=kept\n", encoding="utf-8")
        results = _report(tmp_path, _healthy())
        parser.main(["--results", str(results)])
        assert _parsed(out)["earlier"] == "kept"

    def test_without_the_env_var_values_go_to_stdout(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Edge: running outside Actions must still be inspectable."""
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        results = _report(tmp_path, _healthy(stale_citations=2))
        assert parser.main(["--results", str(results)]) == 0
        assert "has_stale=true" in capsys.readouterr().out


def _module_invocations(text: str) -> list[list[str]]:
    """Return the argv of every ``-m memory_enhancement`` call in a run block."""
    found: list[list[str]] = []
    for line in text.splitlines():
        if "-m memory_enhancement" not in line:
            continue
        command = line.split(">")[0]  # drop redirections; argparse never sees them
        tokens = shlex.split(command, comments=True)
        marker = tokens.index("memory_enhancement")
        found.append(tokens[marker + 1 :])
    return found


def _run_blocks(workflow: Path) -> str:
    """Concatenate every ``run:`` script in a workflow."""
    document = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    blocks: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            run = node.get("run")
            if isinstance(run, str):
                blocks.append(run)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return "\n".join(blocks)


def _emitted_keys() -> set[str]:
    """Run the real health command and return the JSON keys it emits."""
    from memory_enhancement.__main__ import main as producer_main

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        with contextlib.suppress(SystemExit):
            producer_main(["--repo-root", str(REPO_ROOT), "health", "--json"])
    return set(json.loads(stdout.getvalue()))


class TestProducerContract:
    """Class-level gates against a workflow drifting from the tool it runs.

    Both defects in issue #3971 were the same shape: this repository invoked a
    tool with arguments it no longer accepted, and read keys it no longer
    emitted. These tests catch that class, not only the instances that drifted.
    """

    def test_every_workflow_invocation_is_accepted_by_the_real_cli(self) -> None:
        """Positive: argparse must accept every invocation the workflows make.

        This is the gate that would have caught ``--repo-root`` passed after
        the subcommand. argparse rejected it with exit code 2 while the step's
        redirect still created an empty report file, so the failure surfaced
        two steps later as an unreadable report.
        """
        from memory_enhancement.__main__ import _build_parser

        invocations = [
            (workflow.name, argv)
            for workflow in sorted(WORKFLOWS.glob("*.yml"))
            for argv in _module_invocations(_run_blocks(workflow))
        ]
        assert invocations, "no memory_enhancement invocations found to check"

        for name, argv in invocations:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                try:
                    _build_parser().parse_args(argv)
                except SystemExit as exit_signal:
                    pytest.fail(
                        f"{name} calls memory_enhancement with {argv!r}, which "
                        f"the CLI rejects (exit {exit_signal.code}): "
                        f"{stderr.getvalue().strip()}"
                    )

    def test_a_bad_invocation_would_be_caught(self) -> None:
        """Negative control: the gate above must be able to fail."""
        from memory_enhancement.__main__ import _build_parser

        with contextlib.redirect_stderr(io.StringIO()):
            with pytest.raises(SystemExit):
                _build_parser().parse_args(["health", "--repo-root", "."])

    def test_the_parser_reads_only_keys_the_producer_emits(self) -> None:
        """Positive: every field this script reads must exist in the report.

        This is the gate that would have caught the parser reading a
        ``summary`` object the surviving producer never emitted.
        """
        emitted = _emitted_keys()
        consumed = set(parser._REPORT_FIELDS) | {
            "stale_citations",
            "broken_citations",
            "stale_memories",
        }
        assert consumed <= emitted, (
            "parser reads keys the producer does not emit: "
            f"{sorted(consumed - emitted)}"
        )

    def test_the_producer_key_set_is_discoverable(self) -> None:
        """Edge: the gate above is worthless if key discovery returns nothing."""
        assert len(_emitted_keys()) >= 7


class TestWorkflowWiring:
    """The workflow must call the script this module tests."""

    def test_memory_health_calls_the_parser(self) -> None:
        """Positive: extraction is only real once the YAML points here."""
        text = (WORKFLOWS / "memory-health.yml").read_text(encoding="utf-8")
        assert "scripts/ci/parse_memory_health_results.py" in text

    def test_memory_health_no_longer_shells_out_to_jq(self) -> None:
        """Negative: the replaced shell must be gone, not merely bypassed."""
        text = (WORKFLOWS / "memory-health.yml").read_text(encoding="utf-8")
        assert "jq '.summary.total'" not in text

    @pytest.mark.parametrize(
        "workflow", ["memory-health.yml", "memory-validation.yml"]
    )
    def test_no_workflow_filters_on_the_deleted_package_path(
        self, workflow: str
    ) -> None:
        """Negative: a path filter that can never match watches nothing.

        The package moved out of ``.claude/skills/`` in ``2aeb4fddd``. Both
        workflows kept filtering on the old location, so neither reacted to a
        change in the tool it runs.
        """
        text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
        assert ".claude/skills/memory-enhancement/src" not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
