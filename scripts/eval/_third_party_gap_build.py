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
FIXED_WITH_SHA = re.compile(
    r"\b(fixed|addressed|applied)\b[^.\n]{0,40}\b[0-9a-f]{7,40}\b", re.IGNORECASE
)
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


def disposition(
    body: str, replies: list[str], resolved: bool, accepting: list[str] | None = None
) -> str:
    """accepted, rejected, resolved-silent, or unclear, from the human replies.

    ``accepting`` holds the replies that may accept (the pull request author's);
    it defaults to ``replies``. Any human reply can still reject the finding or
    break its silence.
    """
    accepting = replies if accepting is None else accepting
    # A cited fix commit is the strongest evidence. Short of that, an explicit
    # rejection outranks an opening word: "Confirmed false positive" rejects.
    if any(FIXED_WITH_SHA.search(r) for r in accepting):
        return "accepted"
    if any(REJECT.search(r) for r in replies):
        return "rejected"
    if any(ACCEPT.search(r) for r in accepting) or any(m in body for m in BOT_ADDRESSED):
        return "accepted"
    if resolved and not replies:
        return "resolved-silent"
    return "unclear"


def bot_threads(pull_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every bot-opened thread in dump order, with a stable ``T0001`` id."""
    rows: list[dict[str, Any]] = []
    for pr in pull_requests:
        for thread in pr.get("reviewThreads", []):
            bot = findings.opener_bot(thread)
            if bot is None:
                continue
            comments = thread["comments"]
            # Only the pull request author can accept a finding for the author agent.
            author = findings.author_login(pr)
            humans = findings.human_replies(comments)
            replies = [c.get("body") or "" for c in humans]
            by_author = [c.get("body") or "" for c in humans if findings.author_login(c) == author]
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
                    "disposition": disposition(
                        body, replies, bool(thread.get("isResolved")), accepting=by_author
                    ),
                    "first_reply": clean(by_author[0])[:600] if by_author else "",
                    "learned_rule": learned_rule(body),
                    "url": comments[0].get("url"),
                }
            )
    return rows


def _read(git: GitRun, args: tuple[str, ...]) -> str:
    """Output of a git read whose commits are known to exist; a failure is an error.

    Read as empty text, a failed read would admit a finding with no diff and
    then drop it from the replay corpus without a trace.
    """
    out = git(args)
    if out is None:
        raise RuntimeError(f"git {' '.join(args[:2])} failed on commits that exist")
    return out


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
    touched = _read(git, ("show", "--format=", "--name-only", "-z", fix)).split("\0")
    if row["path"] not in touched:
        return "fix_misses_path", None
    merge_base = (git(("merge-base", base_oid, row["commit"])) or "").strip()
    if not merge_base:
        return "no_merge_base", None
    if git(("merge-base", "--is-ancestor", row["commit"], fix)) is None:
        return "fix_not_descendant", None
    files = _read(git, ("diff", "--name-only", "-z", merge_base, row["commit"])).split("\0")
    diff = _read(git, ("diff", merge_base, row["commit"]))
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
    """``findings.jsonl`` rows: admitted threads joined to their model-drafted labels.

    Ids are ordinal, so a reordered dump would hand a label to another thread.
    Each label names its thread URL, and a label whose URL differs is refused.
    """
    missing = [a["id"] for a in admitted if a["id"] not in labels]
    if missing:
        raise ValueError(f"no label for {len(missing)} admitted thread(s), first {missing[0]}")
    moved = [
        a["id"] for a in admitted if not a.get("url") or labels[a["id"]].get("url") != a["url"]
    ]
    if moved:
        raise ValueError(f"{len(moved)} label(s) name another thread's URL, first {moved[0]}")
    rows = [{**a, **{k: labels[a["id"]].get(k) for k in LABEL_KEYS}} for a in admitted]
    return [
        {k: r.get(k) for k in FINDING_KEYS} for r in sorted(rows, key=lambda r: (r["pr"], r["id"]))
    ]


def replay_revisions(
    rows: list[dict[str, Any]], titles: dict[int, str], exclude: frozenset[tuple[int, str]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Group replayable findings by reviewed revision, ids ``TG001`` in (pr, commit) order.

    ``exclude`` names revisions by (pull request, reviewed head), never by id,
    because ids follow sort order and shift when the mined window changes.
    Returns the kept revisions and the ids of the excluded ones. A key that
    matches no revision raises, so a stale exclusion cannot pass silently.
    """
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
    found = {(r["pr"], r["head"]) for r in revisions}
    if missing := sorted(exclude - found):
        raise ValueError(f"excluded revision(s) not in the replay set: {missing}")
    kept = [r for r in revisions if (r["pr"], r["head"]) not in exclude]
    return kept, [r["id"] for r in revisions if (r["pr"], r["head"]) in exclude]


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
