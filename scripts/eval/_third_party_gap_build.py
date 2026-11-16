"""Pure steps that turn a mined pull request dump into the third-party gap corpora.

No I/O except through an injected git callable. The CLI that reads the dump
and writes the files is ``build_third_party_gap_corpus.py``. Method:
``evals/third-party-review-gap/README.md``.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

import _third_party_review_findings as findings

GitRun = Callable[[tuple[str, ...]], str | None]

# A reply that opens with one of these words accepts the finding.
ACCEPT = re.compile(
    r"^\W*(\[COMPLETE\]\s*)?"
    r"(fixed|addressed|confirmed|done|applied|good catch|valid|agreed|correct)\b",
    re.IGNORECASE,
)
REJECT = re.compile(
    r"(false positive|not changed|no change|won.t fix|not a bug|out of scope|/fp\b|/ar\b|declin"
    r"|intentional|by design|not applicable|already|disagree|generated copy|is generated"
    r"|not reproduc)",
    re.IGNORECASE,
)
FIXED_WITH_SHA = re.compile(r"\b(fixed|addressed)\b[^.\n]{0,40}\b[0-9a-f]{7,40}\b", re.IGNORECASE)
FIX_SHA = re.compile(
    r"\b(?:fixed|addressed|applied)\b[^.\n]{0,60}?\b([0-9a-f]{7,40})\b", re.IGNORECASE
)
BOT_ADDRESSED = ("Addressed in commit", "✅ Addressed")
LEARNED_RULE = "Triggered by learned rule:"
HELDOUT_SHARE = 0.35
MAX_REPLAY_DIFF_CHARS = 110_000
IO_RULES = {
    "subprocess.run with text=True": "subprocess-text-encoding",
    "Tests using symlinks": "unguarded-symlink",
    "Path.read_text/write_text": "file-text-encoding",
}
LABEL_KEYS = ("defect_class", "theme", "context_needed", "mechanical", "summary")
FINDING_KEYS = (
    "id", "bot", "pr", "path", "line", "commit", "merge_base", "fix", "split", "url",
    *LABEL_KEYS, "diff_chars_all",
)  # fmt: skip


def clean(body: str) -> str:
    """Bot comment text without HTML comments, folded details, tags, or blank runs."""
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"<details>.*?</details>", "", body, flags=re.S)
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"\n{2,}", "\n", body)
    return html.unescape(body).strip()


def learned_rule(body: str) -> str | None:
    """The Cursor Bugbot learned-rule name a finding cites, if any."""
    start = body.find(LEARNED_RULE)
    if start < 0:
        return None
    window = body[start + len(LEARNED_RULE) : start + 200]
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", window))
    return text.split(" Reviewed by")[0].strip()


def disposition(body: str, replies: list[str], resolved: bool) -> str:
    """accepted, rejected, resolved-silent, or unclear, from the author's replies."""
    if any(FIXED_WITH_SHA.search(r) or ACCEPT.search(r) for r in replies):
        return "accepted"
    if any(marker in body for marker in BOT_ADDRESSED):
        return "accepted"
    if any(REJECT.search(r) for r in replies):
        return "rejected"
    if resolved and not replies:
        return "resolved-silent"
    return "unclear"


def _login(node: dict[str, Any]) -> str:
    author = node.get("author")
    login = author.get("login") if isinstance(author, dict) else None
    return login if isinstance(login, str) else ""


def bot_threads(pull_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every bot-opened thread in dump order, with a stable ``T0001`` id."""
    rows: list[dict[str, Any]] = []
    for pr in pull_requests:
        for thread in pr.get("reviewThreads", []):
            comments = thread.get("comments") or []
            if not comments:
                continue
            bot = findings.bot_name(_login(comments[0]))
            if bot is None:
                continue
            replies = [
                c.get("body") or ""
                for c in comments[1:]
                if _login(c) and findings.bot_name(_login(c)) is None
            ]
            body = comments[0].get("body") or ""
            commit = comments[0].get("originalCommit")
            rows.append(
                {
                    "id": f"T{len(rows) + 1:04d}",
                    "bot": bot,
                    "pr": pr["number"],
                    "path": thread.get("path"),
                    "line": thread.get("originalLine") or thread.get("line"),
                    "commit": commit.get("oid") if isinstance(commit, dict) else None,
                    "disposition": disposition(body, replies, bool(thread.get("isResolved"))),
                    "first_reply": clean(replies[0])[:600] if replies else "",
                    "learned_rule": learned_rule(body),
                    "url": comments[0].get("url"),
                }
            )
    return rows


def admit(row: dict[str, Any], base_oid: str, git: GitRun) -> tuple[str, dict[str, Any] | None]:
    """Admission step for one accepted thread: ``(outcome, admitted row or None)``."""
    match = FIX_SHA.search(row["first_reply"])
    if match is None:
        return "no_sha", None
    resolved = git(("rev-parse", "--verify", "--quiet", match.group(1) + "^{commit}"))
    if not resolved:
        return "fix_unresolved", None
    fix = resolved.strip()
    if git(("cat-file", "-e", f"{row['commit'] or 'x'}^{{commit}}")) is None:
        return "reviewed_missing", None
    touched = (git(("show", "--format=", "--name-only", fix)) or "").split()
    if row["path"] not in touched:
        return "fix_misses_path", None
    merge_base = (git(("merge-base", base_oid, row["commit"])) or "").strip()
    if not merge_base:
        return "no_merge_base", None
    if git(("merge-base", "--is-ancestor", row["commit"], fix)) is None:
        return "fix_not_descendant", None
    files = (git(("diff", "--name-only", merge_base, row["commit"])) or "").split()
    diff = git(("diff", merge_base, row["commit"])) or ""
    admitted = {
        **row,
        "fix": fix,
        "merge_base": merge_base,
        "path_in_diff": row["path"] in files,
        "diff_chars_all": len(diff),
    }
    return "admitted", admitted


def heldout_cutoff(prs: list[int]) -> int:
    """Smallest PR number such that PRs at or above it hold HELDOUT_SHARE of the rows."""
    if not prs:
        raise ValueError("no admitted findings; nothing to split")
    counts = Counter(prs)
    total, running = len(prs), 0
    for number in sorted(counts, reverse=True):
        running += counts[number]
        if running >= HELDOUT_SHARE * total:
            return number
    return min(counts)


def finding_rows(
    admitted: list[dict[str, Any]], labels: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """``findings.jsonl`` rows: admitted threads joined to their model-drafted labels."""
    missing = [a["id"] for a in admitted if a["id"] not in labels]
    if missing:
        raise ValueError(f"no label for {len(missing)} admitted thread(s), first {missing[0]}")
    rows = [{**a, **{k: labels[a["id"]].get(k) for k in LABEL_KEYS}} for a in admitted]
    return [
        {k: r.get(k) for k in FINDING_KEYS} for r in sorted(rows, key=lambda r: (r["pr"], r["id"]))
    ]


def replay_revisions(
    rows: list[dict[str, Any]], titles: dict[int, str], exclude: set[str]
) -> list[dict[str, Any]]:
    """Group replayable findings by reviewed revision, ids ``TG001`` in (pr, commit) order."""
    ok = [
        r
        for r in rows
        if r["path_in_diff"] and r["diff_chars_all"] <= MAX_REPLAY_DIFF_CHARS and r["line"]
    ]
    groups: dict[tuple[int, str, str], list[dict[str, Any]]] = {}
    for r in sorted(ok, key=lambda r: (r["pr"], r["commit"], r["id"])):
        groups.setdefault((r["pr"], r["merge_base"], r["commit"]), []).append(r)
    revisions = []
    for index, ((pr, base, head), items) in enumerate(groups.items(), 1):
        revisions.append(
            {
                "id": f"TG{index:03d}",
                "pr": pr,
                "title": titles.get(pr, ""),
                "base": base,
                "head": head,
                "split": items[0]["split"],
                "defects": [
                    {
                        "thread": a["id"],
                        "bot": a["bot"],
                        "path": a["path"],
                        "line": a["line"],
                        "fix": a["fix"],
                        "defect_class": a["defect_class"],
                        "theme": a["theme"],
                        "context": a["context_needed"],
                        "summary": a["summary"],
                    }
                    for a in items
                ],
            }
        )
    return [r for r in revisions if r["id"] not in exclude]


def io_rows(
    threads: list[dict[str, Any]],
    heads: dict[int, str],
    bases: dict[int, str],
    cutoff: int,
    git: GitRun,
) -> list[dict[str, Any]]:
    """Bugbot learned-rule findings for the three mechanical rules, fixed or silently resolved."""
    out = []
    for t in threads:
        name = t["learned_rule"] or ""
        rule = next((v for k, v in IO_RULES.items() if name.startswith(k)), None)
        if rule is None or t["disposition"] not in ("accepted", "resolved-silent"):
            continue
        if not t["line"] or not t["commit"]:
            continue
        merge_base = (git(("merge-base", bases[t["pr"]], t["commit"])) or "").strip()
        out.append(
            {
                "thread": t["id"],
                "url": t["url"],
                "pr": t["pr"],
                "rule": rule,
                "path": t["path"],
                "line": t["line"],
                "reviewed": t["commit"],
                "merge_base": merge_base or None,
                "final_head": heads[t["pr"]],
                "disposition": t["disposition"],
                "split": "heldout" if t["pr"] >= cutoff else "derive",
            }
        )
    return out
