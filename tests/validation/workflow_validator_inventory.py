"""Discover validators from workflows and from pre_pr by observation, not by name.

Two lists name the same validators and nothing joined them (issues #5670, #5676).
This module derives both sides so a test can compare them.

Workflow side: parse every ``.github/workflows/*.yml`` that runs on a pull
request, join shell line continuations, drop ``echo``/``printf`` commands and
comment lines, and collect the ``scripts/validation/<name>.py`` and
``scripts.validation.<name>`` tokens that remain. A remediation step that prints
a validator command as help text is not an invocation and must not count.

pre_pr side: run every gate in ``pre_pr_sequence._SEQUENCE`` with the process
spawners replaced by recorders, and a profile hook that notes each function
called from a file under ``scripts/validation/``. A validator counts as run when
a spawned argv names it or one of its functions executed. A name in a comment, a
docstring, or an import that is never called leaves no trace in either signal.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_SCRIPT_TOKEN = re.compile(r"scripts/validation/([A-Za-z0-9_]+)\.py")
_MODULE_TOKEN = re.compile(r"scripts\.validation\.([A-Za-z0-9_]+)")
_HELP_COMMANDS = ("echo", "printf", "#")
# ``git_hook_policy.py`` is a dispatcher: one file, many independent policies.
# Each subcommand is its own validator, so ``tracked-conflict-markers`` being
# gated says nothing about ``security-suppressions-diff``.
_DISPATCHER = "git_hook_policy"
_DISPATCH_TOKEN = re.compile(
    r"(?:scripts/validation/git_hook_policy\.py|scripts\.validation\.git_hook_policy)"
    r"\s+([a-z][a-z-]*)"
)


def validator_names(text: str) -> set[str]:
    """Return every validator named by a script path or a module path in ``text``.

    The dispatcher is reported per subcommand as ``git_hook_policy:<subcommand>``.
    """
    names = set(_SCRIPT_TOKEN.findall(text)) | set(_MODULE_TOKEN.findall(text))
    names.discard(_DISPATCHER)
    names |= {f"{_DISPATCHER}:{sub}" for sub in _DISPATCH_TOKEN.findall(text)}
    return names


def _logical_commands(script: str) -> list[str]:
    """Join backslash continuations so a multi-line ``echo`` stays one command."""
    joined = re.sub(r"\\\r?\n", " ", script)
    return [line.strip() for line in joined.splitlines() if line.strip()]


def invocations(script: str) -> list[str]:
    """Commands in a ``run:`` script that are not help text or comments."""
    return [
        command for command in _logical_commands(script) if not command.startswith(_HELP_COMMANDS)
    ]


def command_validators(script: str) -> set[str]:
    """Validators a ``run:`` script invokes, ignoring help text and comments."""
    found: set[str] = set()
    for command in invocations(script):
        found |= validator_names(command)
    return found


def _triggers(document: dict[Any, Any]) -> set[str]:
    """Event names in ``on:``. YAML 1.1 parses the bare key ``on`` as ``True``."""
    raw = document.get("on", document.get(True))
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {str(event) for event in raw}
    if isinstance(raw, dict):
        return {str(event) for event in raw}
    return set()


def runs_on_pull_request(document: dict[Any, Any]) -> bool:
    return bool(_triggers(document) & {"pull_request", "pull_request_target"})


def workflow_commands(workflows_dir: Path) -> list[tuple[str, str]]:
    """Every (workflow file, command) a pull-request workflow runs, help text excluded."""
    found: list[tuple[str, str]] = []
    for path in sorted(workflows_dir.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or not runs_on_pull_request(document):
            continue
        for job in (document.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                script = str(step.get("run", ""))
                found.extend((path.name, command) for command in invocations(script))
    return found


def workflow_validators(workflows_dir: Path) -> dict[str, set[str]]:
    """Map each validator a pull-request workflow runs to the workflows that run it."""
    found: dict[str, set[str]] = {}
    for workflow, command in workflow_commands(workflows_dir):
        for name in validator_names(command):
            found.setdefault(name, set()).add(workflow)
    return found


@dataclass
class Observed:
    """What one sweep of the gates ran, and which gate ran it."""

    by_validator: dict[str, set[str]] = field(default_factory=dict)
    argv: dict[str, list[str]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def note(self, validator: str, gate: str, argv: str = "") -> None:
        self.by_validator.setdefault(validator, set()).add(gate)
        if argv:
            self.argv.setdefault(validator, []).append(argv)


class _Completed(subprocess.CompletedProcess[str]):
    def __init__(self, argv: Any) -> None:
        super().__init__(argv, 0, "", "")


class _FakeProcess:
    returncode = 0

    def __init__(self, argv: Any, *_: Any, **__: Any) -> None:
        self.args = argv

    def communicate(self, *_: Any, **__: Any) -> tuple[str, str]:
        return "", ""

    def wait(self, *_: Any, **__: Any) -> int:
        return 0

    def poll(self) -> int:
        return 0

    def kill(self) -> None:
        return None

    def __enter__(self) -> _FakeProcess:
        return self

    def __exit__(self, *_: Any) -> None:
        return None


@contextmanager
def _spawn_recorder(spawned: list[Any]) -> Iterator[None]:
    """Replace every ``subprocess`` entry point with one that records and returns 0."""

    def run(argv: Any, *_: Any, **__: Any) -> subprocess.CompletedProcess[str]:
        spawned.append(argv)
        return _Completed(argv)

    def call(argv: Any, *_: Any, **__: Any) -> int:
        spawned.append(argv)
        return 0

    def check_output(argv: Any, *_: Any, **__: Any) -> str:
        spawned.append(argv)
        return ""

    class Popen(_FakeProcess):
        def __init__(self, argv: Any, *args: Any, **kwargs: Any) -> None:
            spawned.append(argv)
            super().__init__(argv, *args, **kwargs)

    replacements: dict[str, Any] = {
        "run": run,
        "call": call,
        "check_call": call,
        "check_output": check_output,
        "Popen": Popen,
    }
    saved = {name: getattr(subprocess, name) for name in replacements}
    for name, replacement in replacements.items():
        setattr(subprocess, name, replacement)
    try:
        yield
    finally:
        for name, original in saved.items():
            setattr(subprocess, name, original)


@contextmanager
def _call_recorder(validation_dir: Path, executed: set[str]) -> Iterator[None]:
    """Note the stem of every file under ``validation_dir`` that runs a function.

    A module body executes on import, so ``<module>`` frames are ignored. That is
    what keeps an import that nothing calls from counting as a run.
    """
    root = str(validation_dir.resolve())

    def profile(frame: Any, event: str, _arg: Any) -> None:
        if event != "call":
            return
        code = frame.f_code
        if code.co_name == "<module>" or not code.co_filename.startswith(root):
            return
        executed.add(Path(code.co_filename).stem)

    sys.setprofile(profile)
    threading.setprofile(profile)
    try:
        yield
    finally:
        sys.setprofile(None)
        threading.setprofile(None)


def _argv_text(argv: Any) -> str:
    if isinstance(argv, (list, tuple)):
        return " ".join(str(part) for part in argv)
    return str(argv)


def observe_gates(
    gates: list[tuple[str, Callable[[Path, argparse.Namespace], Any]]],
    repo_root: Path,
    args: argparse.Namespace,
    validation_dir: Path,
) -> Observed:
    """Run each gate under the recorders and attribute what ran to that gate."""
    observed = Observed()
    for name, run in gates:
        spawned: list[Any] = []
        executed: set[str] = set()
        with _spawn_recorder(spawned), _call_recorder(validation_dir, executed):
            try:
                run(repo_root, args)
            except BaseException as error:  # a gate may exit or raise
                observed.errors[name] = f"{type(error).__name__}: {error}"
        for validator in executed:
            observed.note(validator, name)
        for argv in spawned:
            text = _argv_text(argv)
            for validator in validator_names(text):
                observed.note(validator, name, text)
    return observed
