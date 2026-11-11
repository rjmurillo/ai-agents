"""Shared dispatch for repository-only skill instrument tables."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Row = dict[str, Any]


def instrument_row(identifier: str, answers: str, command: str, source: str) -> Row:
    """Keep instrument metadata fields consistent across tables."""
    return {"id": identifier, "answers": answers, "argv": command.split(), "source": source}


def drift_instrument(skill: str, skills_root: str) -> Row:
    return {
        "id": "drift-self-check",
        "answers": "Has this skill drifted from its reverify.json checks?",
        "argv": [
            "python3",
            f"{skills_root}/skill-bootstrap/scripts/bootstrap_drift.py",
            "check",
            "--repo",
            ".",
            "--skills-root",
            skills_root,
            "--name",
            skill,
            "--require",
        ],
        "source": "SKILL.md Provenance and Maintenance",
    }


def instrument_description(summary: str) -> str:
    return (
        summary
        + """

  instruments.py --repo . list
  instruments.py --repo . run <id> [-- args...]

Exit codes: 0 ok, 1 a listed instrument file is missing, 2 bad arguments or
unknown id, 3 the run target failed to start. A started child's exit code
passes through unchanged.
"""
    )


def instrument_epilog(example: str) -> str:
    return f"""\
run passes a started child process exit code through unchanged.

examples:
  %(prog)s --repo . list
  %(prog)s --repo . run {example}

exit codes:
  0  ok
  1  a listed instrument file is missing
  2  bad arguments or unknown id
  3  the run target failed to start
"""


@dataclass(frozen=True, slots=True)
class InstrumentHelp:
    """Keep the three existing help and diagnostic styles explicit."""

    skill: str
    description: str
    epilog: str
    style: Literal["plain", "json", "examined"]


def repo_paths_exist(repo: Path, row: Row) -> bool:
    return all(
        (repo / token).exists()
        for token in row["argv"][1:]
        if "/" in token and not token.startswith("-")
    )


def python_script_exists(repo: Path, row: Row) -> bool:
    argv: list[str] = row["argv"]
    for token in argv[1:]:
        if token.endswith(".py"):
            return (repo / token).is_file()
    return True


def checked_script_exists(repo: Path, row: Row) -> bool:
    if "check_path" in row:
        check_path: str = row["check_path"]
        return (repo / check_path).is_file()
    return python_script_exists(repo, row)


def inline_script_exists(repo: Path, row: Row) -> bool:
    argv = row["argv"]
    if "check_path" in row:
        check_path: str = row["check_path"]
        return (repo / check_path).is_file()
    if "-c" in argv:
        return all((repo / token).is_file() for token in argv[argv.index("-c") + 2 :])
    return python_script_exists(repo, row)


def python_target(argv: list[str]) -> str | None:
    if argv[0] == "python3":
        return argv[1]
    if argv[:3] == ["uv", "run", "python"]:
        return argv[3]
    return None


def target_exists(repo: Path, row: Row) -> bool:
    target = python_target(row["argv"])
    return target is None or (repo / target).is_file()


def test_target_exists(repo: Path, row: Row) -> bool:
    argv: list[str] = row["argv"]
    if argv[:3] == ["uv", "run", "pytest"]:
        return (repo / argv[3]).is_file()
    return target_exists(repo, row)


class InstrumentDispatcher:
    """Read each caller's current table instead of freezing it at import."""

    def __init__(
        self,
        help_text: InstrumentHelp,
        instruments: Callable[[], list[Row]],
        exists: Callable[[Path, Row], bool],
    ) -> None:
        self._help = help_text
        self._instruments = instruments
        self._exists = exists

    def build_parser(self) -> argparse.ArgumentParser:
        style = self._help.style
        description = self._help.description
        if style == "plain":
            description = description.splitlines()[0]
        elif style == "json":
            description = "List or run this skill's instruments."
        parser = argparse.ArgumentParser(
            description=description,
            epilog=self._help.epilog,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        if style == "examined":
            parser.add_argument("--repo", default=".")
        else:
            parser.add_argument("--repo", default=".", help="repository root (default: .)")
        sub = parser.add_subparsers(dest="command" if style == "plain" else "cmd", required=True)
        if style == "examined":
            sub.add_parser("list")
            run = sub.add_parser("run")
        else:
            listing = (
                "list instruments and whether each exists"
                if style == "plain"
                else "print every instrument row"
            )
            sub.add_parser("list", help=listing)
            run = sub.add_parser("run", help="run one instrument")
        run.add_argument("id")
        run.add_argument("args" if style == "json" else "extra", nargs=argparse.REMAINDER)
        return parser

    def cmd_list(self, repo: Path) -> int:
        rows = [{**row, "exists": self._exists(repo, row)} for row in self._instruments()]
        missing = [row["id"] for row in rows if not row["exists"]]
        print(
            json.dumps(
                {
                    "skill": self._help.skill,
                    "instruments": rows,
                    "examined": len(rows),
                    "missing": missing,
                },
                indent=2,
            )
        )
        return 1 if missing else 0

    def _unknown(self, ident: str, rows: list[Row]) -> int:
        if self._help.style == "plain":
            known = ", ".join(row["id"] for row in rows)
            print(f"error: unknown instrument '{ident}' (known: {known})", file=sys.stderr)
        else:
            error: dict[str, Any] = {
                "error": f"unknown instrument id: {ident}",
                "known": [row["id"] for row in rows],
            }
            if self._help.style == "examined":
                error["examined"] = len(rows)
            print(json.dumps(error), file=sys.stderr)
        return 2

    def _start_failure(self, row: Row, exc: OSError, examined: int) -> int:
        if self._help.style == "plain":
            print(f"error: cannot start {row['argv'][0]}: {exc}", file=sys.stderr)
        else:
            error: dict[str, Any] = {"error": f"failed to start: {exc}"}
            if self._help.style == "examined":
                error = {"error": f"cannot start {row['argv'][0]}: {exc}", "examined": examined}
            print(json.dumps(error), file=sys.stderr)
        return 3

    def cmd_run(self, repo: Path, ident: str, extra: list[str]) -> int:
        rows = self._instruments()
        if self._help.style == "examined":
            # This family checked its whole table before dispatch, including unknown IDs.
            rows = [{**row, "exists": self._exists(repo, row)} for row in rows]
        row = next((row for row in rows if row["id"] == ident), None)
        if row is None:
            return self._unknown(ident, rows)
        try:
            sys.stdout.flush()
            return subprocess.run(row["argv"] + extra, cwd=repo, check=False).returncode
        except OSError as exc:
            return self._start_failure(row, exc, len(rows))

    def main(self, argv: list[str] | None = None) -> int:
        try:
            args = self.build_parser().parse_args(argv)
        except SystemExit as exc:
            if self._help.style == "examined":
                return 0 if exc.code in (0, None) else 2
            raise
        repo = Path(args.repo)
        if self._help.style == "plain" and not repo.is_dir():
            print(f"error: --repo {args.repo} is not a directory", file=sys.stderr)
            return 2
        if self._help.style == "json":
            repo = repo.resolve()
        command = args.command if self._help.style == "plain" else args.cmd
        if command == "list":
            return self.cmd_list(repo)
        extra = args.args if self._help.style == "json" else args.extra
        if self._help.style == "examined":
            extra = [arg for arg in extra if arg != "--"]
        elif extra[:1] == ["--"]:
            extra = extra[1:]
        return self.cmd_run(repo, args.id, extra)
