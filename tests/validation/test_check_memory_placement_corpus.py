"""Self-apply test: run check_memory_placement.py over the real memory corpus.

Issue #5828. The synthetic repositories in the sibling tests prove the rules;
this one proves the thresholds against ``.serena/memories/`` itself. Two pins:

* zero failing files at HEAD, so the check never reds a clean checkout;
* the flagged set stays inside a bound. A signal or threshold change that
  flags a tenth of the corpus more (about 100 files) fails here, loudly,
  instead of reaching every contributor as a pre-commit and CI failure.

Measured on the corpus when this test was written: 990 files examined, 159
normative, 187 suspect, 36 suppressed. The ceilings leave headroom for
ordinary drift; lower them when the placement migrations (#5392 to #5394) land.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = _REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_memory_placement as checker

_CORPUS = _REPO_ROOT / ".serena" / "memories"
_NORMATIVE_CEILING = 170
_SUSPECT_CEILING = 220
_SUPPRESSED_CEILING = 60
_EXAMINED_FLOOR = 900


@pytest.fixture(scope="module")
def corpus_report() -> tuple[int, dict]:
    """Run the check once over the live corpus and return (exit code, report)."""
    if not _CORPUS.is_dir():
        pytest.skip("memory corpus is not checked out")
    cwd = Path.cwd()
    os.chdir(_REPO_ROOT)
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            code = checker.main(["--ci", "--json", "--path", ".serena/memories", "--base", "HEAD"])
    finally:
        os.chdir(cwd)
    return code, json.loads(buffer.getvalue())


def test_live_corpus_has_zero_failing_files(corpus_report):
    code, report = corpus_report

    failing = [
        f["path"]
        for f in report["findings"]
        if f["reported_label"] == "normative" and (f["is_new"] or f["rose"])
    ]
    assert failing == []
    assert report["failing"] == 0
    assert code == 0


def test_live_corpus_is_still_being_examined(corpus_report):
    _, report = corpus_report

    assert report["examined"] >= _EXAMINED_FLOOR


@pytest.mark.parametrize(
    ("label", "ceiling"),
    [
        ("normative", _NORMATIVE_CEILING),
        ("suspect", _SUSPECT_CEILING),
        ("suppressed", _SUPPRESSED_CEILING),
    ],
)
def test_live_corpus_flag_counts_stay_inside_the_bound(corpus_report, label, ceiling):
    _, report = corpus_report

    assert report["counts"][label] <= ceiling, (
        f"{report['counts'][label]} {label} files exceeds the {ceiling} bound: "
        "a threshold or signal change widened the flagged set"
    )
