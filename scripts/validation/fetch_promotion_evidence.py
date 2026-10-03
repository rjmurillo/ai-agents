#!/usr/bin/env python3
"""Download the promotion candidate's evidence, keeping only runs that pass provenance.

ADR-113 decisions 2 and 5, issue #5636. A thin command over
``scripts/validation/promotion_fetch.py``: it reads the applicability table from
the default-branch checkout, asks the GitHub API (through ``gh``, which carries
``GH_TOKEN``) for the candidate commit's runs, and writes one evidence file per
accepted artifact into ``--evidence-dir`` for ``promotion_gate.py`` to read.

Exit codes (ADR-035): 0 the fetch ran, whatever it accepted; 2 invalid arguments
or applicability table; 3 GitHub could not answer. Rejected runs are logged and
exit 0, because the gate counts a validator with no accepted evidence as missing
and says so in the manifest. A missing answer from GitHub is not an empty answer,
so that exits 3.
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

from scripts.validation.promotion_applicability import (  # noqa: E402
    ApplicabilityError,
    load_applicability,
)
from scripts.validation.promotion_exemption import GitDiffSource  # noqa: E402
from scripts.validation.promotion_fetch import (  # noqa: E402
    GhCliReader,
    GitHubApiError,
    GitHubReader,
    fetch_build_evidence,
    fetch_verified_evidence,
)

EXIT_OK, EXIT_CONFIG, EXIT_EXTERNAL = 0, 2, 3


def _run_id(text: str) -> int:
    """A run id, or empty for none. A workflow passes an empty string when it has no build run."""
    if text == "":
        return 0
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive integer or empty") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer or empty")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--default-branch", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=_PROJECT_ROOT)
    parser.add_argument(
        "--build-run-id",
        type=_run_id,
        default=0,
        help="the entry workflow run holding the build-tier evidence; empty fetches none",
    )
    return parser


def _fail(label: str, message: str, code: int) -> int:
    print(f"[{label}] fetch promotion evidence: {json.dumps(message)}", file=sys.stderr)
    return code


def main(argv: Sequence[str] | None = None, reader: GitHubReader | None = None) -> int:
    """CLI entry point. ``reader`` is a test seam; production uses the ``gh`` CLI."""
    args = _parser().parse_args(argv)
    try:
        entries = load_applicability(args.repo_root)
        dispositions = fetch_verified_evidence(
            reader or GhCliReader(),
            repo=args.repo,
            candidate_sha=args.candidate_sha,
            default_branch=args.default_branch,
            entries=entries,
            evidence_dir=args.evidence_dir,
            exemption_source=GitDiffSource(args.repo_root),
        )
        if args.build_run_id:
            dispositions += fetch_build_evidence(
                reader or GhCliReader(),
                repo=args.repo,
                run_id=args.build_run_id,
                candidate_sha=args.candidate_sha,
                default_branch=args.default_branch,
                entries=entries,
                evidence_dir=args.evidence_dir,
            )
    except (ApplicabilityError, ValueError) as exc:
        return _fail("FAIL", f"{type(exc).__name__}: {exc}", EXIT_CONFIG)
    except GitHubApiError as exc:
        return _fail("BLOCKED", str(exc), EXIT_EXTERNAL)
    except OSError as exc:
        return _fail("BLOCKED", f"cannot write evidence: {type(exc).__name__}", EXIT_EXTERNAL)
    for item in dispositions:
        print(item.line())
    accepted = sum(1 for item in dispositions if item.accepted)
    print(f"promotion evidence: {accepted} accepted, {len(dispositions) - accepted} rejected")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
