"""Publish, report, and CLI tests for the metric artifact contract (#5639)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.metrics import metric_artifact_io
from scripts.metrics.metric_artifact import main, validate_artifact
from scripts.metrics.metric_artifact_io import SymlinkRefusedError, failure_path, publish_artifact
from scripts.metrics.metric_artifact_report import check_combinable, report_line
from tests.metrics.metric_artifact_helpers import (
    NOW,
    flow_payload,
    nested,
    rate_payload,
    stock_payload,
    with_changes,
)


def _blocked() -> dict:
    payload = nested(
        stock_payload(),
        "pagination",
        complete=False,
        pages_fetched=300,
        failed_page=301,
        failure="HTTP 502 on page 301",
    )
    payload.update(numerator=None, status="BLOCKED", limitations=["page 301 failed"])
    payload["counts"].update(raw=0, derived=0)
    return payload


class TestPublish:
    def test_pass_replaces_the_artifact_atomically(self, tmp_path: Path) -> None:
        path = tmp_path / "open_issues.json"

        result = publish_artifact(path, stock_payload(), now=NOW)

        assert result.written == path
        assert json.loads(path.read_text(encoding="utf-8")) == stock_payload()
        assert sorted(p.name for p in tmp_path.iterdir()) == ["open_issues.json"]

    def test_warn_is_published(self, tmp_path: Path) -> None:
        path = tmp_path / "m.json"
        payload = nested(stock_payload(), "counts", raw=13, null=1)

        result = publish_artifact(path, payload, now=NOW)

        assert result.validation.status == "WARN"
        assert path.exists()

    def test_blocked_run_keeps_the_last_valid_result(self, tmp_path: Path) -> None:
        path = tmp_path / "open_issues.json"
        publish_artifact(path, stock_payload(), now=NOW)
        before = path.read_bytes()

        result = publish_artifact(path, _blocked(), now=NOW)

        assert path.read_bytes() == before
        assert result.written == failure_path(path)
        record = json.loads(result.written.read_text(encoding="utf-8"))
        assert record["validation"]["status"] == "BLOCKED"
        assert record["payload"]["pagination"]["failed_page"] == 301
        assert "retrieval is incomplete" in json.dumps(record["validation"]["findings"])

    def test_invalid_run_keeps_the_last_valid_result(self, tmp_path: Path) -> None:
        path = tmp_path / "open_issues.json"
        publish_artifact(path, stock_payload(), now=NOW)
        before = path.read_bytes()

        result = publish_artifact(path, with_changes(stock_payload(), retrieved_at=None), now=NOW)

        assert path.read_bytes() == before
        assert result.validation.status == "INVALID"
        assert result.written.name == "open_issues.failed.json"

    def test_rejected_first_run_writes_only_the_failure_record(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "m.json"

        publish_artifact(path, None, now=NOW)

        assert not path.exists()
        assert json.loads(failure_path(path).read_text(encoding="utf-8"))["payload"] is None

    def test_symlink_destination_is_refused(self, tmp_path: Path) -> None:
        target = tmp_path / "elsewhere.json"
        target.write_text("keep", encoding="utf-8")
        path = tmp_path / "m.json"
        path.symlink_to(target)

        with pytest.raises(SymlinkRefusedError):
            publish_artifact(path, stock_payload(), now=NOW)

        assert target.read_text(encoding="utf-8") == "keep"

    def test_failed_write_removes_the_temp_file_and_keeps_the_old_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "m.json"
        publish_artifact(path, stock_payload(), now=NOW)
        before = path.read_bytes()

        def boom(src: str, dst: Path) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(metric_artifact_io.os, "replace", boom)

        with pytest.raises(OSError, match="disk full"):
            publish_artifact(path, flow_payload(), now=NOW)

        assert path.read_bytes() == before
        assert sorted(p.name for p in tmp_path.iterdir()) == ["m.json"]


class TestReportLine:
    def _line(self, payload) -> str:
        return report_line(payload, validate_artifact(payload, now=NOW))

    def test_pass_prints_the_number(self) -> None:
        assert self._line(stock_payload()) == "open_issues: 12"

    def test_rate_prints_numerator_over_denominator(self) -> None:
        assert self._line(rate_payload()) == "close_rate_30d: 8/40"

    def test_warn_is_labeled_provisional(self) -> None:
        payload = with_changes(stock_payload(), limitations=["bot issues excluded"])
        payload["counts"].update(raw=13, null=1)

        line = self._line(payload)

        assert line.startswith("[PROVISIONAL] open_issues: 12 (bot issues excluded; ")
        assert "counts.null" in line

    def test_blocked_prints_no_number(self) -> None:
        line = self._line(_blocked())

        assert line.startswith("[BLOCKED] open_issues: withheld (")
        assert "12" not in line

    def test_invalid_prints_no_number_even_when_the_payload_has_one(self) -> None:
        line = self._line(with_changes(stock_payload(), retrieved_at=None))

        assert line.startswith("[INVALID] open_issues: withheld (retrieved_at")
        assert "12" not in line

    def test_non_object_payload_reports_unknown_metric(self) -> None:
        assert self._line(None).startswith("[INVALID] unknown: withheld")


class TestCheckCombinable:
    def test_matching_artifacts_combine(self) -> None:
        assert check_combinable([stock_payload(), stock_payload()]) == []

    def test_mixed_units_need_a_declaration(self) -> None:
        findings = check_combinable([stock_payload(), with_changes(stock_payload(), unit="prs")])

        assert [f.field for f in findings] == ["unit"]
        assert findings[0].status == "INVALID"

    def test_declared_scope_allows_the_mix(self) -> None:
        mixed = [stock_payload(), with_changes(stock_payload(), unit="prs")]

        assert check_combinable(mixed, declared_scope="issues and PRs shown side by side") == []

    def test_blank_declaration_does_not_count(self) -> None:
        mixed = [stock_payload(), with_changes(stock_payload(), unit="prs")]

        assert check_combinable(mixed, declared_scope="   ") != []

    def test_incompatible_windows_and_revisions_are_flagged(self) -> None:
        other = nested(flow_payload(), "window", start="2026-08-01T00:00:00Z")
        other["source_revision"] = "b" * 40

        fields = {f.field for f in check_combinable([flow_payload(), other])}

        assert fields == {"window", "source_revision"}

    def test_non_object_window_is_compared_as_text(self) -> None:
        broken = with_changes(stock_payload(), window=None)

        assert [f.field for f in check_combinable([stock_payload(), broken])] == ["window"]


class TestCli:
    def _write(self, tmp_path: Path, payload) -> Path:
        path = tmp_path / "m.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _fresh(self) -> dict:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = now.isoformat().replace("+00:00", "Z")
        payload = stock_payload()
        payload["retrieved_at"] = stamp
        payload["window"]["end"] = stamp
        return payload

    def test_pass_exits_zero(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code = main([str(self._write(tmp_path, self._fresh()))])

        assert code == 0
        assert capsys.readouterr().out.strip() == "PASS"

    def test_rejected_artifact_exits_one_and_prints_findings(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main([str(self._write(tmp_path, with_changes(self._fresh(), retrieved_at=None)))])

        out = capsys.readouterr().out
        assert code == 1
        assert "INVALID retrieved_at:" in out

    @staticmethod
    def _pin_clock(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
        class PinnedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now

        monkeypatch.setattr("scripts.metrics.metric_artifact.datetime", PinnedDatetime)

    def test_max_age_hours_blocks_an_old_artifact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._pin_clock(monkeypatch, datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc))

        code = main([str(self._write(tmp_path, stock_payload())), "--max-age-hours", "1"])

        assert code == 1

    def test_max_age_hours_allows_a_recent_artifact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._pin_clock(monkeypatch, datetime(2026, 10, 12, 11, 30, tzinfo=timezone.utc))

        code = main([str(self._write(tmp_path, stock_payload())), "--max-age-hours", "1"])

        assert code == 0

    def test_missing_file_exits_two(self, tmp_path: Path) -> None:
        assert main([str(tmp_path / "absent.json")]) == 2

    def test_malformed_json_exits_two(self, tmp_path: Path) -> None:
        path = tmp_path / "m.json"
        path.write_text("{", encoding="utf-8")

        assert main([str(path)]) == 2


def test_failure_path_sits_beside_the_artifact() -> None:
    assert failure_path(Path("a") / "m.json") == Path("a") / "m.failed.json"


def test_publish_leaves_no_group_readable_artifact(tmp_path: Path) -> None:
    path = tmp_path / "m.json"

    publish_artifact(path, stock_payload(), now=NOW)

    assert os.stat(path).st_mode & 0o077 == 0


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_module_entry_point_exits_with_the_cli_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import runpy

    monkeypatch.setattr("sys.argv", ["metric_artifact", str(tmp_path / "absent.json")])

    with pytest.raises(SystemExit) as raised:
        runpy.run_module("scripts.metrics.metric_artifact", run_name="__main__")

    assert raised.value.code == 2
