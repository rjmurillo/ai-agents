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
fails unless the CLI exits 1 and names ``Error.Type``. A gate that cannot go
red reports PASS forever, so the negative half is part of the gate, not a test
beside it.

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
_EXIT_INVALID = 1

# The ADR-103 case: an error envelope with no Error.Type.
_MALFORMED_ENVELOPE = {
    "Success": False,
    "Data": None,
    "Error": {"Message": "boom", "Code": 1},
    "Metadata": {"Script": _SCRIPT_NAME, "Version": "1.0.0", "Timestamp": "2026-01-01T00:00:00Z"},
}


def _printed(call: Callable[[], object]) -> str:
    """Return what a producer prints to stdout, which is what skill consumers read.

    Producers also return the JSON string, but a caller reads stdout. Validating
    the return value would pass a producer that stopped printing. An empty result
    reaches the validator as empty input and fails there.
    """
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        call()
    return buffer.getvalue().strip()


def build_envelopes(producer: ModuleType, error_types: Iterable[str]) -> list[tuple[str, str]]:
    """Return (label, json text) for every envelope the producers can emit."""
    envelopes = [
        (
            "success",
            _printed(
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
            envelopes.append((label, _printed(call)))
    return envelopes


def _rejects_missing_type(repo_root: Path) -> bool:
    """True when the validator CLI rejects the malformed envelope for the right reason.

    A bare non-zero exit is not enough: a crashing validator exits non-zero too.
    The CLI must exit 1, its validation-failure code, and name ``Error.Type``.
    """
    result = subprocess.run(
        [sys.executable, str(repo_root / _VALIDATOR_SCRIPT)],
        input=json.dumps(_MALFORMED_ENVELOPE),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_CLI_TIMEOUT_SECONDS,
        cwd=repo_root,
        check=False,
    )
    return result.returncode == _EXIT_INVALID and "Error.Type" in result.stdout


def find_problems(repo_root: Path, producer: ModuleType, validator: ModuleType) -> list[str]:
    """Every way the producers and the validator disagree with the contract."""
    problems: list[str] = []
    unknown = set(producer.VALID_ERROR_TYPES) - set(validator.VALID_ERROR_TYPES)
    if unknown:
        problems.append(f"producer error types the validator rejects: {sorted(unknown)}")
    for label, text in build_envelopes(producer, validator.VALID_ERROR_TYPES):
        problems.extend(f"{label}: {finding}" for finding in _findings(validator, text))
    if not _rejects_missing_type(repo_root):
        problems.append("validator CLI did not reject an error envelope with no Error.Type")
    return problems


def _findings(validator: ModuleType, text: str) -> list[str]:
    """Validator findings for one printed envelope. Empty or non-JSON output is a finding."""
    try:
        return list(validator.validate_envelope(json.loads(text)))
    except json.JSONDecodeError as error:
        return [f"producer stdout is not one JSON envelope ({error.msg}): {text[:60]!r}"]


def _drop_modules_from_other_checkouts(repo_root: Path) -> None:
    """Forget cached ``scripts`` modules that came from a different checkout.

    ``--repo-root`` names the checkout to check. Python would reuse an already
    imported ``scripts.github_core.output`` from another checkout, and the gate
    would pass without looking at this one.
    """
    for name in [n for n in sys.modules if n == "scripts" or n.startswith("scripts.")]:
        origin = getattr(sys.modules[name], "__file__", None)
        if origin is not None and not Path(origin).resolve().is_relative_to(repo_root):
            del sys.modules[name]


def _load(repo_root: Path) -> tuple[ModuleType, ModuleType]:
    _drop_modules_from_other_checkouts(repo_root)
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
