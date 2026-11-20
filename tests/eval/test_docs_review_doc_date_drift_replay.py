"""Verify deterministic replay scoring and cleanup when a historical scan fails."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.eval import docs_review_doc_date_drift_replay as replay


def finding(line: int = 10) -> dict:
    return {
        "path": "docs/source.md",
        "line": line,
        "rule": "subject-drift",
        "other_path": "docs/page.md",
        "other_line": 20,
    }


def test_matching_requires_the_class_and_a_nearby_reported_location() -> None:
    expected = {"path": "docs/source.md", "line": 13, "rule": "subject-drift"}
    assert replay.matches(expected, finding())
    assert not replay.matches({**expected, "line": 14}, finding())
    assert not replay.matches({**expected, "rule": "header-pair"}, finding())
    assert replay.matches({**expected, "path": "docs/page.md", "line": 20}, finding())


def test_a_positive_needs_both_expected_locations_and_every_negative_warning_counts() -> None:
    cases: list[dict[str, Any]] = [
        {
            "id": "P",
            "kind": "positive",
            "scope": "automatic",
            "expected": [
                {"path": "docs/source.md", "line": 10, "rule": "subject-drift"},
                {"path": "docs/source.md", "line": 94, "rule": "subject-drift"},
            ],
        },
        {"id": "N", "kind": "negative", "scope": "automatic"},
    ]
    rows: list[dict[str, Any]] = [
        {"id": "P", "findings": [finding()]},
        {"id": "N", "findings": [finding()]},
    ]
    score = replay.score(cases, rows)
    assert score["caught"] == 0
    assert score["false_positives"] == 1
    assert not score["passed"]
    rows[0]["findings"].append(finding(94))
    rows[1]["findings"] = []
    assert replay.score(cases, rows)["passed"]


def test_manual_exclusion_requires_a_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        replay.score([{"id": "M", "kind": "positive", "scope": "manual"}], [])


def test_subprocess_env_strips_color_forcing(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[list[str], dict[Any, Any]]] = []

    def fake_run(args: list[str], **kwargs: object) -> object:
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert kwargs.get("shell") is False
        seen.append((list(args), env))
        return type("Done", (), {"returncode": 0, "stdout": "{}\n", "stderr": ""})()

    monkeypatch.setenv("GH_FORCE_TTY", "1")
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(replay, "_gh_accepts_color_never", lambda: True)
    assert replay.command(Path("."), ["gh", "pr", "view", "1", "--json", "baseRefOid"]) == "{}"
    args, env = seen[0]
    assert args[:2] == ["gh", "--color=never"]
    assert env["NO_COLOR"] == "1"
    assert env["GH_NO_COLOR"] == "1"
    assert "GH_FORCE_TTY" not in env
    assert "CLICOLOR_FORCE" not in env

    seen.clear()
    monkeypatch.setattr(replay, "_gh_accepts_color_never", lambda: False)
    replay.command(Path("."), ["git", "merge-base", "a", "b"])
    args, env = seen[0]
    assert args == ["git", "merge-base", "a", "b"]
    assert "GH_FORCE_TTY" not in env
    assert "CLICOLOR_FORCE" not in env


def test_scan_failure_removes_the_worktree_and_temporary_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    def command(_root: Path, args: list[str]) -> str:
        calls.append(args)
        return '{"baseRefOid": "' + ("b" * 40) + '"}' if args[0] == "gh" else "c" * 40

    monkeypatch.setattr(replay, "command", command)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("Known", (), {"returncode": 0})())
    monkeypatch.setattr(replay, "find_doc_date_drift", lambda *a: None)
    head = "a" * 40
    base = "b" * 40
    case = {"id": "P", "pr": 1, "sha": head, "baseRefOid": base}
    with pytest.raises(RuntimeError, match="historical tree"):
        replay.replay(tmp_path, "rjmurillo/ai-agents", case)
    assert any(args[:3] == ["git", "worktree", "remove"] for args in calls)
    assert calls[-1][:3] == ["git", "update-ref", "-d"]


@pytest.mark.parametrize(
    ("repository", "case", "match"),
    [
        ("rjmurillo/ai-agents", {"pr": 1, "sha": "HEAD", "baseRefOid": "b" * 40}, "sha"),
        (
            "rjmurillo/ai-agents",
            {"pr": "1;rm", "sha": "a" * 40, "baseRefOid": "b" * 40},
            "pull",
        ),
        (
            "owner name/repo",
            {"pr": 1, "sha": "a" * 40, "baseRefOid": "b" * 40},
            "repository",
        ),
        (
            "rjmurillo/ai-agents",
            {"pr": 1, "sha": "a" * 40, "baseRefOid": "--upload-pack=x"},
            "base",
        ),
    ],
)
def test_replay_rejects_refs_before_it_runs_a_command(
    repository: str, case: dict[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        replay.replay(Path("."), repository, case)


def test_main_maps_a_bad_corpus_to_exit_2(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.json"
    corpus.write_text('{"cases": []}', encoding="utf-8")
    assert replay.main(["--corpus", str(corpus)]) == 2


@pytest.mark.parametrize(
    "error",
    [RuntimeError("gh failed"), subprocess.TimeoutExpired(["git"], 1)],
)
def test_main_maps_external_failures_to_exit_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    corpus = tmp_path / "corpus.json"
    corpus.write_text(
        json.dumps(
            {
                "repository": "rjmurillo/ai-agents",
                "cases": [
                    {
                        "id": "N",
                        "kind": "negative",
                        "scope": "automatic",
                        "pr": 1,
                        "sha": "a" * 40,
                        "baseRefOid": "b" * 40,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fail(*_args: object, **_kwargs: object) -> str:
        raise error

    monkeypatch.setattr(replay, "command", fail)
    assert replay.main(["--corpus", str(corpus), "--output", str(tmp_path / "out.json")]) == 3


def test_contained_keeps_a_worktree_inside_its_parent(tmp_path: Path) -> None:
    parent = tmp_path / "worktrees"
    parent.mkdir()
    inside = parent / "doc-date-replay"
    inside.mkdir()
    assert replay._contained(inside, parent) == inside.resolve()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    link = parent / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("This platform cannot create a directory link.")
    with pytest.raises(ValueError, match="outside"):
        replay._contained(link, parent)
