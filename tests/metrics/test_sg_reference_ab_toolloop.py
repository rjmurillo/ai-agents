"""Tests for scripts/metrics/sg_reference_ab_toolloop.py (#5856, REQ-8 support).

Tool-confined filesystem access (CWE-22) and the investigate tool loop built
on ``sg_reference_ab_api.post_messages``. Split out of
``tests/metrics/test_sg_reference_ab.py`` under the taste-lints file-size
gate; transport and failure classification are tested in the sibling
``tests/metrics/test_sg_reference_ab_api.py``.

All network access is mocked: every test that drives ``run_investigate_loop``
patches ``urllib.request.urlopen`` with a scripted fake transport. No test
performs a live Anthropic API call.
"""

from __future__ import annotations

import json
import os
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
# Tool confinement (CWE-22)
# ---------------------------------------------------------------------------


def test_tool_read_file_reads_relative_path_within_fixture(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("hello\n", encoding="utf-8")

    assert toolloop._tool_read_file(tmp_path, "a.py") == "hello\n"


def test_tool_read_file_rejects_absolute_path(tmp_path: Path) -> None:
    assert "rejected" in toolloop._tool_read_file(tmp_path, "/etc/passwd")


def test_tool_read_file_rejects_parent_traversal(tmp_path: Path) -> None:
    assert "rejected" in toolloop._tool_read_file(tmp_path, "../outside.txt")


def test_tool_read_file_reports_missing_file(tmp_path: Path) -> None:
    assert "not a file" in toolloop._tool_read_file(tmp_path, "missing.py")


def test_confine_path_rejects_a_symlink_that_resolves_outside_the_root(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (fixture_dir / "link.txt").symlink_to(outside)

    assert toolloop._confine_path(fixture_dir, "link.txt") is None


def test_tool_read_file_oserror_on_permission_denied(tmp_path: Path) -> None:
    target = tmp_path / "denied.py"
    target.write_text("secret", encoding="utf-8")
    os.chmod(target, 0)

    try:
        result = toolloop._tool_read_file(tmp_path, "denied.py")
    finally:
        os.chmod(target, 0o600)

    if os.geteuid() == 0:
        pytest.skip("running as root; chmod 0 does not deny root read access")
    assert "Error reading" in result


def test_tool_grep_finds_matches_with_path_and_line(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("line one\nvuln here\nline three\n", encoding="utf-8")

    result = toolloop._tool_grep(tmp_path, "vuln", None)

    assert result == "a.py:2:vuln here"


def test_tool_grep_scoped_to_one_path(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("vuln here\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("vuln here too\n", encoding="utf-8")

    result = toolloop._tool_grep(tmp_path, "vuln", "b.py")

    assert result == "b.py:1:vuln here too"


def test_tool_grep_no_matches(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("nothing interesting here\n", encoding="utf-8")

    result = toolloop._tool_grep(tmp_path, "absolutely_no_such_token_here", None)

    assert result == "No matches."


def test_tool_grep_rejects_invalid_pattern(tmp_path: Path) -> None:
    assert "invalid pattern" in toolloop._tool_grep(tmp_path, "(unclosed", None)


def test_tool_grep_rejects_absolute_scoped_path(tmp_path: Path) -> None:
    assert "rejected" in toolloop._tool_grep(tmp_path, "x", "/etc/passwd")


def test_tool_grep_requires_pattern(tmp_path: Path) -> None:
    assert "pattern is required" in toolloop._tool_grep(tmp_path, "", None)


def test_tool_grep_skips_directory_entries(tmp_path: Path) -> None:
    (tmp_path / "subdir").mkdir()
    (tmp_path / "a.py").write_text("needle\n", encoding="utf-8")

    result = toolloop._tool_grep(tmp_path, "needle", None)

    assert result == "a.py:1:needle"


def test_tool_grep_skips_unreadable_file(tmp_path: Path) -> None:
    denied = tmp_path / "denied.py"
    denied.write_text("needle\n", encoding="utf-8")
    (tmp_path / "readable.py").write_text("needle too\n", encoding="utf-8")
    os.chmod(denied, 0)

    try:
        result = toolloop._tool_grep(tmp_path, "needle", None)
    finally:
        os.chmod(denied, 0o600)

    if os.geteuid() == 0:
        pytest.skip("running as root; chmod 0 does not deny root read access")
    assert "readable.py:1:needle too" in result
    assert "denied.py" not in result


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
