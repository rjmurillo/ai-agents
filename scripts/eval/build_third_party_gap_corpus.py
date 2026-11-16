#!/usr/bin/env python3
"""Rebuild the third-party review gap corpora from a mined pull request dump.

Reads the dump that ``mine_third_party_review_findings.py`` wrote and the
model-drafted labels in ``evals/third-party-review-gap/labels.jsonl``, then
writes ``findings.jsonl``, ``replay-corpus.json`` and
``io-portability-corpus.json``. ``--check`` writes nothing and exits 1 when a
rebuilt file differs from the committed one. ``--stats`` prints the counts the
README cites. The pull request commits must be present locally
(``git fetch origin pull/<n>/head`` for each mined pull request).

Method and limits: ``evals/third-party-review-gap/README.md``.

Exit codes:
    0  ok
    1  --check found a rebuilt file that differs from the committed one
    2  config error (unreadable dump or labels, missing label)
    3  git failed while computing --stats
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _third_party_gap_build as build  # noqa: E402
import check_io_portability as io_check  # noqa: E402

OUT_DIR = "evals/third-party-review-gap"
# Revisions whose fixing commit edited the reviewer prompt the replay loads, so
# `eval_third_party_gap_replay.py --validate-corpus` finds fix lines in the prompt.
LEAKING_REVISIONS = frozenset({"TG002", "TG083", "TG223"})
REPLAY_RULE = (
    "Every admitted finding in findings.jsonl whose path is in the pull request diff (merge base "
    "to reviewed commit), whose diff is at most 110000 characters, and whose thread has a line, "
    "grouped by reviewed revision. Split follows findings.jsonl (heldout when PR >= 7066)."
)
IO_RULE = (
    "Cursor Bugbot review threads on PRs #6110 to #7380 whose body names the learned rule "
    "'subprocess.run with text=True must include encoding', 'Tests using symlinks must "
    "pytest.skip', or 'Path.read_text/write_text must include encoding', that the author fixed "
    "(reply cites a fix commit) or resolved, with a line and a reviewed commit. Split: heldout "
    "when PR >= 7066."
)


def git_run(args: tuple[str, ...]) -> str | None:
    """Git stdout, or None on a non-zero exit, a timeout, or a missing git binary."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
            cwd=str(REPO_ROOT),
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return result.stdout if result.returncode == 0 else None


def one_record_per_line(obj: dict[str, Any], list_key: str) -> str:
    """JSON with the header keys on their own lines and one list record per line."""
    lines = ["{"]
    lines += [
        f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},"
        for k, v in obj.items()
        if k != list_key
    ]
    items = obj[list_key]
    lines.append(f" {json.dumps(list_key)}: [")
    lines += [
        "  " + json.dumps(x, ensure_ascii=False) + ("," if i < len(items) - 1 else "")
        for i, x in enumerate(items)
    ]
    return "\n".join([*lines, " ]", "}"]) + "\n"


def load_labels(path: Path) -> dict[str, dict[str, Any]]:
    labels = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            labels[row["id"]] = row
    return labels


def build_all(dump: dict[str, Any], labels: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prs = dump["pull_requests"]
    base_of = {p["number"]: p["baseRefOid"] for p in prs}
    threads = build.bot_threads(prs)
    funnel: Counter[str] = Counter(bot_threads=len(threads))
    admitted = []
    for row in threads:
        if row["disposition"] != "accepted":
            continue
        funnel["accepted"] += 1
        outcome, kept = build.admit(row, base_of[row["pr"]], git_run)
        funnel[outcome] += 1
        if kept is not None:
            admitted.append(kept)
    cutoff = build.heldout_cutoff([a["pr"] for a in admitted])
    for a in admitted:
        a["split"] = "heldout" if a["pr"] >= cutoff else "derive"
    rows = build.finding_rows(admitted, labels)
    by_id = {a["id"]: a for a in admitted}
    full = [{**by_id[r["id"]], **r} for r in rows]
    titles = {p["number"]: p.get("title", "") for p in prs}
    revisions = build.replay_revisions(full, titles, set(LEAKING_REVISIONS))
    heads = {p["number"]: p["headRefOid"] for p in prs}
    io = build.io_rows(threads, heads, base_of, cutoff, git_run)
    return {
        "threads": threads,
        "funnel": dict(funnel),
        "cutoff": cutoff,
        "findings": rows,
        "replay": {
            "schema_version": 1,
            "selection": {
                "rule": REPLAY_RULE,
                "source": "findings.jsonl",
                "excluded": {
                    "rule": "A revision is dropped when --validate-corpus finds a fixing commit's "
                    "added lines in the reviewer prompt, because the fix edited the reviewer "
                    "contract or agent template the replay loads.",
                    "ids": sorted(LEAKING_REVISIONS),
                },
            },
            "revisions": revisions,
        },
        "io": {
            "schema_version": 1,
            "selection": {"rule": IO_RULE, "mined_on": "2026-11-15"},
            "rows": io,
        },
    }


def render(built: dict[str, Any]) -> dict[str, str]:
    return {
        "findings.jsonl": "".join(
            json.dumps(r, ensure_ascii=False) + "\n" for r in built["findings"]
        ),
        "replay-corpus.json": one_record_per_line(built["replay"], "revisions"),
        "io-portability-corpus.json": one_record_per_line(built["io"], "rows"),
    }


def stats(dump: dict[str, Any], built: dict[str, Any]) -> dict[str, Any]:
    """The README counts that are not a property of one corpus file."""
    prs = dump["pull_requests"]
    rules = Counter(t["learned_rule"] is not None for t in built["threads"] if t["bot"] == "cursor")
    marker = re.compile(r"Reviewed-By:\s*/review@")
    revisions: dict[tuple[str, str], int] = Counter()
    for f in built["findings"]:
        revisions[(f["merge_base"], f["commit"])] += 1
    marked = Counter[str]()
    for (base, head), count in revisions.items():
        log = git_run(("log", "--format=%B", f"{base}..{head}"))
        if log is None:
            raise ValueError(f"git log {base}..{head} failed")
        key = "marker" if marker.search(log) else "no_marker"
        marked[f"{key}_revisions"] += 1
        marked[f"{key}_findings"] += count
    return {
        "doc_findings_on_added_lines": doc_on_added_lines(built["findings"]),
        "funnel": built["funnel"],
        "heldout_cutoff_pr": built["cutoff"],
        "cursor_learned_rule_threads": rules[True],
        "review_marker": dict(marked),
        "precision_heldout": precision(prs, built["cutoff"]),
    }


DOC_LINE_WINDOW = 2


def doc_on_added_lines(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Doc-accuracy findings whose line is within DOC_LINE_WINDOW of a line the PR added."""
    docs = [r for r in rows if r["defect_class"] == "doc-accuracy"]
    on_added = 0
    for r in docs:
        added = io_check.added_line_numbers(REPO_ROOT, r["merge_base"], r["commit"]).get(
            r["path"], set()
        )
        on_added += any(abs(line - (r["line"] or 0)) <= DOC_LINE_WINDOW for line in added)
    return {"doc_accuracy": len(docs), "within_window": on_added, "window": DOC_LINE_WINDOW}


def precision(prs: list[dict[str, Any]], cutoff: int) -> dict[str, Any]:
    """Shipped-mode flags on every held-out merged pull request: added lines, mirrors skipped."""
    flagged: Counter[int] = Counter()
    rules: Counter[str] = Counter()
    examined = 0
    for pr in prs:
        if pr["number"] < cutoff or pr.get("state") != "MERGED":
            continue
        head = pr["headRefOid"]
        base = (git_run(("merge-base", pr["baseRefOid"], head)) or "").strip()
        if not base or git_run(("cat-file", "-e", f"{head}^{{commit}}")) is None:
            continue
        examined += 1
        added = io_check.added_line_numbers(REPO_ROOT, base, head)
        for path, lines in added.items():
            if not path.endswith(".py") or io_check.is_skipped_path(path):
                continue
            source = git_run(("show", f"{head}:{path}"))
            if source is None:
                raise ValueError(f"git show {head}:{path} failed for a path the diff listed")
            for v in io_check.scan_source(path, source):
                if any(v.spans(line) for line in lines):
                    flagged[pr["number"]] += 1
                    rules[v.rule] += 1
    return {
        "merged_prs_examined": examined,
        "prs_flagged": len(flagged),
        "flags": sum(flagged.values()),
        "by_rule": dict(rules),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dump", type=Path, required=True, help="miner output JSON")
    parser.add_argument("--labels", type=Path, default=REPO_ROOT / OUT_DIR / "labels.jsonl")
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / OUT_DIR)
    parser.add_argument("--check", action="store_true", help="compare, write nothing")
    parser.add_argument("--stats", action="store_true", help="print the README counts")
    args = parser.parse_args(argv)
    try:
        dump = json.loads(args.dump.read_text(encoding="utf-8"))
        built = build_all(dump, load_labels(args.labels))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    files = render(built)
    if args.stats:
        try:
            print(json.dumps(stats(dump, built), indent=2))
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 3
    if args.check:
        stale = []
        for name, text in files.items():
            target = args.out_dir / name
            current = target.read_text(encoding="utf-8") if target.exists() else None
            if current != text:
                stale.append(name)
        for name in stale:
            print(f"DIFFERS: {name}", file=sys.stderr)
        print(f"{len(stale)} of {len(files)} corpus file(s) differ from a rebuild")
        return 1 if stale else 0
    for name, text in files.items():
        (args.out_dir / name).write_text(text, encoding="utf-8")
    print(json.dumps({"written": sorted(files), "funnel": built["funnel"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
