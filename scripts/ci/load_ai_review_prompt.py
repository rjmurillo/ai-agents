"""Load the ai-review prompt template and publish step outputs."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2
PROMPT_OUTPUT_PATH = Path("/tmp/ai-review-prompt.md")
DEFAULT_PROMPT_PATH = Path(".github/prompts/default-ai-review.md")
FALLBACK_PROMPT = (
    "Analyze the provided context and give your assessment.\n\n"
    "End with: VERDICT: [PASS|WARN|CRITICAL_FAIL|REJECTED]\n"
)


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def append_multiline_output(path: Path, name: str, value: str, delimiter: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{name}<<{delimiter}\n")
        handle.write(value)
        if value and not value.endswith("\n"):
            handle.write("\n")
        handle.write(f"{delimiter}\n")


def load_prompt(
    *,
    prompt_file: str,
    github_output: Path,
    prompt_output_path: Path = PROMPT_OUTPUT_PATH,
    default_prompt_path: Path = DEFAULT_PROMPT_PATH,
) -> int:
    if prompt_file and Path(prompt_file).is_file():
        print(f"Using prompt template: {prompt_file}")
        prompt_text = Path(prompt_file).read_text(encoding="utf-8")
        prompt_source = prompt_file
    elif default_prompt_path.is_file():
        print("Using default prompt template")
        prompt_text = default_prompt_path.read_text(encoding="utf-8")
        prompt_source = str(default_prompt_path)
    else:
        print("Warning: No prompt template found, using minimal prompt")
        prompt_text = FALLBACK_PROMPT
        prompt_source = "generated"

    prompt_output_path.write_text(prompt_text, encoding="utf-8")
    append_line(github_output, f"prompt_source={prompt_source}")
    append_line(github_output, f"prompt_file={prompt_output_path}")
    append_multiline_output(github_output, "prompt_template", prompt_text, "EOF_PROMPT")
    return EXIT_OK


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    if argv:
        print("error: no arguments are supported", file=sys.stderr)
        return EXIT_CONFIG
    resolved_env = os.environ if env is None else env
    output_file = resolved_env.get("GITHUB_OUTPUT")
    if not output_file:
        print("error: GITHUB_OUTPUT is required", file=sys.stderr)
        return EXIT_CONFIG
    return load_prompt(
        prompt_file=resolved_env.get("PROMPT_FILE", ""),
        github_output=Path(output_file),
    )


if __name__ == "__main__":
    raise SystemExit(main())
