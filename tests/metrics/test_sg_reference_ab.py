"""Tests for scripts/metrics/sg_reference_ab.py (#5856, REQ-8): orchestration
(run_fixture_mode/run_all) and the CLI.

Split out of the original monolithic test file under the taste-lints
file-size gate; fixture-builder tests live in
``test_sg_reference_ab_fixtures.py``, transport/plugin-contract/failure-
classification tests in ``test_sg_reference_ab_api.py``, tool-loop tests in
``test_sg_reference_ab_toolloop.py``, and aggregation tests in
``test_sg_reference_ab_aggregates.py``.

All network access is mocked: every test that reaches ``post_messages``
patches ``urllib.request.urlopen`` with a scripted fake transport, or stubs
``run_fixture_mode``/``post_messages`` directly. No test performs a live
Anthropic API call.
"""

from __future__ import annotations

import dataclasses
import json
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from scripts.metrics import sg_reference_ab as ab
from scripts.metrics import sg_reference_ab_fixtures as fixtures_mod
from tests.metrics.sg_reference_ab_helpers import (
    SCHEMA,
    make_fake_urlopen,
    report_findings_response,
    tool_use_response,
    write_stub_plugin,
)

# ---------------------------------------------------------------------------
# run_fixture_mode / run_all
# ---------------------------------------------------------------------------


def test_run_fixture_mode_inline_records_prompt_and_classification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = fixtures_mod._build_f_repeat(tmp_path / "fixture")
    findings = [{"filePath": fixture.seeded_path, "category": "CWE-78", "severity": "high"}]
    fake, _calls = make_fake_urlopen([report_findings_response(findings)])
    monkeypatch.setattr(urllib.request, "urlopen", fake)

    result = ab.run_fixture_mode(
        fixture=fixture,
        mode="inline",
        run_index=0,
        api_key="key",
        model="model",
        system="system prompt",
        findings_schema=SCHEMA,
        store_dir=tmp_path / "store",
    )

    assert result.mode == "inline"
    assert result.fixture == "f_repeat"
    assert result.prompt_bytes > 0
    assert result.seeded_detected is True
    assert result.preexisting_flagged is False
    assert result.findings == [(fixture.seeded_path, "CWE-78", "high")]
    assert result.failure is None
    assert result.failure_detail is None
    assert result.infra_failure is False


def test_run_fixture_mode_referenced_writes_artifact_and_can_be_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = fixtures_mod._build_f_repeat(tmp_path / "fixture")
    store_dir = tmp_path / "store"
    responses = [
        tool_use_response("read_diff_artifact", {"sha256": "placeholder"}),
        report_findings_response([]),
    ]

    # The sha256 the model asks for is only known after produce_prompt runs
    # inside run_fixture_mode, so the fake needs to read it back from the
    # request the harness actually sent rather than being scripted ahead of
    # time. Intercept post_messages instead of urlopen for this one case.
    calls: list[list[dict[str, Any]]] = []

    def _fake_post_messages(
        api_key: str,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        calls.append(messages)
        if len(calls) == 1:
            sha_tool = next(t for t in tools if t["name"] == "read_diff_artifact")
            assert sha_tool is not None
            return responses[0]
        return responses[1]

    monkeypatch.setattr(
        "scripts.metrics.sg_reference_ab_toolloop.post_messages", _fake_post_messages
    )

    result = ab.run_fixture_mode(
        fixture=fixture,
        mode="referenced",
        run_index=0,
        api_key="key",
        model="model",
        system="system prompt",
        findings_schema=SCHEMA,
        store_dir=store_dir,
    )

    assert result.mode == "referenced"
    assert len(list((store_dir / fixture.repo_id).glob("*.diff"))) == 1


def test_run_all_produces_one_row_per_fixture_mode_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixtures = [fixtures_mod._build_f_repeat(tmp_path / "fixture")]

    def _stub(**kwargs: Any) -> ab.RunResult:
        return _stub_run_result(kwargs["fixture"].name, kwargs["mode"], kwargs["run_index"])

    monkeypatch.setattr(ab, "run_fixture_mode", _stub)

    contract = ab.PluginContract(
        system="s",
        findings_schema=SCHEMA,
        review_api_sha256="a",
        llm_sha256="b",
        plugin_version="1",
    )
    rows = ab.run_all(fixtures, 2, "key", "model", contract, tmp_path / "store")

    assert len(rows) == 1 * 2 * 2  # 1 fixture x 2 modes x 2 runs
    assert {(r.mode, r.run_index) for r in rows} == {
        ("inline", 0),
        ("inline", 1),
        ("referenced", 0),
        ("referenced", 1),
    }


def _stub_run_result(
    fixture_name: str,
    mode: str,
    run_index: int,
    *,
    failure: str | None = None,
    failure_detail: str | None = None,
    infra_failure: bool = False,
) -> ab.RunResult:
    return ab.RunResult(
        fixture=fixture_name,
        mode=mode,
        run_index=run_index,
        prompt_bytes=10,
        usage_input_tokens=1,
        usage_cache_creation_tokens=0,
        usage_cache_read_tokens=0,
        usage_output_tokens=1,
        total_input_tokens=1,
        turns=1,
        latency_s=0.01,
        failure=failure,
        failure_detail=failure_detail,
        infra_failure=infra_failure,
        findings=[],
        read_diff_artifact_called=False,
        seeded_detected=False,
        preexisting_flagged=False,
    )


# ---------------------------------------------------------------------------
# CLI: argument parsing and fixture selection
# ---------------------------------------------------------------------------


def test_parse_args_reads_all_flags() -> None:
    args = ab._parse_args(
        [
            "--runs",
            "3",
            "--model",
            "m",
            "--output",
            "out.json",
            "--plugin-dir",
            "/tmp/p",
            "--fixtures",
            "f_repeat,f_paths",
        ]
    )

    assert args.runs == 3
    assert args.model == "m"
    assert args.output == Path("out.json")
    assert args.plugin_dir == Path("/tmp/p")
    assert args.fixtures == "f_repeat,f_paths"


def test_selected_fixture_names_default_is_all() -> None:
    assert ab._selected_fixture_names(None) == ab.FIXTURE_NAMES


def test_selected_fixture_names_subset() -> None:
    assert ab._selected_fixture_names("f_repeat, f_trunc") == ("f_repeat", "f_trunc")


def test_selected_fixture_names_rejects_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    assert ab._selected_fixture_names("f_repeat,bogus") is None
    assert "unknown fixture" in capsys.readouterr().err


def test_selected_fixture_names_rejects_empty_string(capsys: pytest.CaptureFixture[str]) -> None:
    assert ab._selected_fixture_names("") is None


# ---------------------------------------------------------------------------
# CLI: main() exit codes
# ---------------------------------------------------------------------------


def test_main_exits_config_when_runs_is_zero(tmp_path: Path) -> None:
    rc = ab.main(["--runs", "0", "--output", str(tmp_path / "out.json")])
    assert rc == ab.EXIT_CONFIG


def test_main_exits_config_when_no_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ab, "load_api_key", lambda repo_root: None)

    rc = ab.main(["--runs", "1", "--output", str(tmp_path / "out.json")])

    assert rc == ab.EXIT_CONFIG


def test_main_exits_config_on_missing_plugin_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ab, "load_api_key", lambda repo_root: "test-key")

    rc = ab.main(
        [
            "--runs",
            "1",
            "--output",
            str(tmp_path / "out.json"),
            "--plugin-dir",
            str(tmp_path / "no-such-plugin"),
        ]
    )

    assert rc == ab.EXIT_CONFIG
    assert not (tmp_path / "out.json").exists()


def test_main_exits_config_on_unknown_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ab, "load_api_key", lambda repo_root: "test-key")
    hooks_dir = write_stub_plugin(tmp_path)

    rc = ab.main(
        [
            "--runs",
            "1",
            "--output",
            str(tmp_path / "out.json"),
            "--plugin-dir",
            str(hooks_dir),
            "--fixtures",
            "not_a_real_fixture",
        ]
    )

    assert rc == ab.EXIT_CONFIG


def test_main_happy_path_writes_output_and_exits_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ab, "load_api_key", lambda repo_root: "test-key")
    hooks_dir = write_stub_plugin(tmp_path)
    output_path = tmp_path / "results" / "out.json"

    def _stub_run_fixture_mode(**kwargs: Any) -> ab.RunResult:
        return _stub_run_result(kwargs["fixture"].name, kwargs["mode"], kwargs["run_index"])

    monkeypatch.setattr(ab, "run_fixture_mode", _stub_run_fixture_mode)

    rc = ab.main(
        [
            "--runs",
            "1",
            "--output",
            str(output_path),
            "--plugin-dir",
            str(hooks_dir),
            "--fixtures",
            "f_repeat",
        ]
    )

    assert rc == ab.EXIT_OK
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(payload["runs"]) == 2  # 1 fixture x 2 modes x 1 run
    assert payload["provenance"]["plugin_version"] == "9.9.9"


def test_main_exits_external_when_every_run_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ab, "load_api_key", lambda repo_root: "test-key")
    hooks_dir = write_stub_plugin(tmp_path)
    output_path = tmp_path / "out.json"

    def _always_fails(**kwargs: Any) -> ab.RunResult:
        row = _stub_run_result(kwargs["fixture"].name, kwargs["mode"], kwargs["run_index"])
        return dataclasses.replace(row, failure="http_500")

    monkeypatch.setattr(ab, "run_fixture_mode", _always_fails)

    rc = ab.main(
        [
            "--runs",
            "1",
            "--output",
            str(output_path),
            "--plugin-dir",
            str(hooks_dir),
            "--fixtures",
            "f_repeat",
        ]
    )

    assert rc == ab.EXIT_EXTERNAL
    # Output is still written so a partial/total-failure run leaves evidence.
    assert output_path.exists()


def test_main_exits_external_with_infra_message_when_every_run_is_infra_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """REQ-8 support (#5856): the motivating live failure was every run
    hitting the same billing error, reported by the pre-Task-2 code only as
    the undifferentiated "every run failed". main() must still exit 3, but
    the stderr message must name the infrastructure cause and surface the
    failure_detail, not read the same as an ordinary review failure.
    """
    monkeypatch.setattr(ab, "load_api_key", lambda repo_root: "test-key")
    hooks_dir = write_stub_plugin(tmp_path)
    output_path = tmp_path / "out.json"

    def _always_infra_fails(**kwargs: Any) -> ab.RunResult:
        return _stub_run_result(
            kwargs["fixture"].name,
            kwargs["mode"],
            kwargs["run_index"],
            failure="http_400:invalid_request_error",
            failure_detail="Your credit balance is too low.",
            infra_failure=True,
        )

    monkeypatch.setattr(ab, "run_fixture_mode", _always_infra_fails)

    rc = ab.main(
        [
            "--runs",
            "1",
            "--output",
            str(output_path),
            "--plugin-dir",
            str(hooks_dir),
            "--fixtures",
            "f_repeat",
        ]
    )

    assert rc == ab.EXIT_EXTERNAL
    stderr = capsys.readouterr().err
    assert "infrastructure error" in stderr
    assert "Your credit balance is too low." in stderr


def test_main_builds_fixtures_for_a_config_error_on_git_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ab, "load_api_key", lambda repo_root: "test-key")
    hooks_dir = write_stub_plugin(tmp_path)

    def _boom(root: Path, names: Any) -> list[ab.Fixture]:
        raise OSError("simulated fixture build failure")

    monkeypatch.setattr(ab, "build_fixtures", _boom)

    rc = ab.main(
        [
            "--runs",
            "1",
            "--output",
            str(tmp_path / "out.json"),
            "--plugin-dir",
            str(hooks_dir),
        ]
    )

    assert rc == ab.EXIT_CONFIG


def test_repo_root_for_returns_repo_root_for_a_real_module_path() -> None:
    module = Path(ab.__file__)
    assert ab.repo_root_for(module) == module.resolve().parents[2]


def test_repo_root_for_refuses_a_symlinked_module_path(tmp_path: Path) -> None:
    link = tmp_path / "sg_reference_ab.py"
    link.symlink_to(Path(ab.__file__))
    assert ab.repo_root_for(link) is None


def test_main_exits_config_when_module_path_is_symlinked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ab, "repo_root_for", lambda _path: None)
    assert ab.main(["--runs", "1", "--output", str(tmp_path / "out.json")]) == 2
    assert "symlinked module path" in capsys.readouterr().err
