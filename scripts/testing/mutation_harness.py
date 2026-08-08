"""Run targeted mutation batteries without silent no-op results.

Battery file format:

```json
{
  "command": ["uv", "run", "pytest", "tests/test_example.py", "-x"],
  "entries": [
    {
      "name": "example-guard",
      "path": "scripts/example.py",
      "old": "raise ValueError(message)",
      "new": "return None"
    }
  ]
}
```

Each entry may override ``command`` and ``timeout_seconds``. A mutation is
``CAUGHT`` when the command fails, because the test suite detected the mutant.
It is ``MISSED`` when the command succeeds, because the mutant survived.

Exit codes:
    0 - Success: all mutations were caught
    1 - Logic error: one or more mutations were missed
    2 - Config error: battery JSON, entry shape, or source anchors are invalid
    3 - External error: source or process I/O failed
    130 - Script-specific interrupt: source was restored after Ctrl-C
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from scripts.testing.mutation_workspace import (
    isolated_mutation_worktree,
    tracked_repository_path,
)

EXIT_OK = 0
EXIT_MUTATION_MISSED = 1
EXIT_CONFIG_ERROR = 2
EXIT_EXTERNAL_ERROR = 3
EXIT_INTERRUPTED = 130
DEFAULT_COMMAND_TIMEOUT_SECONDS = 300
GIT_ROOT_TIMEOUT_SECONDS = 10


class BatteryConfigError(ValueError):
    """Raised when a battery can produce a false result."""


class MutationTimeoutError(RuntimeError):
    """Raised when a child command exceeds its time budget."""

    def __init__(self, command: Sequence[str], timeout_seconds: int | float) -> None:
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"command timed out after {timeout_seconds:g}s: {_format_command(command)}"
        )


@dataclass(frozen=True, slots=True)
class MutationEntry:
    """One targeted source edit and the command that must catch it."""

    name: str
    path: Path
    old: str
    new: str
    command: tuple[str, ...]
    timeout_seconds: int | float = DEFAULT_COMMAND_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class MutationResult:
    """Result for one mutation entry."""

    entry: MutationEntry
    returncode: int

    @property
    def caught(self) -> bool:
        return self.returncode != 0


@dataclass(frozen=True, slots=True)
class ValidationProblem:
    """Configuration problem found before the battery spends any runtime."""

    entry: MutationEntry
    message: str


def load_battery(path: Path) -> list[MutationEntry]:
    """Load mutation entries from a JSON battery file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BatteryConfigError(f"battery file is not valid JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise BatteryConfigError("battery root must be a JSON object")

    repo_root = _find_containment_root()
    default_command = _read_command(raw.get("command"), "battery command")
    default_timeout = _read_timeout(
        raw.get("timeout_seconds"),
        "battery timeout_seconds",
        default=DEFAULT_COMMAND_TIMEOUT_SECONDS,
    )
    if default_timeout is None:
        raise AssertionError("default timeout is required")
    raw_entries = raw.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise BatteryConfigError("battery must contain a non-empty entries list")

    entries: list[MutationEntry] = []
    for index, raw_entry in enumerate(raw_entries, start=1):
        if not isinstance(raw_entry, dict):
            raise BatteryConfigError(f"entry {index} must be a JSON object")
        command = _read_command(raw_entry.get("command"), f"entry {index} command")
        timeout = _read_timeout(
            raw_entry.get("timeout_seconds"),
            f"entry {index} timeout_seconds",
            default=None,
        )
        entries.append(
            MutationEntry(
                name=_read_string(raw_entry, "name", index),
                path=_resolve_entry_path(
                    path.parent,
                    _read_string(raw_entry, "path", index),
                    repo_root,
                ),
                old=_read_string(raw_entry, "old", index),
                new=_read_string(raw_entry, "new", index),
                command=command or default_command,
                timeout_seconds=timeout if timeout is not None else default_timeout,
            )
        )

    missing_command = [entry.name for entry in entries if not entry.command]
    if missing_command:
        names = ", ".join(missing_command)
        raise BatteryConfigError(f"entries missing command: {names}")

    return entries


def validate_battery(entries: Sequence[MutationEntry]) -> list[ValidationProblem]:
    """Return every config problem that would make a mutation result untrusted."""
    problems: list[ValidationProblem] = []
    for entry in entries:
        if entry.old == entry.new:
            problems.append(
                ValidationProblem(
                    entry=entry,
                    message="identity mutation: old and new are equal",
                )
            )
            continue

        try:
            source = entry.path.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(ValidationProblem(entry=entry, message=f"cannot read source: {exc}"))
            continue

        count = source.count(entry.old)
        if count != 1:
            problems.append(
                ValidationProblem(
                    entry=entry,
                    message=f"anchor occurrence count is {count}, expected exactly 1",
                )
            )

    return problems


class MutationRunner:
    """Apply, run, and restore targeted mutation entries."""

    def __init__(self, cwd: Path | None = None) -> None:
        self.cwd = cwd or Path.cwd()

    def run_all(self, entries: Sequence[MutationEntry]) -> list[MutationResult]:
        problems = validate_battery(entries)
        if problems:
            raise BatteryConfigError(format_validation_problems(problems))

        results: list[MutationResult] = []
        for entry in entries:
            result = self.run_entry(entry)
            results.append(result)
            state = "CAUGHT" if result.caught else "MISSED"
            print(f"{state} {entry.name} returncode={result.returncode}", flush=True)
        return results

    def run_entry(self, entry: MutationEntry) -> MutationResult:
        tracked_path = tracked_repository_path(entry.path)
        if tracked_path is None:
            return self._run_entry_in_place(entry)

        repo_root, relative_path = tracked_path
        cwd = self.cwd.resolve()
        if not cwd.is_relative_to(repo_root):
            raise BatteryConfigError(
                f"runner cwd {cwd} is outside mutation target repository {repo_root}"
            )
        with isolated_mutation_worktree(repo_root, [relative_path]) as workspace:
            isolated_entry = replace(entry, path=workspace.root / relative_path)
            isolated_cwd = workspace.root / cwd.relative_to(repo_root)
            result = MutationRunner(cwd=isolated_cwd)._run_entry_in_place(isolated_entry)
        return MutationResult(entry=entry, returncode=result.returncode)

    def _run_entry_in_place(self, entry: MutationEntry) -> MutationResult:
        original = entry.path.read_text(encoding="utf-8")
        mutated = original.replace(entry.old, entry.new, 1)

        try:
            _purge_pycache(entry.path.parent)
            entry.path.write_text(mutated, encoding="utf-8")
            completed = self._run_command(entry.command, entry.timeout_seconds)
            return MutationResult(entry=entry, returncode=completed.returncode)
        finally:
            entry.path.write_text(original, encoding="utf-8")
            _purge_pycache(entry.path.parent)

    def _run_command(
        self,
        command: Sequence[str],
        timeout_seconds: int | float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
        *,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        sys.stderr.flush()
        try:
            sys.stdout.flush()
            return subprocess.run(
                command,
                cwd=cwd or self.cwd,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise MutationTimeoutError(command, timeout_seconds) from exc


def format_validation_problems(problems: Sequence[ValidationProblem]) -> str:
    lines = ["CONFIG_ERROR mutation battery refused before running commands"]
    for problem in problems:
        lines.append(f"{problem.entry.name}: {problem.entry.path}: {problem.message}")
    return "\n".join(lines)


def _purge_pycache(root: Path) -> None:
    for pycache in sorted(root.rglob("__pycache__"), reverse=True):
        if pycache.is_dir():
            shutil.rmtree(pycache)


def _find_containment_root() -> Path:
    command = ["git", "rev-parse", "--show-toplevel"]
    cwd = Path.cwd().resolve()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=GIT_ROOT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise MutationTimeoutError(command, GIT_ROOT_TIMEOUT_SECONDS) from exc
    except OSError:
        return cwd
    if result.returncode == 0 and result.stdout.strip():
        root = Path(result.stdout.strip()).resolve()
        if not cwd.is_relative_to(root):
            raise BatteryConfigError(
                f"current directory {cwd} is outside git top-level {root}"
            )
        return root
    return cwd


def _resolve_entry_path(base: Path, raw_path: str, containment_root: Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = base / path
    resolved = path.resolve()
    root = containment_root.resolve()
    if not resolved.is_relative_to(root):
        raise BatteryConfigError(f"entry path escapes containment root: {raw_path}")
    return resolved


def _read_string(raw_entry: dict[str, Any], key: str, index: int) -> str:
    value = raw_entry.get(key)
    if not isinstance(value, str) or not value:
        raise BatteryConfigError(f"entry {index} field {key!r} must be a non-empty string")
    return value


def _read_command(raw_command: object, field_name: str) -> tuple[str, ...]:
    if raw_command is None:
        return ()
    if not isinstance(raw_command, list) or not raw_command:
        raise BatteryConfigError(f"{field_name} must be a non-empty string list")
    if not all(isinstance(part, str) and part for part in raw_command):
        raise BatteryConfigError(f"{field_name} must contain only non-empty strings")
    return tuple(raw_command)


def _read_timeout(
    raw_timeout: object,
    field_name: str,
    *,
    default: int | float | None,
) -> int | float | None:
    if raw_timeout is None:
        return default
    if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, int | float):
        raise BatteryConfigError(f"{field_name} must be a positive number")
    if raw_timeout <= 0:
        raise BatteryConfigError(f"{field_name} must be a positive number")
    return raw_timeout


def _format_command(command: Sequence[str]) -> str:
    return shlex.join(command)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("battery", type=Path, help="JSON battery file")
    args = parser.parse_args(argv)

    try:
        entries = load_battery(args.battery)
        results = MutationRunner().run_all(entries)
    except BatteryConfigError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return EXIT_CONFIG_ERROR
    except MutationTimeoutError as exc:
        print(f"EXTERNAL_ERROR {exc}", file=sys.stderr, flush=True)
        return EXIT_EXTERNAL_ERROR
    except KeyboardInterrupt:
        print("INTERRUPTED mutation battery restored source", file=sys.stderr, flush=True)
        return EXIT_INTERRUPTED
    except OSError as exc:
        print(f"EXTERNAL_ERROR {exc}", file=sys.stderr, flush=True)
        return EXIT_EXTERNAL_ERROR

    return EXIT_OK if all(result.caught for result in results) else EXIT_MUTATION_MISSED


if __name__ == "__main__":
    raise SystemExit(main())
