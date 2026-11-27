"""prepare subcommand: run directory safety, option and store validation. Synthetic data only."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from replies_helpers import (
    BEFORE,
    CONTROL_TOKEN,
    plant_control,
    prepare_args,
    prepare_ok,
    replies_corpus,
    replies_prepare,
    replies_sample,
    run_cli,
    simple_session,
    user,
    write_session,
)

NARRATION = "synthetic narration before the tool call"
FINAL = "synthetic final answer after the tool boundary"


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "projects" / "proj-a"


def test_run_dir_is_private_and_stdout_holds_no_text(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(store, "main-a", simple_session("synthetic prompt wording xi", [FINAL], 10))
    plant_control(store)
    run_dir = tmp_path / "run"
    _, out = prepare_ok(capsys, store, run_dir)
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    for name in os.listdir(run_dir):
        assert stat.S_IMODE((run_dir / name).stat().st_mode) == 0o600
    for fragment in (FINAL, CONTROL_TOKEN, "synthetic prompt wording", "main-a", str(store)):
        assert fragment not in out


def test_run_dir_refusals(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    plant_control(store)
    existing = tmp_path / "exists"
    existing.mkdir()
    code, payload, _ = run_cli(capsys, prepare_args(store, existing))
    assert (code, payload["message"]) == (2, "run_dir_exists")
    code, payload, _ = run_cli(capsys, prepare_args(store, store / "run"))
    assert (code, payload["message"]) == (2, "run_dir_inside_source_or_repo")
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    code, payload, _ = run_cli(capsys, prepare_args(store, repo / "run"))
    assert (code, payload["message"]) == (2, "run_dir_inside_source_or_repo")
    code, payload, _ = run_cli(capsys, prepare_args(store, tmp_path / "missing-parent" / "run"))
    assert (code, payload["message"]) == (2, "run_dir_parent_missing")
    code, _, _ = run_cli(capsys, prepare_args(store, tmp_path / "fine"))
    assert code == 0


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--since", "not-a-time"], "bad_since"),
        (["--since", BEFORE], "since_not_before_before"),
        (["--limit", "0"], "bad_numeric_option"),
        (["--replay-min", "1"], "bad_numeric_option"),
        (["--marker", "("], "bad_marker"),
    ],
)
def test_option_validation(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], message: str
) -> None:
    plant_control(store)
    code, payload, _ = run_cli(capsys, prepare_args(store, tmp_path / "run", *extra))
    assert (code, payload["message"]) == (2, message)
    assert not (tmp_path / "run").exists()
    prepare_ok(capsys, store, tmp_path / "control-run")


def test_store_validation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "projects"
    plant_control(root / "proj-a")
    empty = tmp_path / "empty"
    empty.mkdir()
    cases = [
        (root, "store_looks_like_root"),
        (empty, "store_has_no_sessions"),
        (tmp_path / "nope", "store_not_a_directory"),
    ]
    for target, message in cases:
        code, payload, _ = run_cli(capsys, prepare_args(target, tmp_path / f"run-{message}"))
        assert (code, payload["message"]) == (2, message)
    prepare_ok(capsys, root / "proj-a", tmp_path / "control-run")


def test_bad_lines_symlinks_and_oversize_are_counted_not_read(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    plant_control(store)
    broken = write_session(
        store, "broken", simple_session("synthetic prompt wording omicron", ["reply"], 10)
    )
    broken.write_text(
        broken.read_text(encoding="utf-8") + '{"type": "user", broken\n', encoding="utf-8"
    )
    link = store / "linked.jsonl"
    try:
        link.symlink_to(broken)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    payload, _ = prepare_ok(capsys, store, tmp_path / "run")
    assert payload["population"]["parse_errors"] == 1
    assert payload["population"]["found"]["main"] == 2
    monkeypatch.setattr(replies_prepare, "MAX_FILE_BYTES", 10)
    code, payload, _ = run_cli(capsys, prepare_args(store, tmp_path / "run2"))
    assert (code, payload["message"]) == (2, "no_replies_in_population")


def test_empty_population_is_a_config_error_and_creates_nothing(
    store: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_session(store, "main-a", [user("synthetic prompt wording pi, no reply", 10)])
    code, payload, _ = run_cli(capsys, prepare_args(store, tmp_path / "run"))
    assert (code, payload["message"]) == (2, "no_replies_in_population")
    assert not (tmp_path / "run").exists()
    plant_control(store)
    prepare_ok(capsys, store, tmp_path / "control-run")


def test_run_dir_behind_a_symlinked_parent_is_refused_and_creates_nothing(
    store: Path, tmp_path: Path
) -> None:
    store.mkdir(parents=True)
    link = tmp_path / "alias"
    try:
        link.symlink_to(store, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(replies_corpus.ConfigError, match="run_dir_inside_source_or_repo"):
        replies_sample.make_run_dir(str(link / "run"), [store], tmp_path)
    assert list(store.iterdir()) == []


def test_inside_forbidden_checks_existing_ancestors_with_samefile(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    link = tmp_path / "alias"
    try:
        link.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert replies_sample._inside_forbidden(link / "run", [root]) is True
    assert replies_sample._inside_forbidden(root / "run", [root]) is True
    assert replies_sample._inside_forbidden(other / "run", [root]) is False
    assert replies_sample._inside_forbidden(other / "missing" / "deeper" / "run", [root]) is False
