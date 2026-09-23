"""Root-move exemption for whole-file content gates (issue #5420).

Issue #5420 moved agent write targets from ``.agents/<sub>`` to
``.project-toolkit/<sub>``. A file whose staged bytes equal its pre-image once
that root rename is undone carries no authored change, so the ADR debate gate
and the session schema gate skip it. Any other edit stays gated.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import git_hook_policy as policy

# Enough unchanged lines that git's 50% rename-similarity threshold pairs the
# source with the destination after the one-line reference rewrite.
ADR_BODY = (
    "# ADR-900\n\n"
    + "".join(f"Context line {n} stays the same.\n" for n in range(8))
    + "See `.agents/analysis/ADR-900-notes.md` for the debate.\n"
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout


def _repo_with(tmp_path: Path, relative_path: str, content: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "feature/test")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "user@example.com")
    _stage(repo, relative_path, content)
    _git(repo, "commit", "-qm", "seed")
    return repo


def _stage(repo: Path, relative_path: str, content: str) -> None:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))
    _git(repo, "add", "--", relative_path)


def _move(repo: Path, source: str, destination: str, content: str) -> None:
    (repo / destination).parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "mv", source, destination)
    _stage(repo, destination, content)


@pytest.fixture(autouse=True)
def _no_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy, "_merge_in_progress", lambda _root: False)


def test_pure_rename_is_exempt(tmp_path: Path) -> None:
    source = ".agents/architecture/ADR-900-x.md"
    destination = ".project-toolkit/architecture/ADR-900-x.md"
    repo = _repo_with(tmp_path, source, ADR_BODY)
    _move(repo, source, destination, ADR_BODY)

    assert policy._drop_root_move_only_paths([destination], repo) == []


def test_reference_rewrite_only_is_exempt(tmp_path: Path) -> None:
    source = ".agents/architecture/ADR-900-x.md"
    destination = ".project-toolkit/architecture/ADR-900-x.md"
    repo = _repo_with(tmp_path, source, ADR_BODY)
    _move(repo, source, destination, ADR_BODY.replace(".agents/", ".project-toolkit/"))

    assert policy.check_adr_review_policy([destination], repo) == 0


def test_authored_edit_after_move_stays_gated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = ".agents/architecture/ADR-900-x.md"
    destination = ".project-toolkit/architecture/ADR-900-x.md"
    repo = _repo_with(tmp_path, source, ADR_BODY)
    _move(repo, source, destination, ADR_BODY + "\nDecision changed.\n")

    assert policy.check_adr_review_policy([destination], repo) == 1
    assert "debate log" in capsys.readouterr().err


def test_in_place_edit_stays_gated(tmp_path: Path) -> None:
    path = ".project-toolkit/architecture/ADR-900-x.md"
    repo = _repo_with(tmp_path, path, ADR_BODY)
    _stage(repo, path, ADR_BODY + "\nNew consequence.\n")

    assert policy._drop_root_move_only_paths([path], repo) == [path]


def test_new_file_stays_gated(tmp_path: Path) -> None:
    repo = _repo_with(tmp_path, "README.md", "seed\n")
    path = ".project-toolkit/architecture/ADR-901-new.md"
    _stage(repo, path, ADR_BODY)

    assert policy._drop_root_move_only_paths([path], repo) == [path]


def test_moved_legacy_session_log_skips_schema_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ".agents/sessions/2025-01-01-session-1.json"
    destination = ".project-toolkit/sessions/2025-01-01-session-1.json"
    legacy = '{"workLog": {"not": "an array"}}\n'
    repo = _repo_with(tmp_path, source, legacy)
    _move(repo, source, destination, legacy)

    real_run_command = policy._run_command

    def _refuse_validator(
        args: list[str], cwd: Path, *rest: Any, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if "scripts/validate_session_json.py" in args:
            raise AssertionError("a moved legacy log must not be re-validated")
        return real_run_command(args, cwd, *rest, **kwargs)

    monkeypatch.setattr(policy, "_run_command", _refuse_validator)
    assert policy.check_sessions([destination], repo) == 0


def test_rename_query_failure_keeps_paths_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ".agents/architecture/ADR-900-x.md"
    destination = ".project-toolkit/architecture/ADR-900-x.md"
    repo = _repo_with(tmp_path, source, ADR_BODY)
    _move(repo, source, destination, ADR_BODY)
    failed = subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="boom")
    monkeypatch.setattr(policy, "_run_git", lambda *_args, **_kwargs: failed)

    assert policy._staged_rename_sources(repo) == {}
    assert policy._drop_root_move_only_paths([destination], repo) == [destination]


def test_relative_link_rebased_to_same_target_is_exempt(tmp_path: Path) -> None:
    source = ".agents/architecture/ADR-900-x.md"
    destination = ".project-toolkit/architecture/ADR-900-x.md"
    before = ADR_BODY + "See [plan](../archive/plan.md).\n"
    after = ADR_BODY.replace(".agents/", ".project-toolkit/")
    after += "See [plan](../../.agents/archive/plan.md).\n"
    repo = _repo_with(tmp_path, source, before)
    _move(repo, source, destination, after)

    assert policy.check_adr_review_policy([destination], repo) == 0


def test_relative_link_retargeted_stays_gated(tmp_path: Path) -> None:
    source = ".agents/architecture/ADR-900-x.md"
    destination = ".project-toolkit/architecture/ADR-900-x.md"
    before = ADR_BODY + "See [plan](../archive/plan.md).\n"
    after = ADR_BODY + "See [plan](../../.agents/archive/other.md).\n"
    repo = _repo_with(tmp_path, source, before)
    _move(repo, source, destination, after)

    assert policy._drop_root_move_only_paths([destination], repo) == [destination]


def test_moved_legacy_session_log_skips_episode_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ".agents/sessions/2025-12-28-session-critic-468-review.json"
    destination = ".project-toolkit/sessions/2025-12-28-session-critic-468-review.json"
    legacy = '{"workLog": []}\n'
    repo = _repo_with(tmp_path, source, legacy)
    _move(repo, source, destination, legacy)
    monkeypatch.setattr(policy, "check_generated_paths", lambda _kind, _root: 0)

    assert policy.extract_session_episodes([destination], repo) == 0


def test_new_session_log_with_legacy_name_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_with(tmp_path, "README.md", "seed\n")
    path = ".project-toolkit/sessions/2025-12-28-session-critic-468-review.json"
    _stage(repo, path, '{"workLog": []}\n')
    monkeypatch.setattr(policy, "check_generated_paths", lambda _kind, _root: 0)

    assert policy.extract_session_episodes([path], repo) == 2


def test_moved_session_on_upstream_under_former_path_is_upstream_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b'{"workLog": {}}\n'
    upstream = {".agents/sessions/2025-01-01-session-1.json": content}
    monkeypatch.setattr(
        policy, "_read_upstream_default_blob", lambda _root, path: upstream.get(path)
    )
    moved = ".project-toolkit/sessions/2025-01-01-session-1.json"

    assert policy._is_session_content_on_upstream_default(tmp_path, moved, content)
    assert not policy._is_session_content_on_upstream_default(tmp_path, moved, b"{}\n")
