"""SPIKE ONLY. Time the checker the way a Stop hook would pay for it.

Each sample is a fresh ``python3 -I`` subprocess that imports the vendored core,
parses the whole transcript, rebuilds session history, and judges the last
reply. Wall clock includes interpreter start. Prints JSON with p50, p95, max.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHILD = (
    "import sys; sys.path.insert(0, sys.argv[1]);"
    "from pathlib import Path; from adapter import check_transcript;"
    "list(check_transcript(Path(sys.argv[2])))"
)


def time_one(path: Path) -> float:
    """Seconds for one cold run over one transcript."""
    start = time.perf_counter()
    subprocess.run(
        [sys.executable, "-I", "-c", CHILD, str(HERE), str(path)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    return time.perf_counter() - start


def main(argv: list[str] | None = None) -> int:
    """Time each transcript named in a selection file plus any extra paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    samples = []
    for path in args.paths:
        seconds = time_one(path)
        samples.append({"bytes": path.stat().st_size, "seconds": round(seconds, 3)})
    secs = sorted(s["seconds"] for s in samples)
    p95 = secs[min(len(secs) - 1, int(round(0.95 * (len(secs) - 1))))]
    biggest = max(samples, key=lambda s: s["bytes"])
    print(
        json.dumps(
            {
                "n": len(secs),
                "p50": statistics.median(secs),
                "p95": p95,
                "max": secs[-1],
                "largest_bytes": biggest["bytes"],
                "largest_seconds": biggest["seconds"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
