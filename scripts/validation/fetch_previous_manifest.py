#!/usr/bin/env python3
"""Download the previous promoted manifest from a GitHub Release, if one exists.

ADR-113 Resolved Question 3, issue #5636. A thin command over
``scripts/validation/promotion_baseline.py``. It writes
``<output-dir>/promotion-manifest.json`` and prints the tag it came from, or
writes ``no-baseline.json`` and prints that there is none. A first promotion has no
baseline, and the marker lets the gate tell that from a step that never ran.

Exit codes (ADR-035): 0 a baseline was written or none exists; 2 invalid
arguments or an asset that is not a promoted manifest; 3 GitHub could not answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.promotion_baseline import fetch_baseline  # noqa: E402
from scripts.validation.promotion_fetch import (  # noqa: E402
    GhCliReader,
    GitHubApiError,
    GitHubReader,
)
from scripts.validation.promotion_findings import ManifestError  # noqa: E402
from scripts.validation.promotion_provenance import is_repository_name  # noqa: E402

EXIT_OK, EXIT_CONFIG, EXIT_EXTERNAL = 0, 2, 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--current-tag", default="", help="the release being promoted, never its own baseline"
    )
    return parser


def _fail(label: str, message: str, code: int) -> int:
    print(f"[{label}] fetch previous manifest: {json.dumps(message)}", file=sys.stderr)
    return code


def main(argv: Sequence[str] | None = None, reader: GitHubReader | None = None) -> int:
    """CLI entry point. ``reader`` is a test seam; production uses the ``gh`` CLI."""
    args = _parser().parse_args(argv)
    if not is_repository_name(args.repo):
        return _fail("FAIL", "repo must be owner/name", EXIT_CONFIG)
    try:
        chosen = fetch_baseline(
            reader or GhCliReader(),
            repo=args.repo,
            exclude_tag=args.current_tag,
            output_dir=args.output_dir,
        )
    except ManifestError as exc:
        return _fail("FAIL", str(exc), EXIT_CONFIG)
    except GitHubApiError as exc:
        return _fail("BLOCKED", str(exc), EXIT_EXTERNAL)
    except OSError as exc:
        return _fail("BLOCKED", f"cannot write: {type(exc).__name__}", EXIT_EXTERNAL)
    if chosen is None:
        print("previous manifest: none (first promotion)")
    else:
        print(f"previous manifest: release {json.dumps(chosen.tag)} asset {chosen.asset_id}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
