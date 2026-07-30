"""Tests for the memory health result parser (#3541, #3971).

Every payload here comes from the real producer rather than a hand-written
object. The suite this replaces built each fixture as ``{"summary": {...}}``,
a shape ``memory_enhancement health --json`` has never emitted, so fifteen
green tests certified a parser that read nothing. Deriving the fixtures from
the producer is what keeps that from happening again.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from memory_enhancement.__main__ import _build_parser
from scripts.ci import parse_memory_health_results as parser

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


@pytest.fixture(scope="module")
def real_payload(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    """Return a health report produced by the real command.

    Runs against a throwaway memories directory so the payload is cheap and
    deterministic, but the keys are the producer's own.
    """
    root = tmp_path_factory.mktemp("memories-root")
    memories = root / ".serena" / "memories"
    memories.mkdir(parents=True)
    (memories / "sample.md").write_text("# Sample\n\nNo citations.\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "memory_enhancement",
            "--repo-root",
            str(root),
            "health",
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "health-report.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "gh-output"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def _parsed(out: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines() if line
    )


_REDIRECT = re.compile(r"\d?>>?\s*\S+")
_SEPARATOR = re.compile(r"&&|\|\||[|;]")

# Output names that intentionally differ from the producer key they read.
_APPROVED_RENAMES = {"total": "total_memories"}


def _argv_after_module(line: str) -> list[str]:
    """Return the argv a workflow passes to the module, redirects removed.

    Redirections are stripped wherever they sit, because arguments may legally
    follow one. Truncating at the first ``>`` hid that: it made
    ``... health --json > /dev/null --repo-root .`` look valid when the shell
    rejects it with the exact exit 2 this gate exists to catch.
    """
    body = line.split("-m memory_enhancement", 1)[1]
    return shlex.split(_SEPARATOR.split(_REDIRECT.sub(" ", body), 1)[0])


def _unapproved_renames(sources: dict[str, str]) -> list[str]:
    """Return output names reading a producer key they were not mapped to."""
    return sorted(
        name
        for name, key in sources.items()
        if name != key and _APPROVED_RENAMES.get(name) != key
    )


class TestProducerContract:
    """The parser may only read keys the producer actually emits."""

    def test_every_key_read_exists_in_a_real_report(self, real_payload) -> None:
        """Positive: the read set is a subset of the emitted set."""
        missing = parser.producer_keys_read() - set(real_payload)
        assert not missing, f"parser reads keys the producer never emits: {sorted(missing)}"

    def test_the_contract_check_can_fail(self, real_payload) -> None:
        """Negative control: a bogus key is reported as missing.

        Without this, a producer that emitted every conceivable key would make
        the test above unfalsifiable.
        """
        assert {"summary"} - set(real_payload) == {"summary"}

    def test_a_real_report_parses_into_non_null_outputs(
        self, real_payload, tmp_path, monkeypatch
    ) -> None:
        """Positive: the end-to-end read produces real values, not nulls."""
        results = _write(tmp_path, real_payload)
        out = _outputs(tmp_path, monkeypatch)
        assert parser.main(["--results", str(results)]) == 0
        parsed = _parsed(out)
        assert parsed["total"] == "1"
        assert parsed["stale"] == "0"
        assert parsed["has_stale"] == "false"
        assert "null" not in parsed.values()

    def test_no_output_reads_an_unapproved_key(self) -> None:
        """Positive: every mapping is identity or a declared rename."""
        assert not _unapproved_renames(parser._FIELD_SOURCES)

    def test_a_swapped_mapping_is_caught(self) -> None:
        """Negative control: pointing an output at a sibling key fails.

        Key membership alone cannot see this. Every candidate key is present
        in a real report, and a healthy fixture's counts are all zero, so a
        swap stays invisible to both the subset check and the value check.
        """
        swapped = dict(parser._FIELD_SOURCES) | {"broken_citations": "valid_citations"}
        assert _unapproved_renames(swapped) == ["broken_citations"]


class TestWorkflowInvocations:
    """Every workflow call of the module must parse under the real parser."""

    @staticmethod
    def _invocations() -> list[tuple[str, list[str]]]:
        found: list[tuple[str, list[str]]] = []
        for path in sorted(WORKFLOW_DIR.glob("*.yml")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if "-m memory_enhancement" not in line:
                    continue
                found.append((f"{path.name}: {line.strip()}", _argv_after_module(line)))
        return found

    def test_at_least_one_invocation_is_discovered(self) -> None:
        """Negative control: an empty scan would make the next test vacuous."""
        assert self._invocations(), "no workflow invokes the module; the scan is broken"

    def test_all_invocations_parse(self) -> None:
        """Positive: each workflow argv is accepted by the module's parser."""
        for label, argv in self._invocations():
            try:
                _build_parser().parse_args(argv)
            except SystemExit as exc:  # argparse exits 2 on a bad argv
                pytest.fail(f"{label} -> argparse rejected {argv} (code {exc.code})")

    @pytest.mark.parametrize(
        "line",
        [
            "python3 -m memory_enhancement health --json --repo-root . > r.json",
            "python3 -m memory_enhancement --repo-root . health --json > /dev/null --repo-root .",
        ],
    )
    def test_a_bad_invocation_is_rejected(self, line: str) -> None:
        """Negative: bad argv fails *through the scanner*, not around it.

        ``--repo-root`` is declared on the top-level parser, so placing it
        after the subcommand exits 2. That is the defect from #3971. The
        second line is the one an earlier scanner passed by truncating at the
        first ``>``: arguments may legally follow a redirection, and the shell
        rejects that command with the same exit 2.
        """
        with pytest.raises(SystemExit):
            _build_parser().parse_args(_argv_after_module(line))

    def test_the_scanner_keeps_arguments_that_follow_a_redirect(self) -> None:
        """Edge: a redirect is removed, but nothing after it is dropped."""
        line = "python3 -m memory_enhancement --repo-root . health --json > /dev/null --x 1"
        assert _argv_after_module(line) == [
            "--repo-root",
            ".",
            "health",
            "--json",
            "--x",
            "1",
        ]


class TestFatalReports:
    """Every shape the producer could not have emitted is fatal.

    Before #3971 each of these read as ``has_stale=false`` and exited 0, so a
    broken producer posted a green "Pass". That is the failure this module
    exists to surface, so tolerance here is the bug, not a feature.
    """

    def test_a_missing_report_fails_loudly(self, tmp_path, monkeypatch, capsys) -> None:
        """Positive: an absent file cannot read as a healthy run.

        The producer step redirects into the report, so the file exists even
        when the command dies. Its absence means the step never ran at all.
        """
        _outputs(tmp_path, monkeypatch)
        assert parser.main(["--results", str(tmp_path / "absent.json")]) == 1
        assert "::error::Could not read absent.json" in capsys.readouterr().out

    @pytest.mark.parametrize("body", ["", "   ", "\n\n"])
    def test_an_empty_report_fails_loudly(self, tmp_path, monkeypatch, capsys, body) -> None:
        """Positive: the shape a crashed producer leaves behind is fatal.

        ``continue-on-error`` on the producer step means a crash shows up here
        as a zero-byte file.
        """
        results = tmp_path / "health-report.json"
        results.write_text(body, encoding="utf-8")
        _outputs(tmp_path, monkeypatch)
        assert parser.main(["--results", str(results)]) == 1
        assert "empty" in capsys.readouterr().out

    def test_invalid_json_fails_loudly(self, tmp_path, monkeypatch, capsys) -> None:
        """Positive: a truncated report exits 1 with an annotation."""
        results = tmp_path / "health-report.json"
        results.write_text("{not json", encoding="utf-8")
        _outputs(tmp_path, monkeypatch)
        assert parser.main(["--results", str(results)]) == 1
        assert "::error::Could not read health-report.json" in capsys.readouterr().out

    @pytest.mark.parametrize("payload", [[], "x", 1, None, True])
    def test_a_non_object_report_fails_loudly(self, tmp_path, monkeypatch, payload) -> None:
        """Edge: valid JSON that is not an object is still not a report."""
        _outputs(tmp_path, monkeypatch)
        assert parser.main(["--results", str(_write(tmp_path, payload))]) == 1

    def test_the_pre_fix_summary_shape_fails_loudly(self, tmp_path, monkeypatch, capsys) -> None:
        """Edge: the fabricated shape the old suite tested is now rejected.

        ``{"summary": {...}}`` is what fifteen green tests asserted against a
        parser that read nothing. It carries no key the producer emits.
        """
        payload = {"summary": {"total": 9, "healthy": 6, "stale": 3}}
        _outputs(tmp_path, monkeypatch)
        assert parser.main(["--results", str(_write(tmp_path, payload))]) == 1
        assert "missing keys the producer emits" in capsys.readouterr().out

    def test_dropping_any_read_key_fails_loudly(
        self, real_payload, tmp_path, monkeypatch
    ) -> None:
        """Positive: a producer regression that drops one key is caught.

        Rendering the survivors and calling it a Pass is what defect B did.
        The key list is read inside the test so that removing the accessor
        fails one test rather than breaking collection for the whole suite.
        """
        for dropped in sorted(parser.producer_keys_read()):
            payload = {k: v for k, v in real_payload.items() if k != dropped}
            _outputs(tmp_path, monkeypatch)
            assert parser.main(["--results", str(_write(tmp_path, payload))]) == 1, (
                f"dropping {dropped} was tolerated"
            )

    @pytest.mark.parametrize("value", [None, "3", 3, {}])
    def test_a_non_list_stale_value_fails_loudly(
        self, real_payload, tmp_path, monkeypatch, value
    ) -> None:
        """Edge: the one field that decides the gate must be the right type."""
        payload = {**real_payload, "stale_memories": value}
        _outputs(tmp_path, monkeypatch)
        assert parser.main(["--results", str(_write(tmp_path, payload))]) == 1

    def test_a_real_report_is_not_fatal(
        self, real_payload, tmp_path, monkeypatch, capsys
    ) -> None:
        """Negative control: none of the above fires on a real report.

        Without this, making every branch fatal would pass this class while
        breaking the workflow outright.
        """
        _outputs(tmp_path, monkeypatch)
        assert parser.main(["--results", str(_write(tmp_path, real_payload))]) == 0
        assert "::error::" not in capsys.readouterr().out


class TestStaleFlag:
    """``has_stale`` is derived from the length of the stale list."""

    def test_stale_memories_set_the_flag(self, real_payload, tmp_path, monkeypatch) -> None:
        """Positive: a non-empty stale list reads as stale."""
        payload = {**real_payload, "stale_memories": ["a", "b", "c"]}
        out = _outputs(tmp_path, monkeypatch)
        parser.main(["--results", str(_write(tmp_path, payload))])
        parsed = _parsed(out)
        assert parsed["stale"] == "3"
        assert parsed["has_stale"] == "true"

    def test_an_empty_stale_list_clears_the_flag(
        self, real_payload, tmp_path, monkeypatch
    ) -> None:
        """Negative: zero stale memories must not raise the flag."""
        payload = {**real_payload, "stale_memories": []}
        out = _outputs(tmp_path, monkeypatch)
        parser.main(["--results", str(_write(tmp_path, payload))])
        parsed = _parsed(out)
        assert parsed["stale"] == "0"
        assert parsed["has_stale"] == "false"


class TestOutputHandling:
    """Outputs go to ``GITHUB_OUTPUT`` when set and to stdout otherwise."""

    def test_outputs_append_rather_than_truncate(
        self, real_payload, tmp_path, monkeypatch
    ) -> None:
        """Edge: an existing output file keeps its earlier lines."""
        out = _outputs(tmp_path, monkeypatch)
        out.write_text("earlier=1\n", encoding="utf-8")
        parser.main(["--results", str(_write(tmp_path, real_payload))])
        assert _parsed(out)["earlier"] == "1"

    def test_outputs_fall_back_to_stdout(
        self, real_payload, tmp_path, monkeypatch, capsys
    ) -> None:
        """Negative: no GITHUB_OUTPUT means print, not crash."""
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        assert parser.main(["--results", str(_write(tmp_path, real_payload))]) == 0
        assert "total=1" in capsys.readouterr().out


class TestWorkflowWiring:
    """The workflow must consume the outputs this script actually emits."""

    def test_every_consumed_output_is_emitted(self, real_payload, tmp_path, monkeypatch) -> None:
        """Positive: no ``steps.parse.outputs.X`` reads a field we dropped."""
        out = _outputs(tmp_path, monkeypatch)
        parser.main(["--results", str(_write(tmp_path, real_payload))])
        emitted = set(_parsed(out))

        text = (WORKFLOW_DIR / "memory-health.yml").read_text(encoding="utf-8")
        consumed = set(re.findall(r"steps\.parse\.outputs\.([A-Za-z0-9_-]+)", text))
        assert consumed, "no workflow step consumes the parser; the scan is broken"
        assert consumed <= emitted, f"workflow reads unemitted outputs: {consumed - emitted}"

    def test_the_inline_jq_is_gone(self) -> None:
        """Negative: ADR-006 forbids the shell this script replaced."""
        text = (WORKFLOW_DIR / "memory-health.yml").read_text(encoding="utf-8")
        assert "jq '.summary" not in text
