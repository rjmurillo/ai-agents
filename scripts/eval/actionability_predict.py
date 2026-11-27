"""Call a model on in-band corpus rows and record one prediction per row.

Plan task M1-T14 of ``.project-toolkit/plans/active/harness-agnostic-llm-fallback.md``.
The ``predict`` subcommand of ``actionability_arms.py`` lives here so the arms and
score code stays cheap to import.

Before any call, every row to be sent is rescanned for secrets (body and replies,
the fields that leave the machine). Each untrusted field is wrapped in delimiters
that carry a random per-call token, so text inside a comment cannot close its own
delimiter (CWE-1427, prompt injection).

Records are appended to ``--output`` one line at a time, so a crash keeps every
finished call. A rerun on the same output skips rows already ``ok`` and retries
the rest. The calls send no ``temperature``: current Claude models may reject it,
and a rejected field makes ``call_api`` retry without it, which doubles the
requests (``scripts/eval/_anthropic_api.py``, ``call_api``).
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, TextIO, cast

# Must exist before the first scripts.* import below, so it cannot come from actionability_io.
_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from scripts.eval.actionability_io import (  # noqa: E402
    REPO_ROOT,  # noqa: F401
    load_jsonl,
    write_jsonl,
)
from scripts.eval.actionability_labels import (  # noqa: E402
    PROVENANCE_FIELDS,  # noqa: F401
    SPLIT_DEV,
    SPLIT_HELDOUT,
    STATUS_AUTH_ERROR,
    STATUS_CALL_ERROR,
    STATUS_INPUT_ERROR,
    STATUS_OK,
    STATUS_PARSE_ERROR,
    STATUSES,
)

# The message and resume groups moved out to keep this file under the taste size ceiling. Names
# marked F401 are re-exported for callers and tests that still import them from here.
from scripts.eval.actionability_message import (  # noqa: E402
    MAX_BODY_CHARS,  # noqa: F401
    MAX_REPLIES,  # noqa: F401
    MAX_REPLY_CHARS,  # noqa: F401
    MAX_TOKEN_ATTEMPTS,  # noqa: F401
    PROMPT_PATH,  # noqa: F401
    _new_token,  # noqa: F401
    _sent_fields,  # noqa: F401
    _wrap,  # noqa: F401
    build_user_message,
    input_sha256,
    load_prompt,
)
from scripts.eval.actionability_resume import (  # noqa: E402
    OutputError,
    _carried_ok,
    _check_carried,  # noqa: F401
    _decode_lines,  # noqa: F401
    _drop_stale,
    _read_prior_records,  # noqa: F401
)
from scripts.eval.actionability_scan import (  # noqa: E402
    add_allow_hex_argument,
    report_scan,
    scan_secrets,
)
from scripts.eval.actionability_validate import (  # noqa: E402
    SENT_ROW_CHECKS,
    RecordError,
    validate_records,
)
from scripts.eval.actionability_verdict import parse_verdict  # noqa: E402

logger = logging.getLogger(__name__)

# Spec Call contract limits.
MAX_OUTPUT_TOKENS = 100

# Premortem R2: below this many calls a failure rate says nothing. A run with no ok
# row at all fails regardless of this minimum.
MIN_ATTEMPTS_FOR_FAILURE_EXIT = 5

# Premortem R2: this many call_error results in a row mean the transport is down. Stop
# calling instead of failing the rest of the corpus one request at a time.
MAX_CONSECUTIVE_CALL_ERRORS = 5

API_KEY_ENV = "ANTHROPIC_API_KEY"

# Provider names that `scripts/eval/_providers.py` `_REGISTRY` maps to `_make_codex_cli`.
# tests/eval/test_actionability_predict_codex_refusal.py reads the registry and fails when
# this set and the registry disagree.
#
# predict sends untrusted review comments. `_codex_cli.py` `_build_argv` passes
# `--sandbox read-only`, which still lets the agent read any file the user can, and
# `codex exec --help` (codex-cli 0.172.0) lists no option that removes the shell or file
# tools. The Claude and Copilot cells pass `--disallowed-tools` and `--available-tools=`.
# A prompt-injected comment could therefore make Codex read a local file into the request.
CODEX_CLI_PROVIDERS = frozenset({"codex-cli", "codex-subscription"})

OUTPUT_FILE_MODE = 0o600

EXIT_SECRET = 1
EXIT_CONFIG = 2
EXIT_FAILURES = 3
EXIT_AUTH = 4

# `scripts/eval/_eval_common.py` `safe_http_error_message` builds
# "<surface> returned HTTP <status>: error=<category>; ..." and `_http_category`
# maps 401 and 403 to "auth". tests/eval/test_actionability_predict_durability.py
# runs the real function against this pattern.
_AUTH_FAILURE = re.compile(r"returned HTTP (?:401|403)\b|error=auth\b")

Complete = Callable[[str], str]
Sink = Callable[[dict[str, Any]], None]


def is_auth_failure(exc: BaseException) -> bool:
    """True when ``exc`` carries the fixed HTTP 401 or 403 message of the eval transports."""
    return bool(_AUTH_FAILURE.search(str(exc)))


def _load_eval_module(name: str) -> ModuleType:
    """Import a private ``scripts/eval`` module at call time, so importing this one stays cheap.

    Each name maps to a literal import, so no caller-supplied string reaches
    ``importlib.import_module``.
    """
    eval_dir = str(Path(__file__).resolve().parent)
    if eval_dir not in sys.path:
        sys.path.insert(0, eval_dir)
    if name == "_anthropic_api":
        return importlib.import_module("_anthropic_api")
    if name == "_providers":
        return importlib.import_module("_providers")
    raise ValueError(f"not a loadable eval module: {name!r}")


def _load_call_api() -> Callable[..., str]:
    """Resolve the shared transport at call time."""
    return cast(Callable[..., str], _load_eval_module("_anthropic_api").call_api)


def _failure_outcome(status: str, exc: BaseException, latency: float) -> dict[str, Any]:
    # The class name is recorded, never the message: provider text may carry secrets.
    return {
        "status": status,
        "is_actionable": None,
        "confidence": None,
        "reason": "",
        "latency_s": latency,
        "error_type": type(exc).__name__,
    }


def _breaker_tripped(records: list[dict[str, Any]]) -> bool:
    """True when the newest transport results are ``MAX_CONSECUTIVE_CALL_ERRORS`` call_error.

    An ``input_error`` never touched the transport, so it neither counts toward the streak
    nor breaks it.
    """
    tail = [r for r in records if r["status"] != STATUS_INPUT_ERROR][-MAX_CONSECUTIVE_CALL_ERRORS:]
    return len(tail) == MAX_CONSECUTIVE_CALL_ERRORS and all(
        r["status"] == STATUS_CALL_ERROR for r in tail
    )


def _predict_one(
    row: dict[str, Any], complete: Complete, clock: Callable[[], float]
) -> dict[str, Any]:
    start = clock()
    try:
        message = build_user_message(row)
    except ValueError as exc:
        return _failure_outcome(STATUS_INPUT_ERROR, exc, round(clock() - start, 4))
    try:
        text = complete(message)
    except (RuntimeError, OSError, ValueError) as exc:
        auth = isinstance(exc, RuntimeError) and is_auth_failure(exc)
        status = STATUS_AUTH_ERROR if auth else STATUS_CALL_ERROR
        return _failure_outcome(status, exc, round(clock() - start, 4))
    latency = round(clock() - start, 4)
    verdict = parse_verdict(text)
    if verdict is None:
        return {
            "status": STATUS_PARSE_ERROR,
            "is_actionable": None,
            "confidence": None,
            "reason": "",
            "latency_s": latency,
        }
    return {
        "status": STATUS_OK,
        "is_actionable": verdict.is_actionable,
        "confidence": verdict.confidence,
        "reason": verdict.reason,
        "latency_s": latency,
    }


def predict_rows(
    rows: list[dict[str, Any]],
    *,
    complete: Complete,
    provider: str,
    model: str,
    prompt_sha256: str,
    clock: Callable[[], float] = time.monotonic,
    sink: Sink | None = None,
) -> list[dict[str, Any]]:
    """Call ``complete`` once per row and return one record per row attempted.

    ``sink`` receives each record as soon as it exists. The loop stops after the
    first ``auth_error``, and after ``MAX_CONSECUTIVE_CALL_ERRORS`` call_error results
    in a row: the next call would fail the same way.
    """
    records: list[dict[str, Any]] = []
    for row in rows:
        outcome = _predict_one(row, complete, clock)
        record = {
            "id": row["id"],
            "status": outcome.pop("status"),
            "is_actionable": outcome.pop("is_actionable"),
            "confidence": outcome.pop("confidence"),
            "reason": outcome.pop("reason"),
            "latency_s": outcome.pop("latency_s"),
            "provider": provider,
            "model": model,
            "prompt_sha256": prompt_sha256,
            "input_sha256": input_sha256(row),
            **outcome,
        }
        records.append(record)
        if sink is not None:
            sink(record)
        if record["status"] == STATUS_AUTH_ERROR or _breaker_tripped(records):
            break
    return records


def _effective_provider(provider: str | None) -> str:
    if provider is not None:
        return provider
    return os.environ.get("EVAL_PROVIDER") or "anthropic"


def _needs_anthropic_key(provider: str | None) -> bool:
    """True when the effective provider is the built-in Anthropic transport.

    Same test as ``_anthropic_api.load_api_key_for_selected_provider``: ``--provider`` wins,
    then ``EVAL_PROVIDER``, and only the default transport needs ``ANTHROPIC_API_KEY``. Any
    other transport loads its own credential or needs none.
    """
    is_default = cast(
        Callable[[str | None], bool], _load_eval_module("_providers").is_default_anthropic
    )
    return is_default(_effective_provider(provider))


def _predict_config_error(args: argparse.Namespace, has_api_key: bool) -> str | None:
    if not 0.0 <= args.max_failure_rate <= 1.0:
        return "--max-failure-rate must be between 0 and 1"
    if not args.model.strip():
        return "--model must not be empty"
    if _effective_provider(args.provider).strip().lower() in CODEX_CLI_PROVIDERS:
        return (
            f"provider {_effective_provider(args.provider)!r} cannot run predict: `codex exec` "
            "has no option that disables its shell and file tools, so a prompt-injected "
            "comment could read local files into the request. Use another provider"
        )
    if not has_api_key and _needs_anthropic_key(args.provider):
        return "ANTHROPIC_API_KEY is not set; set it or select another provider"
    return None


def _make_sink(handle: TextIO) -> Sink:
    def sink(record: dict[str, Any]) -> None:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())

    return sink


def _exit_code(records: list[dict[str, Any]], max_rate: float, tripped: bool = False) -> int:
    """Decide the exit code from every record of the selected rows, carried ones included.

    ``tripped`` is the consecutive call_error breaker, judged on this run's new records only.
    """
    attempted = len(records)
    ok = sum(1 for r in records if r["status"] == STATUS_OK)
    failures = attempted - ok
    if any(r["status"] == STATUS_AUTH_ERROR for r in records):
        print("authentication failed (HTTP 401 or 403); stopped calling", file=sys.stderr)
        return EXIT_AUTH
    if tripped:
        print(
            f"stopped after {MAX_CONSECUTIVE_CALL_ERRORS} consecutive call_error; "
            "rerun to retry the rest",
            file=sys.stderr,
        )
        return EXIT_FAILURES
    if attempted >= 1 and ok == 0:
        print(f"no ok prediction in {attempted} attempted", file=sys.stderr)
        return EXIT_FAILURES
    if attempted >= MIN_ATTEMPTS_FOR_FAILURE_EXIT and failures / attempted > max_rate:
        print(
            f"failure rate {failures}/{attempted} exceeds --max-failure-rate {max_rate}",
            file=sys.stderr,
        )
        return EXIT_FAILURES
    return 0


def _summary_line(records: list[dict[str, Any]], selected: int, tripped: bool = False) -> str:
    counts = {s: sum(1 for r in records if r["status"] == s) for s in STATUSES}
    line = (
        f"attempted {len(records)} of {selected} selected: ok {counts[STATUS_OK]}, "
        f"parse_error {counts[STATUS_PARSE_ERROR]}, call_error {counts[STATUS_CALL_ERROR]}"
    )
    if counts[STATUS_AUTH_ERROR]:
        line += f", auth_error {counts[STATUS_AUTH_ERROR]}"
    if counts[STATUS_INPUT_ERROR]:
        line += f", input_error {counts[STATUS_INPUT_ERROR]}"
    if tripped:
        line += f"; stopped after {MAX_CONSECUTIVE_CALL_ERRORS} consecutive call_error"
    return line


def _run_pending(
    pending: list[dict[str, Any]], args: argparse.Namespace, api_key: str, run: dict[str, str]
) -> list[dict[str, Any]]:
    """Call the model for ``pending`` rows, appending each record to ``--output`` as it lands."""
    if not pending:
        return []
    system, _ = load_prompt()
    call_api = _load_call_api()

    def complete(user_message: str) -> str:
        return call_api(
            api_key,
            [{"role": "user", "content": user_message}],
            system=system,
            model=args.model,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=None,
            provider=args.provider,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Owner-only on first creation, like the 0600 files `atomic_write_text` makes: the records
    # name the provider and model, and a shared umask must not widen who can read them.
    fd = os.open(args.output, os.O_WRONLY | os.O_APPEND | os.O_CREAT, OUTPUT_FILE_MODE)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        return predict_rows(
            pending,
            complete=complete,
            provider=run["provider"],
            model=run["model"],
            prompt_sha256=run["prompt_sha256"],
            sink=_make_sink(handle),
        )


def cmd_predict(args: argparse.Namespace) -> int:
    """Call the model on in-band rows of one split and log one record per row."""
    api_key = (os.environ.get(API_KEY_ENV) or "").strip()
    config_error = _predict_config_error(args, bool(api_key))
    if config_error is not None:
        print(f"error: {config_error}", file=sys.stderr)
        return EXIT_CONFIG
    rows = load_jsonl(args.corpus)
    if rows is None:
        return EXIT_CONFIG
    positions = [
        i for i, r in enumerate(rows, start=1) if r.get("in_band") and r.get("split") == args.split
    ]
    selected = [rows[i - 1] for i in positions]
    if not selected:
        logger.error("no in_band rows in split %r of %s", args.split, args.corpus)
        return EXIT_CONFIG
    try:
        validate_records(selected, SENT_ROW_CHECKS, "corpus", numbers=positions)
    except RecordError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    scan = scan_secrets(selected, allow_hex_rows=args.allow_hex_rows, include_hunk=False)
    if not report_scan(scan):
        return EXIT_SECRET

    _, digest = load_prompt()
    run = {
        "provider": _effective_provider(args.provider),
        "model": args.model,
        "prompt_sha256": digest,
    }
    selected_ids = {r["id"] for r in selected}
    carried: list[dict[str, Any]] = []
    if args.output.exists():
        try:
            carried = _carried_ok(args.output, run)
        except OutputError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_CONFIG
        carried, stale = _drop_stale(carried, selected)
        write_jsonl(args.output, carried)
        done = [r for r in carried if r["id"] in selected_ids]
        print(f"resuming, {len(done)} done")
        if stale:
            print(f"{stale} carried records no longer match the corpus text; predicting again")
    done_ids = {r["id"] for r in carried}
    new_records = _run_pending([r for r in selected if r["id"] not in done_ids], args, api_key, run)
    final = [r for r in carried if r["id"] in selected_ids] + new_records
    tripped = _breaker_tripped(new_records)
    print(_summary_line(final, len(selected), tripped))
    return _exit_code(final, args.max_failure_rate, tripped)


def register_predict_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Add the ``predict`` subcommand to the arms CLI."""
    predict = sub.add_parser("predict", help="Call a model on the in-band rows of one split")
    predict.add_argument("--corpus", type=Path, required=True, help="Corpus JSONL")
    predict.add_argument("--split", choices=(SPLIT_DEV, SPLIT_HELDOUT), required=True)
    predict.add_argument("--provider", default=None, help="Provider name passed to call_api")
    predict.add_argument("--model", required=True, help="Model id (no default)")
    predict.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Predictions JSONL. Appended per call. An existing file is resumed.",
    )
    predict.add_argument("--max-failure-rate", type=float, default=0.5)
    add_allow_hex_argument(predict)
    predict.set_defaults(handler=cmd_predict)
