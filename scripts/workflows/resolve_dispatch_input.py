#!/usr/bin/env python3
"""Validate a workflow input and write it to a GitHub Actions step output.

ADR-006 keeps logic out of ``run:`` blocks. Two workflows picked a value from
either a ``workflow_dispatch`` input or the event payload, constrained it, and
appended it to ``$GITHUB_OUTPUT`` in shell. The constraint is the part that has
to be right: both values reach a shell argument and a ``gh`` call downstream, so
an unconstrained dispatch input is a command-injection surface (#3652). The
workflow now picks the source in a ``env:`` expression, which is configuration,
and this script owns the check.

Environment:
    GITHUB_OUTPUT   Path Actions appends step outputs to. Required.
    OUTPUT_NAME     Name of the output to write. Required.
    INPUT_VALUE     The raw value to validate. Required, may be empty.
    VALUE_KIND      ``integer`` (default) or ``choice``.
    ALLOWED_CHOICES Comma-separated allowed values. Required when kind is
                    ``choice``, ignored otherwise.

Exit codes (AGENTS.md): 0 ok, 1 the value is rejected, 2 config error.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_REJECTED = 1
EXIT_CONFIG = 2

_OUTPUT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_POSITIVE_INTEGER = re.compile(r"^[0-9]+$")


class ConfigError(Exception):
    """The caller wired the script wrong."""


def parse_choices(raw: str) -> list[str]:
    return [choice.strip() for choice in raw.split(",") if choice.strip()]


def rejection(value: str, kind: str, choices: list[str]) -> str | None:
    """Return the rejection message for ``value``, or None when it is allowed."""
    if kind == "integer":
        if _POSITIVE_INTEGER.fullmatch(value) and int(value) > 0:
            return None
        return "must be a positive integer"
    if kind == "choice":
        if value in choices:
            return None
        return f"must be one of: {', '.join(choices)}"
    raise ConfigError(f"unknown VALUE_KIND: {kind!r}")


def write_output(output_path: Path, output_name: str, value: str) -> None:
    if not _OUTPUT_NAME_PATTERN.fullmatch(output_name):
        raise ConfigError(f"invalid GitHub output name: {output_name!r}")
    # A newline in the value would forge a second output line, so a value that
    # survived validation still gets checked before it is appended.
    if "\n" in value or "\r" in value:
        raise ConfigError("value contains a line break")
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{output_name}={value}\n")


def main() -> int:
    try:
        output_path = Path(os.environ["GITHUB_OUTPUT"])
        output_name = os.environ["OUTPUT_NAME"]
        value = os.environ["INPUT_VALUE"]
        kind = os.environ.get("VALUE_KIND", "integer")
        choices = parse_choices(os.environ.get("ALLOWED_CHOICES", ""))
        if kind == "choice" and not choices:
            raise ConfigError("VALUE_KIND=choice requires ALLOWED_CHOICES")
        problem = rejection(value, kind, choices)
        if problem is not None:
            print(f"::error::{output_name} {problem}", file=sys.stderr)
            return EXIT_REJECTED
        write_output(output_path, output_name, value)
    except KeyError as exc:
        print(f"error: missing environment variable: {exc.args[0]}", file=sys.stderr)
        return EXIT_CONFIG
    except (ConfigError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
