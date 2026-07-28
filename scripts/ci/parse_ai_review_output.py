"""Parse ai-review Copilot output and publish action outputs."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_CONFIG = 2
VALID_VERDICTS = {
    "PASS",
    "WARN",
    "CRITICAL_FAIL",
    "REJECTED",
    "COMPLIANT",
    "NON_COMPLIANT",
    "PARTIAL",
    "FAIL",
    "NEEDS_REVIEW",
    "DID_NOT_RUN",
    "UNKNOWN",
}
BLOCKING_VERDICTS = {
    "CRITICAL_FAIL",
    "REJECTED",
    "FAIL",
    "NON_COMPLIANT",
    "NEEDS_REVIEW",
    "DID_NOT_RUN",
    "UNKNOWN",
}
VERDICT_LINE_RE = re.compile(r"VERDICT:[ \t]*\[?([A-Z_][A-Z_]*)\]?[ \t]*$")
JSON_VERDICT_RE = re.compile(r'"verdict"\s*:\s*"([A-Z_]+)"')
LABEL_RE = re.compile(r"LABEL:[ \t]*([^ \t\n]*)")
MILESTONE_RE = re.compile(r"MILESTONE:[ \t]*([^ \t\n]*)")


@dataclass(frozen=True, slots=True)
class ParseResult:
    verdict: str
    labels: str
    milestone: str
    exit_code: int


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def extract_verdict(output: str) -> str:
    matches = [
        match.group(1)
        for line in output.splitlines()
        if (match := VERDICT_LINE_RE.search(line))
    ]
    if matches:
        return matches[-1]

    json_matches: list[str] = JSON_VERDICT_RE.findall(output)
    if json_matches:
        print("::notice::Verdict extracted from JSON 'verdict' field (no literal VERDICT: line)")
        return json_matches[-1]
    return ""


def parse_output(output: str) -> ParseResult:
    verdict = extract_verdict(output)
    if verdict not in VALID_VERDICTS:
        if not verdict:
            print("::warning::No explicit VERDICT: TOKEN found in AI output")
        else:
            print(f"::warning::Unrecognized verdict token: {verdict}")
        print(
            "::warning::AI output should end with: VERDICT: "
            "[PASS|WARN|CRITICAL_FAIL|REJECTED|COMPLIANT|NON_COMPLIANT|PARTIAL|FAIL]"
        )
        verdict = "NEEDS_REVIEW"

    labels = json.dumps(
        [label for label in LABEL_RE.findall(output) if label],
        separators=(",", ":"),
    )
    milestone_match = MILESTONE_RE.search(output)
    milestone = milestone_match.group(1) if milestone_match else ""
    exit_code = 1 if verdict in BLOCKING_VERDICTS else 0
    return ParseResult(verdict=verdict, labels=labels, milestone=milestone, exit_code=exit_code)


def publish_result(result: ParseResult, output_path: Path) -> None:
    append_line(output_path, f"verdict={result.verdict}")
    append_line(output_path, f"labels={result.labels}")
    append_line(output_path, f"milestone={result.milestone}")
    append_line(output_path, f"exit_code={result.exit_code}")
    print("Parsed results:")
    print(f"  Verdict: {result.verdict}")
    print(f"  Labels: {result.labels}")
    print(f"  Milestone: {result.milestone}")
    print(f"  Exit Code: {result.exit_code}")


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    if argv:
        print("error: no arguments are supported", file=sys.stderr)
        return EXIT_CONFIG
    resolved_env = os.environ if env is None else env
    input_file = resolved_env.get("AI_REVIEW_OUTPUT_FILE")
    github_output = resolved_env.get("GITHUB_OUTPUT")
    if not input_file:
        print("error: AI_REVIEW_OUTPUT_FILE is required", file=sys.stderr)
        return EXIT_CONFIG
    if not github_output:
        print("error: GITHUB_OUTPUT is required", file=sys.stderr)
        return EXIT_CONFIG

    output = Path(input_file).read_text(encoding="utf-8") if Path(input_file).is_file() else ""
    publish_result(parse_output(output), Path(github_output))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
