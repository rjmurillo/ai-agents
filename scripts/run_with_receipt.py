#!/usr/bin/env python3
"""Run a command and keep its bulk output out of model context (issue #5851).

Opt-in wrapper. No tool-use hook may intercept output (tool-use-hook-bar.md,
ADR-097), so agents and skills call this explicitly for commands known to be
large (full test runs, builds, log dumps, wide greps).

Usage:
    run_with_receipt.py run [--max-inline-bytes N] [--out-dir DIR] -- CMD [ARG...]
    run_with_receipt.py read ARTIFACT [--offset N] [--length N] [--out-dir DIR]

``run`` executes CMD as an argv list (never through a shell), captures stdout
and stderr in arrival order, and redacts secrets in memory with
``redact_secrets.redact_ci_sink`` before any byte reaches disk or a terminal.

* Output at or below ``--max-inline-bytes`` (default 16384) passes through to the
  same streams, redacted, with no receipt and no artifact.
* Larger output is saved in full (redacted) to a file under the output dir
  (default ``.project-toolkit/temp/tool-output``, gitignored) and a bounded
  receipt is printed: command, exit code, duration, total bytes, exposed bytes,
  truncated flag, artifact path, and, on nonzero exit, a stderr tail.

``read`` pages through a saved artifact by byte range. The artifact holds the
redacted bytes. Unredacted bytes are never written, so a retrieval cannot
return a secret the run did not already redact.

Exit codes: the wrapper returns the child's exit code (a signal death becomes
128 + signal), so a child exit of 2 or 3 cannot be told apart from the
wrapper's own codes without a receipt. Wrapper failures use the AGENTS.md
scheme: 2 = usage error, 3 = external failure (cannot launch the command, cannot
write or read the artifact). ``read`` returns 0 or 2/3 on those same terms.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from io import BufferedReader
from pathlib import Path

from redact_secrets import redact_ci_sink

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_EXTERNAL = 3

DEFAULT_MAX_INLINE_BYTES = 16384
HEAD_BYTES = 2048
TAIL_BYTES = 2048
FAILURE_EXCERPT_BYTES = 2048
DEFAULT_READ_LENGTH = 8192
MAX_READ_LENGTH = 65536
READ_CHUNK = 65536
DEFAULT_OUT_SUBDIR = Path(".project-toolkit") / "temp" / "tool-output"
OUT_DIR_ENV = "TOOL_OUTPUT_DIR"

_SECRET_ENV_NAME = re.compile(
    r"(?i)(token|secret|passw(or)?d|api[_-]?key|credential|private[_-]?key)"
)
_MIN_SECRET_LENGTH = 8


@dataclass(slots=True)
class Capture:
    """Child output in arrival order, plus per-stream byte buffers."""

    chunks: list[tuple[str, bytes]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, stream: str, data: bytes) -> None:
        with self.lock:
            self.chunks.append((stream, data))

    def stream_bytes(self, stream: str) -> bytes:
        return b"".join(data for name, data in self.chunks if name == stream)

    def merged_bytes(self) -> bytes:
        return b"".join(data for _, data in self.chunks)


@dataclass(frozen=True, slots=True)
class Receipt:
    """Facts printed for a contained run. Text fields are already redacted."""

    command: str
    exit_code: int
    duration_s: float
    total_bytes: int
    exposed_bytes: int
    truncated: bool
    artifact: str
    head: str
    tail: str
    failure_excerpt: str


def _secret_values() -> list[str]:
    return [
        value
        for name, value in os.environ.items()
        if _SECRET_ENV_NAME.search(name) and len(value) >= _MIN_SECRET_LENGTH
    ]


def _scrub(text: str) -> str:
    """Redact `text` with token shapes plus exact secret values from the env."""
    return str(redact_ci_sink(text, secret_values=_secret_values()).text)


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _pump(pipe: BufferedReader, stream: str, capture: Capture) -> None:
    while True:
        data = pipe.read1(READ_CHUNK)
        if not data:
            return
        capture.add(stream, data)


def _run_child(argv: list[str]) -> tuple[int, Capture]:
    """Run argv without a shell and return the exit code and captured output."""
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    capture = Capture()
    threads = [
        threading.Thread(target=_pump, args=(proc.stdout, "out", capture)),
        threading.Thread(target=_pump, args=(proc.stderr, "err", capture)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    code = proc.wait()
    return (128 - code if code < 0 else code), capture


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def resolve_out_dir(explicit: str | None) -> Path:
    chosen = explicit or os.environ.get(OUT_DIR_ENV)
    if chosen:
        return Path(chosen).expanduser().resolve()
    return _find_repo_root(Path.cwd().resolve()) / DEFAULT_OUT_SUBDIR


def _write_artifact(out_dir: Path, text: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = out_dir / f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.log"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def _clip_bytes(text: str, limit: int, *, keep: str) -> str:
    """Return at most `limit` UTF-8 bytes from the head or tail of `text`."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    piece = data[:limit] if keep == "head" else data[-limit:]
    return piece.decode("utf-8", errors="ignore")


def build_receipt(
    argv: list[str],
    exit_code: int,
    duration_s: float,
    capture: Capture,
    artifact: Path,
    redacted_merged: str,
) -> Receipt:
    total = len(capture.merged_bytes())
    head = _clip_bytes(redacted_merged, HEAD_BYTES, keep="head")
    tail = _clip_bytes(redacted_merged, TAIL_BYTES, keep="tail")
    fits = len(head.encode("utf-8")) + len(tail.encode("utf-8")) >= len(
        redacted_merged.encode("utf-8")
    )
    if fits:
        head, tail = redacted_merged, ""
    failure = ""
    if exit_code != 0:
        failure = _clip_bytes(
            _scrub(_decode(capture.stream_bytes("err"))), FAILURE_EXCERPT_BYTES, keep="tail"
        )
    exposed = sum(len(part.encode("utf-8")) for part in (head, tail, failure))
    return Receipt(
        command=_scrub(shlex.join(argv)),
        exit_code=exit_code,
        duration_s=duration_s,
        total_bytes=total,
        exposed_bytes=exposed,
        truncated=not fits,
        artifact=str(artifact),
        head=head,
        tail=tail,
        failure_excerpt=failure,
    )


def format_receipt(receipt: Receipt) -> str:
    lines = [
        "[output contained: full output saved, excerpts below]",
        f"command: {receipt.command}",
        f"exit_code: {receipt.exit_code}",
        f"duration_s: {receipt.duration_s:.2f}",
        f"total_bytes: {receipt.total_bytes}",
        f"exposed_bytes: {receipt.exposed_bytes}",
        f"truncated: {str(receipt.truncated).lower()}",
        f"artifact: {receipt.artifact}",
        "retrieve: run_with_receipt.py read <artifact> --offset N --length N",
        "--- output head ---",
        receipt.head,
    ]
    if receipt.tail:
        lines += ["--- output tail ---", receipt.tail]
    if receipt.failure_excerpt:
        lines += ["--- stderr tail (nonzero exit) ---", receipt.failure_excerpt]
    return "\n".join(lines).rstrip("\n") + "\n"


def _passthrough(capture: Capture) -> None:
    sys.stdout.write(_scrub(_decode(capture.stream_bytes("out"))))
    sys.stdout.flush()
    sys.stderr.write(_scrub(_decode(capture.stream_bytes("err"))))
    sys.stderr.flush()


def run_command(argv: list[str], max_inline_bytes: int, out_dir: Path) -> int:
    started = time.monotonic()
    try:
        exit_code, capture = _run_child(argv)
    except OSError as exc:
        print(f"run_with_receipt: cannot launch {argv[0]!r}: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    duration = time.monotonic() - started
    if len(capture.merged_bytes()) <= max_inline_bytes:
        _passthrough(capture)
        return exit_code
    redacted = _scrub(_decode(capture.merged_bytes()))
    try:
        artifact = _write_artifact(out_dir, redacted)
    except OSError as exc:
        print(f"run_with_receipt: cannot write artifact: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    receipt = build_receipt(argv, exit_code, duration, capture, artifact, redacted)
    sys.stdout.write(format_receipt(receipt))
    sys.stdout.flush()
    return exit_code


def _is_inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def read_artifact(artifact: str, offset: int, length: int, out_dir: Path) -> int:
    """Print `length` bytes of a saved artifact from `offset` (CWE-22 guarded)."""
    path = Path(artifact).expanduser().resolve()
    if not _is_inside(path, out_dir):
        print(f"run_with_receipt: {path} is outside {out_dir}", file=sys.stderr)
        return EXIT_USAGE
    if offset < 0 or length < 1:
        print("run_with_receipt: offset must be >= 0 and length >= 1", file=sys.stderr)
        return EXIT_USAGE
    length = min(length, MAX_READ_LENGTH)
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(length)
    except OSError as exc:
        print(f"run_with_receipt: cannot read artifact: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    sys.stdout.write(_decode(data))
    sys.stdout.flush()
    end = offset + len(data)
    more = f" next_offset={end}" if end < size else " end_of_artifact"
    print(f"\n[range {offset}-{end} of {size} bytes;{more}]", file=sys.stderr)
    return EXIT_OK


def _split_command(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" not in argv:
        return argv, []
    index = argv.index("--")
    return argv[:index], argv[index + 1 :]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_with_receipt.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="mode", required=True)
    run = sub.add_parser("run", help="run CMD after `--`, contain large output")
    run.add_argument("--max-inline-bytes", type=int, default=DEFAULT_MAX_INLINE_BYTES)
    run.add_argument("--out-dir", default=None)
    read = sub.add_parser("read", help="page through a saved artifact by byte range")
    read.add_argument("artifact")
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--length", type=int, default=DEFAULT_READ_LENGTH)
    read.add_argument("--out-dir", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    own, command = _split_command(raw)
    try:
        args = _build_parser().parse_args(own)
    except SystemExit as exc:
        return EXIT_OK if exc.code in (0, None) else EXIT_USAGE
    out_dir = resolve_out_dir(args.out_dir)
    if args.mode == "read":
        return read_artifact(args.artifact, args.offset, args.length, out_dir)
    if not command or args.max_inline_bytes < 0:
        print("usage: run_with_receipt.py run [options] -- CMD [ARG...]", file=sys.stderr)
        return EXIT_USAGE
    return run_command(command, args.max_inline_bytes, out_dir)


if __name__ == "__main__":
    sys.exit(main())
