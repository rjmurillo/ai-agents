"""Reply-friction procedure: sample agent replies privately, then tally reader labels.

    replies_audit.py prepare --store DIR [--store DIR ...] --before ISO
        --run-dir NEW_DIR [--since ISO] [--exclude-session ID ...] [--limit 1000]
        [--seed 1] [--sample-per-kind 25] [--replay-min 3] [--marker REGEX ...]
        [--machine-turn REGEX ...] [--machine-first REGEX ...] [--entrypoint NAME ...]
    replies_audit.py tally --run-dir DIR --labels FILE

Privacy boundary:
- `--store` names one explicit Claude project directory per flag. A store root
  is refused, so unrelated projects are never read.
- stdout carries aggregate counts and reason codes only: no reply text, no
  quotes, no session ids. It also echoes `--run-dir` and the short
  entrypoint and agent-type names. Errors are fixed codes.
- Sampled text goes to `--run-dir`, which must not exist yet, must sit outside
  every store and outside the repository of the current directory, and is
  created 0700 with 0600 files. There is no full corpus export.
- `--marker` names a reply already known to be bad, the positive control. Each
  hit is sampled and kept out of every rate, up to 20 controls (`MAX_CONTROLS`
  in `replies_prepare.py`). Hits past 20 stay in the rate strata as ordinary
  replies. `tally` exits 1 unless each control label is `friction`.
  Only the hit count is printed.
- `--entrypoint` keeps only sessions started from that client. `--machine-first`
  drops a session whose first prompt a harness or another agent wrote.
- `--machine-turn` names the opening text of a turn another agent or the host
  writes in your setup. A matching turn counts as machine, not as a typed
  follow-up. A turn that opens with a tag (`<name>` or `</name>`) always counts
  as machine.

Exit codes: 0 ok, 1 labels failed validation, 2 usage or configuration error,
3 a read or write failure or an unexpected internal error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from replies_corpus import ConfigError, parse_ts
from replies_prepare import Config, run_prepare
from replies_tally import MAX_PROBLEMS, ValidationError, run_tally

DEFAULT_LIMIT = 1000
DEFAULT_PER_KIND = 25
DEFAULT_REPLAY_MIN = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="replies_audit.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="sample replies into a private run directory")
    prep.add_argument("--store", action="append", required=True, metavar="DIR")
    prep.add_argument("--before", required=True, help="frozen exclusive upper bound, ISO time")
    prep.add_argument("--since", help="inclusive lower bound, ISO time")
    prep.add_argument("--exclude-session", action="append", default=[], metavar="ID")
    prep.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT, help="transcripts, children included"
    )
    prep.add_argument("--run-dir", required=True, metavar="NEW_DIR")
    prep.add_argument("--seed", type=int, default=1)
    prep.add_argument("--sample-per-kind", type=int, default=DEFAULT_PER_KIND)
    prep.add_argument("--replay-min", type=int, default=DEFAULT_REPLAY_MIN)
    prep.add_argument("--marker", action="append", default=[], metavar="REGEX")
    prep.add_argument("--machine-turn", action="append", default=[], metavar="REGEX")
    prep.add_argument("--machine-first", action="append", default=[], metavar="REGEX")
    prep.add_argument("--entrypoint", action="append", default=[], metavar="NAME")
    tally = sub.add_parser("tally", help="validate labels and compute weighted estimates")
    tally.add_argument("--run-dir", required=True, metavar="DIR")
    tally.add_argument("--labels", required=True, metavar="FILE")
    return parser


def _time(raw: str | None, code: str) -> Any:
    if raw is None:
        return None
    parsed = parse_ts(raw)
    if parsed is None:
        raise ConfigError(code)
    return parsed


def _patterns(raw: list[str], code: str) -> list[re.Pattern[str]]:
    try:
        return [re.compile(item) for item in raw]
    except re.error as exc:
        raise ConfigError(code) from exc


def config_from(args: argparse.Namespace) -> Config:
    before = _time(args.before, "bad_before")
    since = _time(args.since, "bad_since")
    if since is not None and since >= before:
        raise ConfigError("since_not_before_before")
    if args.limit < 1 or args.sample_per_kind < 1 or args.replay_min < 2:
        raise ConfigError("bad_numeric_option")
    return Config(
        stores=[Path(s).expanduser() for s in args.store],
        before=before,
        since=since,
        exclude=set(args.exclude_session),
        limit=args.limit,
        run_dir=args.run_dir,
        seed=args.seed,
        per_kind=args.sample_per_kind,
        replay_min=args.replay_min,
        markers=_patterns(args.marker, "bad_marker"),
        cwd=Path.cwd(),
        relays=_patterns(args.machine_turn, "bad_machine_turn"),
        machine_first=_patterns(args.machine_first, "bad_machine_first"),
        entrypoints=set(args.entrypoint),
    )


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=1, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            payload = run_prepare(config_from(args))
            payload["examined"] = sum(payload["population"]["found"].values())
        else:
            payload = run_tally(Path(args.run_dir), Path(args.labels))
            payload["examined"] = payload["labeled"]
        _emit(payload)
    except ConfigError as exc:
        _emit({"error": "config", "message": str(exc)})
        return 2
    except ValidationError as exc:
        _emit(
            {
                "error": "invalid",
                "problem_count": len(exc.problems),
                "problems": exc.problems[:MAX_PROBLEMS],
            }
        )
        return 1
    except OSError:
        _emit({"error": "io", "message": "read_or_write_failed"})
        return 3
    except Exception:
        _emit({"error": "internal", "message": "unexpected_failure"})
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
