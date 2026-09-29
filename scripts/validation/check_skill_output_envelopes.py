#!/usr/bin/env python3
"""Check that real skill-output envelopes pass the ADR-056 / ADR-103 validator.

`scripts/validate_skill_output.py` is the envelope contract's validator. Until
issue #5299 nothing in the repository's own gates ran it: it was exercised only by
its unit tests, so a producer that drifted from the contract passed every gate.
ADR-103 named the gap and scoped its claim to "the function rejects a malformed
envelope when called".

This gate closes it from the producer side. It builds envelopes with the real
producers, `write_skill_output` and `write_skill_error` in
`scripts/github_core/output.py`, which every github-skill script calls, and asks
the validator to accept each one:

  * one success envelope;
  * one error envelope for every error type the validator accepts, with and
    without ``extra`` data.

Then it proves the check can fail. A malformed envelope (an error with no
``Type``, the ADR-103 case) is piped through the validator's CLI, and the gate
fails if the CLI accepts it. A gate that cannot go red reports PASS forever, so
the negative half is part of the gate, not a test beside it.

Also fails when a producer error type is one the validator rejects.

EXIT CODES (ADR-035):
  0 - every envelope validates and the malformed one is rejected
  1 - a producer envelope was rejected, or the validator accepted a malformed one
  2 - configuration error (repo root missing, or a required module is absent)
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import subprocess
import sys
from collections.abc import Callable, Iterable
from functools import partial
from pathlib import Path
from types import ModuleType

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import MissingScriptSkip  # noqa: E402

_PRODUCER_MODULE = "scripts.github_core.output"
_VALIDATOR_MODULE = "scripts.validate_skill_output"
_VALIDATOR_SCRIPT = Path("scripts") / "validate_skill_output.py"
_SCRIPT_NAME = "check_skill_output_envelopes.py"
_CLI_TIMEOUT_SECONDS = 30

# The ADR-103 case: an error envelope with no Error.Type.
_MALFORMED_ENVELOPE = {
    "Success": False,
    "Data": None,
    "Error": {"Message": "boom", "Code": 1},
    "Metadata": {"Script": _SCRIPT_NAME, "Version": "1.0.0", "Timestamp": "2026-01-01T00:00:00Z"},
}


def _quiet(call: Callable[[], object]) -> str:
    """Run a producer with its stdout swallowed. Producers print the envelope."""
    with contextlib.redirect_stdout(io.StringIO()):
        return str(call())


def build_envelopes(producer: ModuleType, error_types: Iterable[str]) -> list[tuple[str, str]]:
    """Return (label, json text) for every envelope the producers can emit."""
    envelopes = [
        (
            "success",
            _quiet(
                partial(
                    producer.write_skill_output,
                    {"key": "value"},
                    output_format="json",
                    script_name=_SCRIPT_NAME,
                )
            ),
        )
    ]
    for error_type in sorted(error_types):
        for extra in (None, {"detail": "extra"}):
            label = f"error:{error_type}" + (":extra" if extra else "")
            call = partial(
                producer.write_skill_error,
                "boom",
                1,
                error_type=error_type,
                output_format="json",
                script_name=_SCRIPT_NAME,
                extra=extra,
            )
            envelopes.append((label, _quiet(call)))
    return envelopes


def _rejected_by_cli(repo_root: Path, envelope: object) -> bool:
    """True when the validator CLI exits non-zero for ``envelope``."""
    result = subprocess.run(
        [sys.executable, str(repo_root / _VALIDATOR_SCRIPT)],
        input=json.dumps(envelope),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_CLI_TIMEOUT_SECONDS,
        cwd=repo_root,
        check=False,
    )
    return result.returncode != 0


def find_problems(repo_root: Path, producer: ModuleType, validator: ModuleType) -> list[str]:
    """Every way the producers and the validator disagree with the contract."""
    problems: list[str] = []
    unknown = set(producer.VALID_ERROR_TYPES) - set(validator.VALID_ERROR_TYPES)
    if unknown:
        problems.append(f"producer error types the validator rejects: {sorted(unknown)}")
    for label, text in build_envelopes(producer, validator.VALID_ERROR_TYPES):
        for finding in validator.validate_envelope(json.loads(text)):
            problems.append(f"{label}: {finding}")
    if not _rejected_by_cli(repo_root, _MALFORMED_ENVELOPE):
        problems.append("validator CLI accepted an error envelope with no Error.Type")
    return problems


def _load(repo_root: Path) -> tuple[ModuleType, ModuleType]:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return importlib.import_module(_PRODUCER_MODULE), importlib.import_module(_VALIDATOR_MODULE)


def validate_skill_output_envelopes(repo_root: Path) -> bool:
    """Pre-PR gate. Prints each problem and returns whether there were none."""
    if not (repo_root / _VALIDATOR_SCRIPT).is_file():
        raise MissingScriptSkip(f"{_VALIDATOR_SCRIPT.as_posix()} not present")
    producer, validator = _load(repo_root)
    problems = find_problems(repo_root, producer, validator)
    for problem in problems:
        print(f"[FAIL] skill output envelope: {problem}")
    return not problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    if not repo_root.is_dir():
        print(f"[CONFIG] repo root not found: {repo_root}", file=sys.stderr)
        return 2
    try:
        producer, validator = _load(repo_root)
    except ImportError as exc:
        print(f"[CONFIG] cannot import a required module: {exc}", file=sys.stderr)
        return 2
    problems = find_problems(repo_root, producer, validator)
    for problem in problems:
        print(f"[FAIL] {problem}")
    if not problems:
        print("[PASS] every producer envelope validates; the malformed envelope is rejected")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
