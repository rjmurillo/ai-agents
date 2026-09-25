"""Tests for run_investigate_loop in scripts/metrics/sg_reference_ab_toolloop.py
(#5856, REQ-8 support).

Split out of ``tests/metrics/test_sg_reference_ab_toolloop.py`` under the
taste-lints file-size gate: that sibling file keeps the tool-confinement
(CWE-22) tests for ``_tool_read_file``/``_tool_grep``; this file covers the
tool loop itself. Transport and failure classification are tested in the
sibling ``tests/metrics/test_sg_reference_ab_api.py``.

All network access is mocked: every test here patches ``urllib.request.urlopen``
with a scripted fake transport. No test performs a live Anthropic API call.
"""

from __future__ import annotations

import http.client
import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from scripts.metrics import sg_diff_artifact as sgda
from scripts.metrics import sg_reference_ab_toolloop as toolloop
from tests.metrics.sg_reference_ab_helpers import (
    SCHEMA,
    http_error,
    make_fake_urlopen,
    report_findings_response,
    text_only_response,
    tool_use_response,
)

# ---------------------------------------------------------------------------
# run_investigate_loop: the tool loop
# ---------------------------------------------------------------------------


def test_run_investigate_loop_calls_report_findings_immediately(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    findings = [{"filePath": "a.py", "category": "CWE-78", "severity": "high"}]
    fake, calls = make_fake_urlopen([report_findings_response(findings)])
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.findings == findings
    assert result.turns == 1
    assert result.failure is None
    assert result.failure_detail is None
    assert result.infra_failure is False
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20
    assert len(calls) == 1


def test_run_investigate_loop_executes_read_file_then_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text("subprocess.run(x, shell=True)\n", encoding="utf-8")
    responses = [
        tool_use_response("read_file", {"path": "a.py"}),
        report_findings_response([{"filePath": "a.py", "category": "CWE-78", "severity": "high"}]),
    ]
    fake, calls = make_fake_urlopen(list(responses))
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.turns == 2
    assert len(result.findings) == 1
    assert len(calls) == 2
    # The tool result content actually carried the file's real bytes.
    second_call_messages = json.loads(calls[1].data.decode("utf-8"))["messages"]
    tool_result_content = second_call_messages[-1]["content"][0]["content"]
    assert "shell=True" in tool_result_content


def test_run_investigate_loop_executes_grep_then_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text("query = 'SELECT * FROM t WHERE x=' + y\n", encoding="utf-8")
    responses = [
        tool_use_response("grep", {"pattern": "SELECT", "path": "a.py"}),
        report_findings_response([]),
    ]
    fake, calls = make_fake_urlopen(list(responses))
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.turns == 2
    second_call_messages = json.loads(calls[1].data.decode("utf-8"))["messages"]
    tool_result_content = second_call_messages[-1]["content"][0]["content"]
    assert "a.py:1:" in tool_result_content


def test_run_investigate_loop_unknown_tool_name_reports_gracefully(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    responses = [
        tool_use_response("delete_everything", {}),
        report_findings_response([]),
    ]
    fake, calls = make_fake_urlopen(list(responses))
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.failure is None
    second_call_messages = json.loads(calls[1].data.decode("utf-8"))["messages"]
    tool_result_content = second_call_messages[-1]["content"][0]["content"]
    assert tool_result_content == "Unknown tool: delete_everything"


def test_run_investigate_loop_records_read_diff_artifact_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store_dir = tmp_path / "store"
    ref = sgda.write_artifact(store_dir, "a" * 64, "head1", "the real diff", ["f.py"], 0)
    responses = [
        tool_use_response("read_diff_artifact", {"sha256": ref.sha256}),
        report_findings_response([]),
    ]
    fake, _calls = make_fake_urlopen(list(responses))
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=store_dir,
        ref=ref,
        expected_repo_id="a" * 64,
        expected_head="head1",
        inline_diff_text="INLINE FALLBACK",
        findings_schema=SCHEMA,
    )

    assert result.read_diff_artifact_called is True
    assert result.findings == []


def test_run_investigate_loop_read_diff_artifact_unavailable_in_inline_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The model can still name the tool even when it wasn't offered (ref=None);
    the handler must respond gracefully rather than raising.
    """
    responses = [
        tool_use_response("read_diff_artifact", {"sha256": "a" * 64}),
        report_findings_response([]),
    ]
    fake, _calls = make_fake_urlopen(list(responses))
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.read_diff_artifact_called is False
    assert result.failure is None


def test_run_investigate_loop_fails_on_http_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake, _calls = make_fake_urlopen([http_error(400)])
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.failure == "http_400"
    assert result.failure_detail is None
    assert result.infra_failure is False
    assert result.findings == []


def test_run_investigate_loop_fails_on_infra_http_error_carries_classification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Wiring proof: run_investigate_loop's exception branch must route
    through sg_reference_ab_api.classify_failure, not a bare status string,
    so an infra failure (billing/auth) is distinguishable at this layer
    already, before it ever reaches RunResult/Aggregate in the orchestration
    module.
    """
    body = json.dumps(
        {
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Your credit balance is too low.",
            },
        }
    ).encode()
    fake, _calls = make_fake_urlopen([http_error(400, body)])
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.failure == "http_400:invalid_request_error"
    assert result.failure_detail == "Your credit balance is too low."
    assert result.infra_failure is True


def test_run_investigate_loop_fails_on_incomplete_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """response.read() inside sg_reference_ab_api._send_once can raise
    http.client.IncompleteRead (a connection dropped mid-body), which the
    prior except clause (HTTPError, URLError, TimeoutError) did not catch.
    An uncaught exception here would abort run_all for every remaining
    fixture/mode/run, discarding every already-completed row.
    """
    fake, _calls = make_fake_urlopen([http.client.IncompleteRead(b"")])
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.failure == "error_IncompleteRead"
    assert result.infra_failure is False
    assert result.findings == []


def test_run_investigate_loop_fails_on_non_json_200_body(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A 200 response whose body is not JSON makes json.loads raise
    ValueError (json.JSONDecodeError) inside _send_once. The prior except
    clause did not catch ValueError either.
    """

    class _RawBodyResponse:
        def __enter__(self) -> _RawBodyResponse:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def read(self) -> bytes:
            return b"not json"

    def _fake_urlopen(request: Any, timeout: float | None = None) -> _RawBodyResponse:
        return _RawBodyResponse()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.failure == "error_JSONDecodeError"
    assert result.infra_failure is False
    assert result.findings == []


def test_run_investigate_loop_fails_when_model_stops_without_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake, _calls = make_fake_urlopen([text_only_response()])
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.failure == "model_stopped_without_report"
    assert result.infra_failure is False


def test_run_investigate_loop_exhausts_max_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    responses: list[dict[str, Any] | Exception] = [
        tool_use_response("read_file", {"path": "a.py"}) for _ in range(toolloop.MAX_TURNS)
    ]
    fake, calls = make_fake_urlopen(responses)
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = toolloop.run_investigate_loop(
        api_key="key",
        model="model",
        system="system",
        prompt="prompt",
        fixture_dir=tmp_path,
        store_dir=tmp_path / "store",
        ref=None,
        expected_repo_id="r",
        expected_head="h",
        inline_diff_text="diff",
        findings_schema=SCHEMA,
    )

    assert result.turns == toolloop.MAX_TURNS
    assert result.failure == "max_turns_exceeded"
    assert result.infra_failure is False
    assert len(calls) == toolloop.MAX_TURNS
