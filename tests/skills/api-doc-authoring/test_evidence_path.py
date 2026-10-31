"""``--evidence`` must not follow a symlink or clobber an unrelated file (#6506)."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import api_examples as ax
import pytest
from api_fixtures import WORKED_EXAMPLE
from test_run import run_args


def _link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")


def _evidence_report() -> dict[str, object]:
    return {"verdict": "PASS", "doc_sha256": {}}


def test_symlink_at_the_evidence_path_is_refused_and_target_untouched(
    order_api: str, tmp_path: Path
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me\n", encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    _link(evidence, victim)

    with pytest.raises(ax.InputError, match="symlink or not a regular file"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))

    assert victim.read_text(encoding="utf-8") == "keep me\n"
    assert evidence.is_symlink()


def test_dangling_symlink_at_the_evidence_path_is_refused(order_api: str, tmp_path: Path) -> None:
    victim = tmp_path / "not-yet.txt"
    evidence = tmp_path / "evidence.json"
    _link(evidence, victim)

    with pytest.raises(ax.InputError, match="symlink or not a regular file"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))

    assert not victim.exists()


def test_existing_unrelated_file_is_not_overwritten(order_api: str, tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# docs\n", encoding="utf-8")

    with pytest.raises(ax.InputError, match="not a prior evidence report"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, readme))

    assert readme.read_text(encoding="utf-8") == "# docs\n"


def test_existing_json_without_evidence_keys_is_not_overwritten(
    order_api: str, tmp_path: Path
) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"name": "x"}\n', encoding="utf-8")

    with pytest.raises(ax.InputError, match="not a prior evidence report"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, config))

    assert json.loads(config.read_text(encoding="utf-8")) == {"name": "x"}


def test_directory_at_the_evidence_path_is_refused(order_api: str, tmp_path: Path) -> None:
    with pytest.raises(ax.InputError, match="symlink or not a regular file"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, tmp_path))


def test_prior_evidence_is_replaced_on_a_rerun(order_api: str, tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(_evidence_report()), encoding="utf-8")

    report, code = ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))

    assert code == ax.EXIT_OK
    saved = json.loads(evidence.read_text(encoding="utf-8"))
    assert saved["executed"] == report["executed"] == 4


def test_refused_evidence_path_fails_before_any_request_is_sent(tmp_path: Path) -> None:
    """The path check runs first, so no example reaches the server."""
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me\n", encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    _link(evidence, victim)
    sent: list[str] = []

    def spy(method: str, url: str, headers: dict[str, str], body: bytes) -> ax.Reply:
        sent.append(url)
        return ax.Reply(200, b"{}")

    with pytest.raises(ax.InputError):
        ax.cmd_run(run_args([WORKED_EXAMPLE], "http://127.0.0.1:9", evidence), spy)

    assert sent == []


def test_failed_examples_with_an_unwritable_evidence_path_are_unverifiable(
    changed_order_api: str, tmp_path: Path
) -> None:
    """A FAIL verdict that cannot be recorded exits 2, not 1, and leaves no partial file."""
    evidence = tmp_path / "missing-dir" / "evidence.json"

    with pytest.raises(ax.InputError, match="cannot write evidence"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], changed_order_api, evidence))

    assert not evidence.parent.exists()


def test_evidence_write_leaves_no_temp_file(order_api: str, tmp_path: Path) -> None:
    evidence = tmp_path / "out" / "evidence.json"
    evidence.parent.mkdir()

    ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))

    assert [p.name for p in evidence.parent.iterdir()] == ["evidence.json"]


def test_evidence_write_failure_is_unverifiable_input_not_a_traceback(
    order_api: str, tmp_path: Path
) -> None:
    evidence = tmp_path / "missing-dir" / "evidence.json"

    with pytest.raises(ax.InputError, match="cannot write evidence"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_evidence_file_is_world_readable_but_not_group_writable(
    order_api: str, tmp_path: Path
) -> None:
    evidence = tmp_path / "evidence.json"
    old_umask = os.umask(0o022)
    try:
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))
    finally:
        os.umask(old_umask)

    assert stat.S_IMODE(evidence.stat().st_mode) == 0o644


def test_cli_exits_2_with_unverified_json_for_a_refused_evidence_path(
    order_api: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me\n", encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    _link(evidence, victim)

    code = ax.main(
        ["run", str(WORKED_EXAMPLE), "--base-url", order_api, "--evidence", str(evidence)]
    )

    assert code == ax.EXIT_UNVERIFIABLE
    assert json.loads(capsys.readouterr().out)["verdict"] == "UNVERIFIED"
    assert victim.read_text(encoding="utf-8") == "keep me\n"


def test_failed_replace_removes_the_temp_file_and_leaves_prior_evidence(
    order_api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(_evidence_report()), encoding="utf-8")
    before = evidence.read_bytes()

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated swap failure")

    monkeypatch.setattr(ax.os, "replace", boom)

    with pytest.raises(ax.InputError, match="cannot write evidence"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, evidence))

    assert evidence.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["evidence.json"]


def test_oversized_existing_file_is_not_read_as_prior_evidence(
    order_api: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = tmp_path / "big.json"
    big.write_text(json.dumps(_evidence_report()), encoding="utf-8")
    monkeypatch.setattr(ax, "_MAX_EVIDENCE_BYTES", 5)

    with pytest.raises(ax.InputError, match="not a prior evidence report"):
        ax.cmd_run(run_args([WORKED_EXAMPLE], order_api, big))


def test_failed_open_does_not_unlink_a_path_it_never_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "evidence.json"
    bystander = tmp_path / "bystander.tmp"
    bystander.write_text("not mine\n", encoding="utf-8")
    monkeypatch.setattr(ax.os, "urandom", lambda _n: b"\x00" * 8)
    clash = tmp_path / f".{target.name}.{'00' * 8}.tmp"
    clash.write_text("pre-existing\n", encoding="utf-8")

    with pytest.raises(ax.InputError, match="cannot write evidence"):
        ax._write_evidence(target, _evidence_report())

    assert clash.read_text(encoding="utf-8") == "pre-existing\n"
    assert bystander.exists()
    assert not target.exists()


def test_run_evidence_help_names_the_refusals() -> None:
    sub = next(a for a in ax.build_parser()._actions if a.dest == "command")
    help_text = " ".join(sub.choices["run"].format_help().split())
    assert "refuses a symlink" in help_text
    assert "outside the working directory" in help_text
    assert "not a prior report" in help_text
