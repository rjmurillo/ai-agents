#!/usr/bin/env python3
"""Replay real docs review findings through the authoring gates.

Only this runner's worktrees and refs are removed. They use a unique prefix.
No historical code executes. The current gate reads each historical tree.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validation import check_agent_skill_docs as gate  # noqa: E402

CORPUS = ROOT / "evals/docs-review-catch-rate/agent_skill_docs/corpus.json"


def command(root: Path, *args: str) -> str:
    """Run a bounded command, failing rather than scoring an external error."""
    result = subprocess.run(
        args,
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited {result.returncode}: {result.stderr[-3000:]}")
    return result.stdout.strip()


def source_members(root: Path, ref: str) -> dict[str, set[str]]:
    """List source identities at a revision without reading generated mirrors."""
    listing = command(
        root, "git", "ls-tree", "-r", "--name-only", ref, "--", *gate.SKILL_TREES, gate.AGENT_TREE
    )
    members: dict[str, set[str]] = {"skills": set(), "agents": set()}
    for path in listing.splitlines():
        for tree in gate.SKILL_TREES:
            match = re.fullmatch(re.escape(tree) + r"/([^/]+)/SKILL\.md", path)
            if match:
                members["skills"].add(match[1])
        match = re.fullmatch(re.escape(gate.AGENT_TREE) + r"/([^/]+)\.shared\.md", path)
        if match:
            members["agents"].add(match[1])
    return members


def classify(finding: gate.Finding, *, freshness: bool = False) -> dict[str, Any]:
    """Normalize gate findings for deterministic file/class/line scoring."""
    message = finding.message
    if freshness:
        defect = "stale-page"
    elif "has no page" in message:
        defect = "missing-page"
    elif message.startswith("page has no "):
        defect = "orphan-page"
    elif message.startswith("no table row"):
        defect = "missing-row"
    elif message.startswith("row links missing page"):
        defect = "broken-row"
    else:
        defect = "section-order"
    return {"file": finding.path, "defect_class": defect, "line": 1, "message": message}


def attributable(finding: dict[str, Any], affected: dict[str, set[str]]) -> bool:
    """Keep structural findings only for changed source membership."""
    path = Path(str(finding["file"]))
    kind = path.parent.name
    if path.stem != "README":
        return path.stem in affected.get(kind, set())
    message = str(finding["message"])
    return any(f" {name}.md" in message for name in affected.get(kind, set()))


def matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Match the same file and defect class, within three lines."""
    return (
        expected["file"] == actual["file"]
        and expected["defect_class"] == actual["defect_class"]
        and abs(int(str(expected["line"])) - int(str(actual["line"]))) <= 3
    )


def inspect_tree(tree: Path, base: str) -> dict[str, Any]:
    """Run both pre-PR adapters, capturing their reports and terminal output."""
    before, after = source_members(tree, base), source_members(tree, "HEAD")
    affected = {kind: before[kind] ^ after[kind] for kind in before}
    config_error = None
    try:
        pages = gate.find_page_findings(tree)
    except gate.ConfigError as exc:
        # Historical PRs can predate the reference-page system itself.
        if any(affected.values()):
            raise RuntimeError(f"Changed sources cannot be scored: {exc}") from exc
        for kind in gate.DOCS:
            readme = f"{gate.DOCS[kind]}/README.md"
            exists = command(tree, "git", "ls-tree", "--name-only", base, "--", readme)
            if not (tree / readme).exists() and exists:
                raise RuntimeError(f"PR removed required {readme}") from exc
        config_error = str(exc)
        pages = gate.Report(examined=0)
    freshness = gate.find_stale_pages(tree, base)
    if freshness is None:
        raise RuntimeError(f"Could not read freshness against {base}")
    output = io.StringIO()
    # Supply the recorded PR base instead of this checkout's default branch.
    with (
        patch.object(gate, "_resolve_default_base_ref", return_value=base),
        patch.object(
            gate,
            "find_page_findings",
            return_value=pages,
            side_effect=gate.ConfigError(config_error) if config_error else None,
        ),
        patch.object(gate, "find_stale_pages", return_value=freshness),
        contextlib.redirect_stdout(output),
        contextlib.redirect_stderr(output),
    ):
        blocking = gate.validate_agent_skill_docs(tree)
        advisory = gate.validate_skill_page_freshness(tree)
    structural = [classify(f) for f in pages.findings]
    included = [f for f in structural if attributable(f, affected)]
    warnings = [classify(f, freshness=True) for f in freshness.findings]
    return {
        "excluded_preexisting_config": config_error,
        "affected_sources": {k: sorted(v) for k, v in affected.items()},
        "findings": included + warnings,
        "excluded_preexisting": [f for f in structural if not attributable(f, affected)],
        "pre_pr_outcomes": [asdict(blocking), asdict(advisory)],
        "output": output.getvalue(),
    }


def replay(root: Path, case: dict[str, Any], repository: str, token: str) -> dict[str, Any]:
    """Fetch one PR and remove its disposable checkout and ref on every exit."""
    number = int(str(case["pr"]))
    metadata = json.loads(
        command(
            root,
            "gh",
            "pr",
            "view",
            str(number),
            "--repo",
            repository,
            "--json",
            "baseRefOid,headRefOid",
        )
    )
    ref = f"refs/docs-review-agent-skill-docs/{token}/{number}"
    tree = Path.home() / "worktrees/ai-agents" / f"docs-review-skill-docs-{token}-{number}"
    created = fetched = False
    try:
        command(root, "git", "fetch", "--no-tags", "origin", f"pull/{number}/head:{ref}")
        fetched = True
        sha = command(root, "git", "rev-parse", "--verify", f"{case['sha'] or ref}^{{commit}}")
        # Reject an unrelated abbreviated SHA, even when another worktree fetched it.
        command(root, "git", "merge-base", "--is-ancestor", sha, ref)
        base_oid = metadata["baseRefOid"]
        command(root, "git", "cat-file", "-e", f"{base_oid}^{{commit}}")
        base = command(root, "git", "merge-base", sha, base_oid)
        command(root, "git", "worktree", "add", "--detach", str(tree), sha)
        created = True
        result: dict[str, Any] = {
            "id": case["id"],
            "pr": number,
            "sha": sha,
            "baseRefOid": base_oid,
            "headRefOid": metadata["headRefOid"],
            "merge_base": base,
            "scope": case["scope"],
        }
        if case["scope"] == "manual":
            result.update({"why": case["why"], "findings": [], "caught": None})
        else:
            inspected = inspect_tree(tree, base)
            result.update(inspected)
            found = inspected["findings"]
            result["caught"] = (
                all(any(matches(e, f) for f in found) for e in case["expected"])
                if case["scope"] == "automated"
                else None
            )
        return result
    finally:
        if created:
            command(root, "git", "worktree", "remove", str(tree))
        if fetched:
            command(root, "git", "update-ref", "-d", ref)


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Count every finding on negatives, including freshness advisories."""
    positives = [r for r in rows if r["scope"] == "automated"]
    negatives = [r for r in rows if r["scope"] == "negative"]
    caught = sum(r["caught"] is True for r in positives)
    false_positives = sum(len(r["findings"]) for r in negatives)
    return {
        "caught": caught,
        "in_scope_positives": len(positives),
        "recall": caught / len(positives) if positives else 0,
        "false_positives": false_positives,
        "negatives": len(negatives),
        "manual": sum(r["scope"] == "manual" for r in rows),
        "passed": caught == len(positives) and false_positives == 0 and len(negatives) == 12,
    }


def main() -> int:
    """Write the receipt. Exit one for a missed positive or a false positive."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    token = uuid.uuid4().hex[:10]
    rows = []
    try:
        for case in corpus["cases"]:
            row = replay(ROOT, case, corpus["repository"], token)
            rows.append(row)
            print(
                f"{case['id']}: {len(row['findings'])} findings, caught={row['caught']}", flush=True
            )
    except (RuntimeError, subprocess.TimeoutExpired, OSError, ValueError, gate.ConfigError) as exc:
        print(f"Replay failed: {exc}", file=sys.stderr)
        return 3
    now = datetime.now(UTC)
    result: dict[str, Any] = {
        "schema_version": 1,
        "run_at": now.isoformat(),
        "corpus_sha256": hashlib.sha256(args.corpus.read_bytes()).hexdigest(),
        "checker_sha256": hashlib.sha256(Path(gate.__file__).read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "checker_revision": command(ROOT, "git", "rev-parse", "HEAD"),
        "summary": score(rows),
        "cases": rows,
    }
    out = args.output or CORPUS.parent / "results" / f"{now.date()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Keep one auditable case per line, below the artifact size ceiling.
    header = json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2)[:-2]
    cases_json = ",\n".join("    " + json.dumps(row) for row in rows)
    out.write_text(header + ',\n  "cases": [\n' + cases_json + "\n  ]\n}\n", encoding="utf-8")
    print(json.dumps(result["summary"]))
    return 0 if result["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
