"""A --body-file body may quote a literal backslash-n (issue #6940).

The escaped-newline check steers an inline ``--body`` to ``--body-file``.
Applied to a file body, it refused a one-line reply that quoted a Python
bytes literal and then advised the flag the caller had already used.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from scripts.github_core import validation

# One line, a literal backslash-r-backslash-n inside inline code, no real
# line break: the shape the escaped-newline check refuses.
ONE_LINE_QUOTE = 'The payload is `b"HTTP/1.1 200 OK\\r\\nX-Slow: "` plus 200 bytes.'

_SCRIPTS = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts"


class _ReachedPastBodyCheckError(Exception):
    """Raised by the first call after the body check, so no API call runs."""


def _load(rel: str, alias: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(alias, _SCRIPTS / rel)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


class TestResolvedBodyError:
    def test_file_body_may_quote_a_backslash_n(self) -> None:
        assert validation.resolved_body_error(ONE_LINE_QUOTE, from_file=True) is None

    def test_inline_body_still_refuses_a_backslash_n(self) -> None:
        message = validation.resolved_body_error(ONE_LINE_QUOTE, from_file=False)
        assert message is not None and "literal backslash-n" in message

    @pytest.mark.parametrize("body", ["", "  \n\t ", None])
    @pytest.mark.parametrize("from_file", [True, False])
    def test_empty_body_is_refused_either_way(self, body: str | None, from_file: bool) -> None:
        assert validation.resolved_body_error(body, from_file=from_file) == "Body cannot be empty."

    def test_normal_body_passes_either_way(self) -> None:
        for from_file in (True, False):
            assert validation.resolved_body_error("## H\n\ntext\n", from_file=from_file) is None


# Each entry: script, the argv before the body flag, and the first name the
# script calls after the body check passes.
_SITES = [
    (
        "pr/add_pr_review_thread_reply.py",
        ["--thread-id", "PRRT_x"],
        "assert_gh_authenticated",
    ),
    ("pr/post_pr_comment_reply.py", ["--pull-request", "1"], "subprocess"),
    ("issue/post_issue_comment.py", ["--issue", "1"], "subprocess"),
]


def _run_to_body_check(
    rel: str, argv: list[str], after: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load(rel, f"_6940_{Path(rel).stem}")
    for name in ("assert_gh_authenticated", "resolve_repo_params"):
        if hasattr(module, name) and name != after:
            monkeypatch.setattr(module, name, lambda *a, **k: _repo())

    def stop(*_args: object, **_kwargs: object) -> None:
        raise _ReachedPastBodyCheckError

    if after == "subprocess":
        monkeypatch.setattr(module.subprocess, "run", stop)
    else:
        monkeypatch.setattr(module, after, stop)
    module.main(argv)


def _repo() -> object:
    from scripts.github_core.api import RepoInfo

    return RepoInfo(owner="o", repo="r")


@pytest.mark.parametrize(("rel", "argv", "after"), _SITES)
def test_a_one_line_file_body_passes_the_body_check(
    rel: str,
    argv: list[str],
    after: str,
    stub_git_probes: None,
    tmp_path_is_temp_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body_file = tmp_path_is_temp_root / "reply.md"
    body_file.write_text(ONE_LINE_QUOTE + "\n", encoding="utf-8")
    with pytest.raises(_ReachedPastBodyCheckError):
        _run_to_body_check(rel, [*argv, "--body-file", str(body_file)], after, monkeypatch)


@pytest.mark.parametrize(("rel", "argv", "after"), _SITES)
def test_the_same_text_inline_is_refused(
    rel: str, argv: list[str], after: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as exc:
        _run_to_body_check(rel, [*argv, "--body", ONE_LINE_QUOTE], after, monkeypatch)
    assert exc.value.code == 2
