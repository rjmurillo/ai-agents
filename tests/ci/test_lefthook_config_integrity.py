"""Whole-config invariants for ``lefthook.yml`` (issue #4634).

``lefthook.yml`` declared ``push-ref-staleness`` twice. Every existing test that
looks at a job reaches it through a name-keyed lookup:
``tests/test_lefthook_integration.py:_job_map`` builds
``{str(job["name"]): job for job in _flatten_jobs(jobs)}`` and
``tests/ci/test_lefthook_ratchet_wiring.py:_find_job`` returns on the first
match. A dict comprehension keeps the last copy, a first-match search keeps the
first, and neither can report that there were two. So the duplicate survived
while one copy silently checked nothing: it passed ``{remote}``, which lefthook
does not substitute, and ``git ls-remote "{remote}"`` resolves no SHA, which
``push_ref_staleness.py`` reads as a new branch and passes.

These tests ask questions about the config as a whole, which is the shape a
name-keyed lookup cannot express:

1. No hook declares the same job name twice, at any nesting depth.
2. No ``run`` body uses a token that looks like a lefthook placeholder but is
   not one.

The supported placeholder set below is probed from the pinned binary rather
than recalled. ``lefthook.yml`` pins ``min_version: 2.1.10``; against that
version a job with ``run: printf 'ARG1=[{1}] ARG2=[{2}] ALL=[{0}]\\n'``
substitutes the hook's positional arguments and leaves an unknown name such as
``{remote}`` verbatim. ``tests/test_lefthook_integration.py``
::test_pre_push_staleness_checks_the_remote_named_on_the_command_line exercises
that substitution end to end against the real config, so the string assertions
here are pinned by a runtime test rather than only by each other.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"

# Placeholders lefthook 2.1.10 substitutes. The four file templates are the
# complete set the pinned binary carries: `strings <lefthook> | grep -oE
# '\{[a-z_]*files\}'` yields {all_files}, {files}, {push_files}, {staged_files}
# and nothing else. `{cmd}` is the runner-command template, and `{0}` plus
# `{1}`..`{n}` are the hook's positional arguments, probed as described above.
_SUPPORTED_PLACEHOLDERS = frozenset(
    {"staged_files", "push_files", "all_files", "files", "cmd"}
)

# A brace token that is not a shell expansion. `$` excludes `${VAR}`, which the
# shell owns, not lefthook.
_PLACEHOLDER_TOKEN = re.compile(r"(?<!\$)\{([A-Za-z_][A-Za-z_0-9]*|\d+)\}")


def _load_config() -> dict[str, Any]:
    data = yaml.safe_load(_LEFTHOOK.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "lefthook.yml must parse to a YAML mapping."
    return data


def _hooks(config: dict[str, Any]) -> Iterator[tuple[str, list[Any]]]:
    """Yield (hook name, jobs) for every git hook the config declares."""
    for name, value in config.items():
        if isinstance(value, dict) and isinstance(value.get("jobs"), list):
            yield name, value["jobs"]


def _walk_jobs(jobs: list[Any]) -> Iterator[dict[str, Any]]:
    """Yield every job mapping, duplicates included, groups descended into.

    Unlike the name-keyed helpers this module was written to backstop, nothing
    here collapses or short-circuits on a repeated name. Groups are yielded as
    well as descended into, because ``lefthook run --job`` matches a group name
    the same way it matches a job name.
    """
    for job in jobs:
        if not isinstance(job, dict):
            continue
        yield job
        group = job.get("group")
        nested = group.get("jobs") if isinstance(group, dict) else job.get("jobs")
        if isinstance(nested, list):
            yield from _walk_jobs(nested)


def _duplicate_names(jobs: list[Any]) -> list[str]:
    """Return the names declared more than once, sorted."""
    counts = Counter(
        job["name"] for job in _walk_jobs(jobs) if isinstance(job.get("name"), str)
    )
    return sorted(name for name, count in counts.items() if count > 1)


def _unsupported_placeholders(command: str) -> list[str]:
    """Return brace tokens in a run body that lefthook will not substitute."""
    return sorted(
        {
            token
            for token in _PLACEHOLDER_TOKEN.findall(command)
            if not token.isdigit() and token not in _SUPPORTED_PLACEHOLDERS
        }
    )


def _run_bodies() -> Iterator[tuple[str, str, str]]:
    """Yield (hook, job name, run body) for every job that runs a command."""
    for hook, jobs in _hooks(_load_config()):
        for job in _walk_jobs(jobs):
            run = job.get("run")
            if isinstance(run, str):
                yield hook, str(job.get("name", "<unnamed>")), run


def _pre_push_job(name: str) -> dict[str, Any]:
    config = _load_config()
    matches = [
        job for job in _walk_jobs(config["pre-push"]["jobs"]) if job.get("name") == name
    ]
    assert matches, f"lefthook.yml declares no pre-push job named {name!r}."
    return matches[0]


class TestJobNamesAreUnique:
    """No hook may declare a job name twice (issue #4634, required fix 3)."""

    @pytest.mark.parametrize("hook", sorted(name for name, _ in _hooks(_load_config())))
    def test_hook_declares_each_job_name_once(self, hook: str) -> None:
        jobs = dict(_hooks(_load_config()))[hook]
        duplicates = _duplicate_names(jobs)
        assert duplicates == [], (
            f"lefthook.yml declares {duplicates} more than once under {hook!r}. "
            "Lefthook runs every copy, and each name-keyed test helper sees only "
            "one of them, so a copy that checks nothing can pass unnoticed "
            "(issue #4634). Delete the duplicate."
        )

    def test_detector_flags_a_top_level_duplicate(self) -> None:
        jobs = [
            {"name": "alpha", "run": "true"},
            {"name": "beta", "run": "true"},
            {"name": "alpha", "run": "true"},
        ]
        assert _duplicate_names(jobs) == ["alpha"]

    def test_detector_flags_a_duplicate_inside_a_group(self) -> None:
        # The shape lefthook.yml actually had: one copy at the top level and one
        # nested, which is why a flat scan of the top-level list missed it.
        jobs = [
            {"name": "alpha", "run": "true"},
            {"group": {"jobs": [{"name": "alpha", "run": "true"}]}},
        ]
        assert _duplicate_names(jobs) == ["alpha"]

    def test_detector_accepts_distinct_names_across_nesting(self) -> None:
        jobs = [
            {"name": "alpha", "run": "true"},
            {"group": {"jobs": [{"name": "beta", "run": "true"}]}},
        ]
        assert _duplicate_names(jobs) == []


class TestPushRefStalenessJob:
    """The reported job: declared once, reading the remote lefthook can supply."""

    def test_declared_exactly_once(self) -> None:
        names = [
            job.get("name")
            for job in _walk_jobs(_load_config()["pre-push"]["jobs"])
        ]
        assert names.count("push-ref-staleness") == 1

    def test_reads_the_remote_from_the_first_hook_argument(self) -> None:
        run = _pre_push_job("push-ref-staleness")["run"]
        assert '"{1}"' in run, (
            "The pre-push staleness check must take the remote from lefthook's "
            "first positional argument, which git sets to the pushed remote. "
            f"Found: {run!r}"
        )
        assert "{remote}" not in run, (
            "{remote} is not a lefthook placeholder; it reaches the script "
            "verbatim and the check silently passes (issue #4634)."
        )

    def test_reads_the_pushed_refs_from_stdin(self) -> None:
        assert _pre_push_job("push-ref-staleness")["use_stdin"] is True

    def test_runs_before_the_long_running_groups(self) -> None:
        # The check exists to abort before the 6-15 minute jobs, so its position
        # is load-bearing: the deleted duplicate sat after the piped group.
        jobs = _load_config()["pre-push"]["jobs"]
        index = next(
            position
            for position, job in enumerate(jobs)
            if job.get("name") == "push-ref-staleness"
        )
        first_group = next(
            position for position, job in enumerate(jobs) if "group" in job
        )
        assert index < first_group


class TestPlaceholderTokens:
    """No run body may use a brace token lefthook will not substitute."""

    def test_no_run_body_uses_an_unsupported_placeholder(self) -> None:
        offenders = [
            (hook, name, unsupported)
            for hook, name, run in _run_bodies()
            if (unsupported := _unsupported_placeholders(run))
        ]
        assert offenders == [], (
            f"Unsupported lefthook placeholders: {offenders}. Lefthook passes an "
            "unknown brace token through verbatim, so the command receives the "
            f"literal text. Supported: {sorted(_SUPPORTED_PLACEHOLDERS)} plus "
            "positional arguments such as {0} and {1}."
        )

    def test_detector_flags_the_reported_token(self) -> None:
        assert _unsupported_placeholders(
            "python check.py {remote}"
        ) == ["remote"]

    def test_detector_accepts_supported_tokens(self) -> None:
        command = 'lint {staged_files} {push_files} {all_files} {files} "{1}" {0} {cmd}'
        assert _unsupported_placeholders(command) == []

    def test_detector_ignores_shell_expansion(self) -> None:
        assert _unsupported_placeholders('echo "${HOME}" ${PATH}') == []
