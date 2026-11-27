"""The whole pipeline end to end, through each CLI's main(argv).

Plan M1-T7 to M1-T15, review round 1 QA ask (still open at round 2).

    sample -> sheet -> fill labels -> merge-labels -> predict (fake transport) -> score

Every step runs on the previous step's output file in tmp_path. Unit tests prove each piece
alone; this proves the files one step writes are the files the next step can read, that the
labeler's sheet stays blind, and that the score report describes exactly the files it read.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.eval.actionability_io import head_sha, load_jsonl, write_jsonl
from tests.eval._actionability_arms_test_support import FakeCallApi, aa, install_call_api
from tests.eval._actionability_corpus_test_support import (
    cc,
    make_node,
    make_pr,
    make_thread,
    write_prs,
)

pytestmark = pytest.mark.usefixtures("freeze_actionability_clock")

_REVIEWERS = ["alice", "bob", "carol"]
_SHEET_KEYS = {"id", "path", "diff_hunk", "body", "label"}
_BAND_COUNT, _OUTSIDE_COUNT, _DEV_COUNT = 30, 10, 10
_HELDOUT = _BAND_COUNT - _DEV_COUNT


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)


def _pr_nodes() -> list[dict[str, Any]]:
    """40 PRs with one in-band comment each, and 12 PRs with one clearly severe comment each."""
    prs = []
    for i in range(40):
        node = make_node(f"PRRC_B{i:02d}", f"Consider a helper here {i}", login=_REVIEWERS[i % 3])
        prs.append(make_pr(i + 1, make_thread(node)))
    for i in range(12):
        body = f"Critical security vulnerability: injection {i}"
        node = make_node(f"PRRC_O{i:02d}", body, login=_REVIEWERS[i % 3])
        prs.append(make_pr(100 + i, make_thread(node)))
    return prs


def _run(argv: list[str]) -> int:
    return aa.main(argv) if argv[0] in {"predict", "score"} else cc.main(argv)


class TestPipeline:
    def test_sample_to_score_through_every_cli(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Each step exits 0 on the previous step's file, and the final report adds up."""
        prs = write_prs(tmp_path / "prs.json", _pr_nodes())
        corpus, sheet = tmp_path / "corpus.jsonl", tmp_path / "sheet.jsonl"
        merged, preds = tmp_path / "labeled.jsonl", tmp_path / "predictions.jsonl"
        report_path = tmp_path / "report.json"

        # 1. sample
        sample = ["sample", "--prs", str(prs), "--output", str(corpus)]
        sample += ["--band-count", str(_BAND_COUNT), "--outside-count", str(_OUTSIDE_COUNT)]
        assert _run([*sample, "--dev-count", str(_DEV_COUNT)]) == 0
        sampled = load_jsonl(corpus) or []
        heldout_ids = sorted(r["id"] for r in sampled if r["split"] == "heldout")
        assert len(heldout_ids) == _HELDOUT
        assert {r["split"] for r in sampled} == {"dev", "heldout", "outside"}

        # 2. sheet, and the labeler sees only the allowlisted fields
        assert _run(["sheet", "--corpus", str(corpus), "--output", str(sheet)]) == 0
        blank = load_jsonl(sheet) or []
        assert len(blank) == len(sampled)
        assert all(set(row) == _SHEET_KEYS and row["label"] is None for row in blank)
        assert [r["id"] for r in blank] != [r["id"] for r in sampled]

        # 3. fill the labels: alternate, with one heldout row marked unsure
        unsure_id = heldout_ids[0]
        filled = []
        for index, row in enumerate(sorted(blank, key=lambda r: r["id"])):
            label = "actionable" if index % 2 == 0 else "not_actionable"
            filled.append({**row, "label": "unsure" if row["id"] == unsure_id else label})
        write_jsonl(sheet, filled)

        # 4. merge-labels
        merge = ["merge-labels", "--corpus", str(corpus), "--sheet", str(sheet)]
        assert _run([*merge, "--output", str(merged)]) == 0
        labeled = load_jsonl(merged) or []
        assert [r["id"] for r in labeled] == [r["id"] for r in sampled]
        assert all(r["label"] is not None for r in labeled)
        assert {r["pr_number"] for r in labeled} == {r["pr_number"] for r in sampled}

        # 5. predict on the heldout split with a fake transport
        fake = install_call_api(monkeypatch, FakeCallApi())
        predict = ["predict", "--corpus", str(merged), "--split", "heldout"]
        predict += ["--provider", "fake", "--model", "fake-model", "--output", str(preds)]
        assert _run(predict) == 0
        records = load_jsonl(preds) or []
        assert sorted(r["id"] for r in records) == heldout_ids
        assert {r["status"] for r in records} == {"ok"}
        assert len(fake.calls) == _HELDOUT

        # 6. score
        capsys.readouterr()
        score = ["score", "--corpus", str(merged), "--predictions", str(preds)]
        score += ["--output", str(report_path), "--bootstrap", "300", "--seed", "3"]
        assert _run(score) == 0
        report = json.loads(report_path.read_text(encoding="utf-8"))

        # the verdict exists and the report describes the files it read
        assert report["verdict"] in {"pass", "fail", "inconclusive"}
        assert "verdict" in capsys.readouterr().out
        assert report["corpus_sha256"] == hashlib.sha256(merged.read_bytes()).hexdigest()
        assert report["predictions_sha256"] == hashlib.sha256(preds.read_bytes()).hexdigest()
        assert report["corpus_seed"] == 20261124
        assert report["corpus_head_sha"] == head_sha()
        assert report["model"] == "fake-model"
        assert report["provider"] == "fake"

        # every heldout band row got a prediction, and dev and outside rows got none
        assert report["predictions"]["missing"] == 0
        assert report["predictions"]["ok"] == _HELDOUT - 1
        assert report["labels"]["unsure_dropped"] == 1
        assert report["heldout_band"]["n"] == _HELDOUT - 1
        assert report["bootstrap_unit"] == "pr"
        assert report["n_clusters"] == _HELDOUT - 1
        predicted = {r["id"] for r in records}
        assert not predicted & {r["id"] for r in labeled if r["split"] != "heldout"}

    def test_the_dev_guard_is_part_of_the_chain(self, tmp_path: Path) -> None:
        """A dev count that takes every band row stops at sample, before anything is written."""
        prs = write_prs(tmp_path / "prs.json", _pr_nodes())
        corpus = tmp_path / "corpus.jsonl"
        argv = ["sample", "--prs", str(prs), "--output", str(corpus)]
        argv += ["--band-count", "10", "--outside-count", "5", "--dev-count", "10"]

        assert _run(argv) == 2
        assert not corpus.exists()
