"""Render the post-PR retrospective prompt and publish it as a step output.

The prompt lived in a bash heredoc with an unquoted delimiter, so every
backtick in it needed a backslash to avoid command substitution. Forty-eight
lines of prose carrying that hazard is a poor trade for no benefit; the text
now lives in ``.github/prompts/post-pr-retrospective.md`` and is substituted
here, where a backtick is just a backtick.
"""

from __future__ import annotations

import argparse
import os
import string
import sys
from collections.abc import Mapping
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2

TEMPLATE_PATH = Path(".github/prompts/post-pr-retrospective.md")
DELIMITER = "RETRO_EOF"
PLACEHOLDERS = ("PR_NUMBER", "MERGED", "ESCALATE")


def render(template: str, values: Mapping[str, str]) -> str:
    """Substitute every placeholder, raising on one the caller did not supply.

    ``string.Template.substitute`` raises ``KeyError`` for an unknown name
    rather than leaving it in the text. A prompt that reaches the agent still
    reading ``${PR_NUMBER}`` is worse than a red step.
    """
    return string.Template(template).substitute(values)


def append_multiline_output(path: Path, name: str, value: str) -> None:
    """Append a heredoc-delimited output, refusing a value that contains the delimiter.

    A value carrying the delimiter on its own line would close the block early
    and let the remainder be parsed as further outputs.
    """
    if any(line.strip() == DELIMITER for line in value.splitlines()):
        raise ValueError(f"rendered prompt contains the output delimiter {DELIMITER}")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{name}<<{DELIMITER}\n")
        handle.write(value)
        if not value.endswith("\n"):
            handle.write("\n")
        handle.write(f"{DELIMITER}\n")


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", default=str(TEMPLATE_PATH))
    args = parser.parse_args(argv)

    resolved = os.environ if env is None else env
    output = resolved.get("GITHUB_OUTPUT", "")
    if not output:
        print("::error::GITHUB_OUTPUT is required", file=sys.stderr)
        return EXIT_CONFIG

    template_path = Path(args.template)
    if not template_path.is_file():
        print(f"::error::Prompt template not found: {template_path}", file=sys.stderr)
        return EXIT_CONFIG

    values = {name: resolved.get(name, "") for name in PLACEHOLDERS}
    try:
        prompt = render(template_path.read_text(encoding="utf-8"), values)
    except KeyError as exc:
        print(f"::error::Prompt template uses an unknown placeholder: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    append_multiline_output(Path(output), "PROMPT", prompt)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
