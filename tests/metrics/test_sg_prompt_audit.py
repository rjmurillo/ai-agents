"""Tests for the scripts/metrics/sg_prompt_audit.py CLI (#5856, REQ-3):
exit codes, output shape, date-window flags, and the no-leak (content-free
output) guarantee.

Split out of the original monolithic ``test_sg_prompt_audit.py`` under the
taste-lints file-size gate; fixture prompt/transcript builders live in
``tests/metrics/sg_prompt_audit_helpers.py``.
"""

from __future__ import annotations

import dataclasses
import json
import runpy
import sys
from pathlib import Path

import pytest

from scripts.metrics import sg_prompt_audit as audit
from tests.metrics.sg_prompt_audit_helpers import (
    diff_text,
    investigate_prompt,
    successful_session,
    write_transcript,
)

# --- CLI ----------------------------------------------------------------------------


def test_main_exits_zero_and_writes_json_report(tmp_path: Path) -> None:
    diff = diff_text([("a.py", "+x\n")])
    session = successful_session(investigate_prompt(diff))
    write_transcript(tmp_path, "proj-a", "s1.jsonl", session)
    output_path = tmp_path / "report.json"

    rc = audit.main(["--projects-dir", str(tmp_path), "--output", str(output_path)])

    assert rc == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["sessions_examined"] == 1
    assert data["counts_by_kind"] == {"investigate": 1}


def test_main_prints_json_to_stdout_when_no_output_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    diff = diff_text([("a.py", "+x\n")])
    session = successful_session(investigate_prompt(diff))
    write_transcript(tmp_path, "proj-a", "s1.jsonl", session)

    rc = audit.main(["--projects-dir", str(tmp_path)])

    assert rc == 0
    captured = json.loads(capsys.readouterr().out)
    assert captured["sessions_examined"] == 1


def test_main_respects_top_flag(tmp_path: Path) -> None:
    big_diff = diff_text([("a.py", "+" + "x" * 50 + "\n")])
    small_diff = diff_text([("b.py", "+y\n")])
    big_session = successful_session(investigate_prompt(big_diff))
    small_session = successful_session(investigate_prompt(small_diff))
    for i in range(2):
        write_transcript(tmp_path, "proj-a", f"big{i}.jsonl", big_session)
    for i in range(2):
        write_transcript(tmp_path, "proj-a", f"small{i}.jsonl", small_session)
    output_path = tmp_path / "report.json"

    rc = audit.main(
        ["--projects-dir", str(tmp_path), "--top", "1", "--output", str(output_path)]
    )

    assert rc == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(data["repeated_diffs"]) == 1


def test_main_exits_two_when_projects_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert audit.main(["--projects-dir", str(missing)]) == 2


def test_main_exits_two_on_malformed_since_date(tmp_path: Path) -> None:
    assert audit.main(["--projects-dir", str(tmp_path), "--since", "banana"]) == 2


def test_main_exits_two_on_malformed_until_date(tmp_path: Path) -> None:
    assert audit.main(["--projects-dir", str(tmp_path), "--until", "2026/09/20"]) == 2


def test_main_filters_by_since_and_until(tmp_path: Path) -> None:
    diff = diff_text([("a.py", "+x\n")])
    write_transcript(
        tmp_path,
        "proj-a",
        "old.jsonl",
        successful_session(investigate_prompt(diff), ts_start="2026-01-01T00:00:00Z"),
    )
    write_transcript(
        tmp_path,
        "proj-a",
        "new.jsonl",
        successful_session(investigate_prompt(diff), ts_start="2026-09-20T00:00:00Z"),
    )
    output_path = tmp_path / "report.json"

    rc = audit.main(
        [
            "--projects-dir",
            str(tmp_path),
            "--since",
            "2026-09-01",
            "--until",
            "2026-09-30",
            "--output",
            str(output_path),
        ]
    )

    assert rc == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["sessions_examined"] == 1
    assert data["window"] == {"since": "2026-09-01", "until": "2026-09-30"}


# --- no-leak: content-free output ---------------------------------------------------


def test_report_json_never_contains_diff_or_prompt_content(tmp_path: Path) -> None:
    secret = "sk-DO-NOT-LEAK-9f8a7b6c5d4e3f2a1b0c"
    diff = diff_text([("a.py", f"+token = '{secret}'\n")])
    text = investigate_prompt(diff, checkout_note=True)
    write_transcript(tmp_path, "proj-a", "s1.jsonl", successful_session(text))

    report = audit.build_report(tmp_path, since=None, until=None, top=20)
    rendered = json.dumps(dataclasses.asdict(report))

    assert secret not in rendered
    assert "token = " not in rendered
    # Prove the audit actually processed the content, rather than silently
    # finding nothing: the diff's hash and byte count are present.
    assert report.sessions_examined == 1
    assert report.total_prompt_bytes == len(text.encode("utf-8"))


def test_module_puts_repo_root_on_sys_path_when_run_as_a_plain_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_file = Path(audit.__file__).resolve()
    repo_root = str(module_file.parents[2])
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != repo_root])

    runpy.run_path(str(module_file), run_name="__not_main__")

    assert sys.path[0] == repo_root
