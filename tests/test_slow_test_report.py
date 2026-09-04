"""Tests for the slow-test telemetry recorder and report (issue #5382).

Coverage:
* ``module_of`` and ``junit_nodeid``: positive, class-nested, edge (no separator).
* ``load_telemetry`` / ``load_junit``: positive, malformed payload, DOCTYPE
  rejection (the XXE/entity guard).
* ``load_inputs``: JUnit duration merged with recorder process and traversal
  counts for the same node id.
* ``group_by_module``: totals, slow-count threshold, scanner labels.
* ``main``: every documented exit code (0, 1, 2, 3).
* Probes: subprocess and traversal counting, and the negative control that the
  counters stay at zero when no test item is active.
* End-to-end: a real pytest subprocess with the plugin writes a telemetry file
  whose counts match what the generated test actually did, and writes nothing
  when ``--slow-report`` is absent.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.testing import slow_test_report as report

REPO_ROOT = Path(__file__).resolve().parents[1]

_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
<testcase classname="tests.test_alpha" name="test_one" time="4.500" />
<testcase classname="tests.test_alpha.TestGroup" name="test_two" time="7.250" />
</testsuite></testsuites>
"""

# 602 of this repository's 998 test files sit in a package under tests/, so this
# classname shape, not the flat one above, is the common CI case.
_JUNIT_PACKAGE = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2">
<testcase classname="tests.hooks.test_beta" name="test_one" time="3.000" />
<testcase classname="tests.hooks.test_beta.TestGroup" name="test_two" time="2.000" />
</testsuite></testsuites>
"""

_JUNIT_WITH_DOCTYPE = """<?xml version="1.0"?>
<!DOCTYPE testsuites [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<testsuites><testsuite name="pytest"><testcase classname="t" name="a" time="1"/>
</testsuite></testsuites>
"""


def _telemetry_file(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    path = tmp_path / "telemetry.json"
    path.write_text(
        json.dumps({"schema": 1, "records": records}), encoding="utf-8"
    )
    return path


class TestNodeIdParsing:
    def test_module_of_strips_the_test_selector(self) -> None:
        assert report.module_of("tests/test_x.py::TestY::test_z") == "tests/test_x.py"

    def test_module_of_passes_through_a_bare_path(self) -> None:
        assert report.module_of("tests/test_x.py") == "tests/test_x.py"

    def test_junit_nodeid_for_a_module_level_function(self) -> None:
        assert (
            report.junit_nodeid("tests.test_alpha", "test_one")
            == "tests/test_alpha.py::test_one"
        )

    def test_junit_nodeid_keeps_the_class_segment(self) -> None:
        assert (
            report.junit_nodeid("tests.test_alpha.TestGroup", "test_two")
            == "tests/test_alpha.py::TestGroup::test_two"
        )

    def test_junit_nodeid_for_a_module_inside_a_package(self) -> None:
        """The package directory is part of the path, never a class segment."""
        assert (
            report.junit_nodeid("tests.hooks.test_beta", "test_one")
            == "tests/hooks/test_beta.py::test_one"
        )

    def test_junit_nodeid_for_a_class_inside_a_package(self) -> None:
        assert (
            report.junit_nodeid("tests.skills.github.test_beta.TestGroup", "test_two")
            == "tests/skills/github/test_beta.py::TestGroup::test_two"
        )

    def test_junit_nodeid_without_a_classname_is_the_bare_name(self) -> None:
        """Edge: pytest emits an empty classname for a collection-level entry."""
        assert report.junit_nodeid("", "test_solo") == "test_solo"

    def test_junit_nodeid_falls_back_to_the_class_naming_convention(self) -> None:
        """Edge: no part names a test file, so the capitalized part starts the classes."""
        assert (
            report.junit_nodeid("pkg.mod.TestGroup", "test_three")
            == "pkg/mod.py::TestGroup::test_three"
        )


class TestLoading:
    def test_load_junit_reads_durations(self, tmp_path: Path) -> None:
        path = tmp_path / "junit.xml"
        path.write_text(_JUNIT, encoding="utf-8")
        records = {r.nodeid: r for r in report.load_junit(path)}
        assert records["tests/test_alpha.py::test_one"].duration == pytest.approx(4.5)
        assert records[
            "tests/test_alpha.py::TestGroup::test_two"
        ].module == "tests/test_alpha.py"

    def test_load_junit_refuses_a_report_that_declares_an_entity(
        self, tmp_path: Path
    ) -> None:
        """Negative control for the XXE guard: a DOCTYPE must never be parsed."""
        path = tmp_path / "junit.xml"
        path.write_text(_JUNIT_WITH_DOCTYPE, encoding="utf-8")
        with pytest.raises(ValueError, match="DTD or entity"):
            report.load_junit(path)

    def test_load_telemetry_reads_counts(self, tmp_path: Path) -> None:
        path = _telemetry_file(
            tmp_path,
            [
                {
                    "nodeid": "tests/test_a.py::test_one",
                    "module": "tests/test_a.py",
                    "duration": 2.0,
                    "subprocesses": 3,
                    "traversals": 4,
                    "commands": ["git"],
                    "roots": [".claude/skills:**/*.py"],
                }
            ],
        )
        (record,) = report.load_telemetry(path)
        assert (record.subprocesses, record.traversals) == (3, 4)
        assert record.roots == [".claude/skills:**/*.py"]

    def test_load_telemetry_rejects_a_payload_without_records(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "telemetry.json"
        path.write_text(json.dumps({"schema": 1}), encoding="utf-8")
        with pytest.raises(ValueError, match="not a slow-report telemetry file"):
            report.load_telemetry(path)

    def test_load_inputs_merges_junit_duration_with_recorder_counts(
        self, tmp_path: Path
    ) -> None:
        """The CI path: JUnit supplies time, the recorder supplies telemetry."""
        junit = tmp_path / "junit.xml"
        junit.write_text(_JUNIT, encoding="utf-8")
        telemetry = _telemetry_file(
            tmp_path,
            [
                {
                    "nodeid": "tests/test_alpha.py::test_one",
                    "module": "tests/test_alpha.py",
                    "duration": 0.0,
                    "subprocesses": 5,
                    "traversals": 2,
                    "commands": ["semgrep"],
                    "roots": [],
                }
            ],
        )
        merged = report.load_inputs([junit, telemetry])
        record = merged["tests/test_alpha.py::test_one"]
        assert record.duration == pytest.approx(4.5)
        assert record.subprocesses == 5
        assert record.commands == ["semgrep"]

    def test_load_inputs_merges_a_package_module_into_one_record(
        self, tmp_path: Path
    ) -> None:
        """A mismatched key doubled the record count and the recorded seconds.

        Two rows for one test also strand the process and traversal counts on a
        node id that no module group can name.
        """
        junit = tmp_path / "junit.xml"
        junit.write_text(_JUNIT_PACKAGE, encoding="utf-8")
        telemetry = _telemetry_file(
            tmp_path,
            [
                {
                    "nodeid": "tests/hooks/test_beta.py::test_one",
                    "module": "tests/hooks/test_beta.py",
                    "duration": 0.0,
                    "subprocesses": 7,
                    "traversals": 1,
                    "commands": ["git"],
                    "roots": [],
                },
                {
                    "nodeid": "tests/hooks/test_beta.py::TestGroup::test_two",
                    "module": "tests/hooks/test_beta.py",
                    "duration": 0.0,
                    "subprocesses": 0,
                    "traversals": 4,
                    "commands": [],
                    "roots": [".claude/skills:**/*.py"],
                },
            ],
        )
        merged = report.load_inputs([junit, telemetry])
        assert sorted(merged) == [
            "tests/hooks/test_beta.py::TestGroup::test_two",
            "tests/hooks/test_beta.py::test_one",
        ]
        (group,) = report.group_by_module(merged.values(), min_seconds=5.0)
        assert group.module == "tests/hooks/test_beta.py"
        assert group.seconds == pytest.approx(5.0)
        assert (group.subprocesses, group.traversals) == (7, 5)

    def test_load_inputs_raises_for_a_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            report.load_inputs([tmp_path / "absent.json"])


class TestGrouping:
    def _records(self) -> list[report.TestRecord]:
        return [
            report.TestRecord(
                "tests/test_a.py::test_slow",
                "tests/test_a.py",
                duration=9.0,
                subprocesses=2,
                traversals=3,
                commands=["git"],
            ),
            report.TestRecord(
                "tests/test_a.py::test_fast", "tests/test_a.py", duration=0.5
            ),
            report.TestRecord(
                "tests/test_b.py::test_mid", "tests/test_b.py", duration=6.0
            ),
        ]

    def test_groups_rank_by_total_seconds(self) -> None:
        groups = report.group_by_module(self._records(), min_seconds=5.0)
        assert [g.module for g in groups] == ["tests/test_a.py", "tests/test_b.py"]
        assert groups[0].seconds == pytest.approx(9.5)
        assert groups[0].tests == 2

    def test_only_items_at_or_above_the_threshold_count_as_slow(self) -> None:
        groups = report.group_by_module(self._records(), min_seconds=5.0)
        assert groups[0].slow_tests == 1
        assert groups[0].subprocesses == 2
        assert groups[0].traversals == 3

    def test_a_threshold_below_every_duration_marks_everything_slow(self) -> None:
        """Edge: a zero threshold must not silently exclude a zero-second test."""
        groups = report.group_by_module(self._records(), min_seconds=0.0)
        assert sum(g.slow_tests for g in groups) == 3

    def test_scanner_labels_reach_the_group(self) -> None:
        groups = report.group_by_module(self._records(), min_seconds=5.0)
        assert groups[0].scanners == {"git"}

    def test_report_text_names_the_module_and_the_slow_item(self) -> None:
        built = report.build_report(
            {r.nodeid: r for r in self._records()}, min_seconds=5.0, top=10
        )
        assert "tests/test_a.py" in built["text"]
        assert "tests/test_a.py::test_slow" in built["text"]
        assert built["total_seconds"] == pytest.approx(15.5)


class TestMainExitCodes:
    def test_a_readable_report_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        junit = tmp_path / "junit.xml"
        junit.write_text(_JUNIT, encoding="utf-8")
        assert report.main([str(junit)]) == 0
        assert "tests/test_alpha.py" in capsys.readouterr().out

    def test_json_output_is_parseable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        junit = tmp_path / "junit.xml"
        junit.write_text(_JUNIT, encoding="utf-8")
        assert report.main([str(junit), "--output-format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["modules"][0]["module"] == "tests/test_alpha.py"

    def test_an_empty_input_exits_one(self, tmp_path: Path) -> None:
        """No records is a logic error, not a silent success."""
        path = _telemetry_file(tmp_path, [])
        assert report.main([str(path)]) == 1

    def test_a_negative_threshold_exits_two(self, tmp_path: Path) -> None:
        path = _telemetry_file(tmp_path, [])
        assert report.main([str(path), "--min-seconds", "-1"]) == 2

    def test_a_zero_top_exits_two(self, tmp_path: Path) -> None:
        path = _telemetry_file(tmp_path, [])
        assert report.main([str(path), "--top", "0"]) == 2

    def test_a_malformed_payload_exits_two(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.json"
        path.write_text(json.dumps({"schema": 1}), encoding="utf-8")
        assert report.main([str(path)]) == 2

    def test_a_missing_input_exits_three(self, tmp_path: Path) -> None:
        assert report.main([str(tmp_path / "absent.json")]) == 3

    def test_unparseable_xml_exits_three(self, tmp_path: Path) -> None:
        path = tmp_path / "junit.xml"
        path.write_text("<testsuites>", encoding="utf-8")
        assert report.main([str(path)]) == 3


class TestProbes:
    def test_probes_count_a_subprocess_and_a_traversal(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        report.install_probes()
        counters = report._Telemetry()
        monkeypatch.setattr(report, "_active", counters)
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        list(tmp_path.rglob("*.py"))
        subprocess.run(
            [sys.executable, "-c", "pass"], check=True, capture_output=True
        )
        assert counters.traversals >= 1
        assert counters.subprocesses == 1
        assert "python" in " ".join(counters.commands).lower()

    def test_probes_record_nothing_when_no_item_is_active(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Negative control: work outside a test item must not be attributed."""
        report.install_probes()
        counters = report._Telemetry()
        monkeypatch.setattr(report, "_active", None)
        list(tmp_path.rglob("*.py"))
        assert (counters.subprocesses, counters.traversals) == (0, 0)

    def test_label_capping_bounds_the_stored_names(self) -> None:
        """Edge: a test that spawns many processes stores its count, not a list."""
        counters = report._Telemetry()
        for index in range(report._MAX_LABELS + 5):
            counters.note_subprocess([f"tool{index}"])
        assert counters.subprocesses == report._MAX_LABELS + 5
        assert len(counters.commands) == report._MAX_LABELS

    def test_temp_dir_traversals_collapse_to_one_label(self, tmp_path: Path) -> None:
        """Every pytest tmp_path is unique, so literal roots would bury the signal."""
        counters = report._Telemetry()
        for index in range(5):
            counters.note_traversal(tmp_path / f"case{index}", "**/*.py")
        counters.note_traversal(Path("/repo/.claude/skills"), "**/*.py")
        assert counters.traversals == 6
        assert counters.roots == {"<tmp>", "/repo/.claude/skills:**/*.py"}

    def test_group_scanner_labels_are_bounded(self) -> None:
        """Edge: a module with hundreds of distinct roots must stay readable."""
        records = [
            report.TestRecord(
                f"tests/test_a.py::test_{i}", "tests/test_a.py", commands=[f"tool{i}"]
            )
            for i in range(report._MAX_GROUP_LABELS + 20)
        ]
        (group,) = report.group_by_module(records, min_seconds=5.0)
        assert len(group.scanners) <= report._MAX_GROUP_LABELS

    def test_worker_suffix_keeps_xdist_writes_apart(self) -> None:
        assert report._worker_suffixed(Path("out.json"), "gw3") == Path("out.gw3.json")
        assert report._worker_suffixed(Path("out.json"), None) == Path("out.json")


class TestPluginEndToEnd:
    """The recorder must work in a real pytest process, not only in unit calls."""

    _GENERATED = (
        "import subprocess, sys\n"
        "from pathlib import Path\n"
        "def test_walks_and_spawns(tmp_path):\n"
        "    (tmp_path / 'a.py').write_text('x = 1\\n', encoding='utf-8')\n"
        "    assert list(tmp_path.rglob('*.py'))\n"
        "    subprocess.run([sys.executable, '-c', 'pass'], check=True)\n"
    )

    def _run(self, tmp_path: Path, extra: list[str]) -> subprocess.CompletedProcess[str]:
        target = tmp_path / "test_generated.py"
        target.write_text(self._GENERATED, encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(target),
                "-p",
                "scripts.testing.slow_test_report",
                "-p",
                "no:cacheprovider",
                "-q",
                "--no-header",
                *extra,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            encoding="utf-8",
            check=False,
            timeout=180,
        )

    def test_plugin_records_the_work_the_test_actually_did(
        self, tmp_path: Path
    ) -> None:
        destination = tmp_path / "telemetry.json"
        result = self._run(tmp_path, [f"--slow-report={destination}"])
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(destination.read_text(encoding="utf-8"))
        (record,) = payload["records"]
        assert record["nodeid"].endswith("::test_walks_and_spawns")
        assert record["subprocesses"] == 1
        assert record["traversals"] >= 1
        assert record["duration"] > 0

    def test_plugin_writes_nothing_without_the_flag(self, tmp_path: Path) -> None:
        """Negative control: the recorder is opt-in and inert by default."""
        destination = tmp_path / "telemetry.json"
        result = self._run(tmp_path, [])
        assert result.returncode == 0, result.stdout + result.stderr
        assert not destination.exists()
