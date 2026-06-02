#!/usr/bin/env python3
"""Cluster unresolved PR review threads by shared gist before the fix loop.

Phase 0 of the pr-comment-responder workflow. When a bot rescan surfaces many
unresolved threads, several are often the same root cause stated on different
files. PR #1897 round 7 surfaced 17 unresolved threads; 8 were the same
"model_tier=opus contradicts cheaper-tier reviewer claim" framing on different
paths (see .agents/retrospective/2026-05-08-pr-1897-confident-incorrectness-recurrence.md).
Rounds 5 and 6 patched those per-file and did not close the cluster; round 7
retired the framing in the source artifact and the cluster collapsed in one
round.

This module turns the agent-side mental model captured in the global memory
``feedback_bot_thread_clustering.md`` ("4+ threads with the same gist = single
source-of-truth violation, retire the framing once") into a mechanical step.
When a cluster reaches ``CLUSTER_WARNING_THRESHOLD`` threads it is flagged so the
agent fixes the framing root cause before the per-thread fix loop begins.

Pipeline:

1. Fetch unresolved threads with a clustering-specific GraphQL query that
   selects path and first-comment body fields, then map nodes through
   ``github_core.review_threads.transform_review_thread``.
2. Extract a "gist" (a set of load-bearing tokens) from each thread's first
   comment body.
3. Cluster threads whose gists overlap (Jaccard similarity at or above
   ``SIMILARITY_THRESHOLD``) using union-find.
4. Report clusters of ``CLUSTER_WARNING_THRESHOLD`` or more threads, naming the
   source artifact (the file path shared by the most threads in the cluster)
   most likely to be the framing root cause.

The fetch is an integration point; the clustering is pure. ``cluster_threads``
and its helpers take plain dicts (the canonical flat thread shape produced by
``github_core.review_threads.transform_review_thread``) and return plain dicts,
so the algorithm is unit-testable without the network.

Exit codes follow ADR-035:
    0 - Report produced (warnings, if any, are in the JSON; not an error exit)
    2 - Config/usage error (invalid parameters)
    3 - Fetch failed (could not obtain a trustworthy thread snapshot)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# A review thread in the canonical flat shape produced by
# github_core.review_threads.transform_review_thread. Heterogeneous values
# (str, int, None, list), so the value type is object rather than a narrower
# alias; callers read specific keys (first_comment_body, path, thread_id).
Thread = dict[str, object]
# A clustering report or one cluster entry: same heterogeneous-value shape.
Report = dict[str, object]

# Threads with this many members sharing one gist are flagged as a probable
# single-source-of-truth (framing/spec) violation. The value 4 comes directly
# from the issue #1917 acceptance criteria and feedback_bot_thread_clustering.md;
# the round-7 asymmetry cluster had 8 members and must trip the warning.
CLUSTER_WARNING_THRESHOLD = 4

# Two gists are "the same" when their Jaccard similarity (size of token
# intersection over size of token union) is at or above this value. Bots
# paraphrase, so an exact-match rule would split the round-7 asymmetry cluster
# across Copilot/CodeRabbit re-wordings. 0.5 keeps loosely paraphrased restates
# of one finding together while separating genuinely distinct findings.
SIMILARITY_THRESHOLD = 0.5

# A token must carry meaning to count toward overlap. We drop review-comment
# filler ("consider", "should", "please") and structural noise so that the
# load-bearing words (the nouns of the finding: "model", "tier", "opus",
# "contradicts") drive clustering. Tokens shorter than this are also dropped.
_MIN_TOKEN_LENGTH = 4

# Generic review-comment vocabulary that appears across unrelated findings and
# would create false overlap if counted. Lowercased; matched after tokenizing.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "this",
        "that",
        "with",
        "from",
        "have",
        "should",
        "would",
        "could",
        "consider",
        "please",
        "change",
        "changes",
        "comment",
        "review",
        "line",
        "lines",
        "file",
        "code",
        "above",
        "below",
        "here",
        "there",
        "when",
        "then",
        "than",
        "your",
        "into",
        "also",
        "make",
        "uses",
        "used",
        "using",
        "note",
        "needs",
        "need",
        "want",
        "very",
        "more",
        "most",
        "some",
        "they",
        "them",
        "what",
        "which",
        "where",
        "will",
        "does",
        "doesn",
        "isn",
        "instead",
        "rather",
        "suggest",
        "suggestion",
    }
)

# Token = a run of word characters. Markdown punctuation, backticks, and code
# fences are stripped first so "`model_tier`" and "model_tier" tokenize the same.
_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def extract_gist(body: object) -> frozenset[str]:
    """Reduce a comment body to its set of load-bearing tokens.

    Lowercases, splits ``snake_case`` and ``CamelCase`` boundaries into their
    parts (so ``model_tier`` contributes ``model`` and ``tier``), then keeps
    tokens that are at least ``_MIN_TOKEN_LENGTH`` long and not in
    ``_STOPWORDS``. Returns an empty set for an empty or token-poor body; such
    threads cannot join a cluster, which is the safe default (a thread with no
    distinctive words should not be lumped with a real finding).

    ``body`` is typed ``object`` because it comes straight from a JSON thread
    dict whose value type is unconstrained (untrusted input at the boundary).
    A non-string body (None, a number, a malformed list) yields an empty gist
    rather than raising, so one bad thread cannot abort the whole report.
    """
    if not isinstance(body, str) or not body:
        return frozenset()

    body = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
        "_",
        body,
    )
    lowered = body.lower()
    raw_tokens = _TOKEN_RE.findall(lowered)

    gist: set[str] = set()
    for token in raw_tokens:
        for part in token.split("_"):
            if len(part) >= _MIN_TOKEN_LENGTH and part not in _STOPWORDS:
                gist.add(part)
    return frozenset(gist)


def gist_similarity(left: frozenset[str], right: frozenset[str]) -> float:
    """Jaccard similarity between two gists: |intersection| / |union|.

    Returns 0.0 when either gist is empty (an empty gist shares nothing). The
    value is in [0.0, 1.0]; 1.0 means identical token sets.
    """
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    if intersection == 0:
        return 0.0
    union = len(left | right)
    return intersection / union


class _UnionFind:
    """Disjoint-set over thread indices for transitive clustering.

    If thread A is similar to B and B is similar to C, A, B and C land in one
    cluster even when A and C are not directly similar. This matches the
    real-world shape: a paraphrase chain across bot rescans links restates that
    are not pairwise identical.
    """

    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, node: int) -> int:
        root = node
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression keeps repeated finds near-constant time.
        while self._parent[node] != root:
            self._parent[node], node = root, self._parent[node]
        return root

    def union(self, left: int, right: int) -> None:
        self._parent[self.find(left)] = self.find(right)


def _group_indices_by_root(uf: _UnionFind, count: int) -> dict[int, list[int]]:
    groups: dict[int, list[int]] = {}
    for index in range(count):
        groups.setdefault(uf.find(index), []).append(index)
    return groups


def _identify_source_artifact(threads: list[Thread]) -> str | None:
    """Return the file path shared by the most threads in a cluster.

    A cluster whose threads land on one path points at that file as the framing
    root cause. When the cluster spans several files (the round-7 asymmetry
    case: 8 paths, one framing), the most common path is the best single
    pointer only if it has a unique lead. Ties return None so the report does
    not steer the agent into an arbitrary file patch. Returns None when no
    thread in the cluster carries a path.
    """
    counts: dict[str, int] = {}
    order: list[str] = []
    for thread in threads:
        path = thread.get("path")
        # Non-string or empty paths (None, missing, malformed) carry no
        # artifact signal; skip them rather than key a count on a non-str.
        if not isinstance(path, str) or not path:
            continue
        if path not in counts:
            order.append(path)
        counts[path] = counts.get(path, 0) + 1
    if not counts:
        return None
    max_count = max(counts.values())
    winners = [path for path in order if counts[path] == max_count]
    if len(winners) != 1:
        return None
    return winners[0]


def _shared_tokens(threads: list[Thread]) -> list[str]:
    """Tokens present in the gist of every thread in the cluster, sorted.

    These are the load-bearing words that define the cluster's gist; surfacing
    them tells the agent what framing to retire. When transitive linking means
    no single token spans all members, returns the empty list and the caller
    falls back to the per-thread gists.
    """
    gists = [extract_gist(t.get("first_comment_body")) for t in threads]
    gists = [g for g in gists if g]
    if not gists:
        return []
    common = set.intersection(*(set(g) for g in gists))
    return sorted(common)


def _cluster_size(cluster: Report) -> int:
    """Read a cluster's ``size`` as an int for sorting.

    The value is always the ``len(members)`` int stored in ``cluster_threads``;
    the isinstance check narrows the ``object`` value type so the sort key is
    typed and mypy's no-any-return rule is satisfied without a cast.
    """
    size = cluster["size"]
    return size if isinstance(size, int) else 0


def cluster_threads(
    threads: list[Thread],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    warning_threshold: int = CLUSTER_WARNING_THRESHOLD,
) -> Report:
    """Group threads by shared gist and flag large clusters.

    ``threads`` is a list of canonical flat thread dicts (the shape from
    ``transform_review_thread``); each must carry ``first_comment_body`` and
    optionally ``path`` and ``thread_id``. Returns a report dict:

        {
          "thread_count": <int>,
          "cluster_count": <int>,          # clusters at/over warning_threshold
          "warning": <bool>,               # any cluster at/over the threshold
          "clusters": [
            {
              "size": <int>,
              "shared_tokens": [<str>, ...],
              "source_artifact": <str|None>,
              "thread_ids": [<str|None>, ...],
              "paths": [<str|None>, ...]
            },
            ...
          ]
        }

    Only clusters of ``warning_threshold`` or more threads appear in
    ``clusters`` and contribute to ``cluster_count``; smaller groups are the
    per-thread fix loop's normal work and are not framing problems. Clusters are
    sorted largest-first so the worst single-source-of-truth violation leads.
    """
    count = len(threads)
    gists = [extract_gist(t.get("first_comment_body")) for t in threads]

    token_to_indices: dict[str, set[int]] = {}
    for index, gist in enumerate(gists):
        for token in gist:
            token_to_indices.setdefault(token, set()).add(index)

    uf = _UnionFind(count)
    for i in range(count):
        if not gists[i]:
            continue
        candidates: set[int] = set()
        for token in gists[i]:
            candidates.update(token_to_indices[token])
        for j in sorted(candidate for candidate in candidates if candidate > i):
            if gist_similarity(gists[i], gists[j]) >= similarity_threshold:
                uf.union(i, j)

    groups = _group_indices_by_root(uf, count)

    clusters: list[Report] = []
    for indices in groups.values():
        if len(indices) < warning_threshold:
            continue
        members = [threads[i] for i in indices]
        clusters.append(
            {
                "size": len(members),
                "shared_tokens": _shared_tokens(members),
                "source_artifact": _identify_source_artifact(members),
                "thread_ids": [m.get("thread_id") for m in members],
                "paths": [m.get("path") for m in members],
            }
        )

    # Largest cluster first; size is always the int we stored above.
    clusters.sort(key=_cluster_size, reverse=True)

    return {
        "thread_count": count,
        "cluster_count": len(clusters),
        "warning": bool(clusters),
        "clusters": clusters,
    }


_REVIEW_THREADS_FOR_CLUSTERING_QUERY = """\
query($owner: String!, $name: String!, $prNumber: Int!, $cursor: String) {
    repository(owner: $owner, name: $name) {
        pullRequest(number: $prNumber) {
            reviewThreads(first: 100, after: $cursor) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    isResolved
                    isOutdated
                    path
                    line
                    startLine
                    diffSide
                    comments(first: 1) {
                        totalCount
                        nodes {
                            databaseId
                            body
                            createdAt
                            author {
                                login
                            }
                        }
                    }
                }
            }
        }
    }
}"""


def _fail_fetch(message: str, pull_request: int) -> None:
    print(f"Could not fetch review threads for PR {pull_request}: {message}", file=sys.stderr)
    sys.exit(3)


def _fetch_unresolved_threads_with_clients(
    owner: str,
    repo: str,
    pull_request: int,
    gh_graphql,
    filter_unresolved_threads,
    transform_review_thread,
) -> list[Thread]:
    """Fetch unresolved threads with enough fields for gist clustering."""
    aggregated: list[dict] = []
    cursor: str | None = None
    max_pages = 50

    for _page in range(max_pages):
        variables: dict[str, object] = {
            "owner": owner,
            "name": repo,
            "prNumber": pull_request,
        }
        if cursor is not None:
            variables["cursor"] = cursor

        try:
            data = gh_graphql(_REVIEW_THREADS_FOR_CLUSTERING_QUERY, variables)
        except RuntimeError as exc:
            _fail_fetch(str(exc), pull_request)

        repository = data.get("repository") or {}
        pr_obj = repository.get("pullRequest")
        if not isinstance(pr_obj, dict):
            _fail_fetch("missing pullRequest", pull_request)
        review_threads = pr_obj.get("reviewThreads")
        if not isinstance(review_threads, dict):
            _fail_fetch("missing reviewThreads", pull_request)
        nodes = review_threads.get("nodes")
        if not isinstance(nodes, list):
            _fail_fetch("missing reviewThreads nodes", pull_request)

        aggregated.extend(node for node in nodes if isinstance(node, dict))

        page_info = review_threads.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor_obj = page_info.get("endCursor")
        if not isinstance(cursor_obj, str) or not cursor_obj:
            _fail_fetch("missing pagination cursor", pull_request)
        cursor = cursor_obj
    else:
        _fail_fetch("pagination exceeded 50 pages", pull_request)

    unresolved = filter_unresolved_threads(aggregated)
    return [
        item
        for item in (transform_review_thread(node) for node in unresolved)
        if isinstance(item, dict)
    ]


def _fetch_unresolved_threads(owner: str, repo: str, pull_request: int) -> list[Thread]:
    """Fetch unresolved threads via a clustering-specific GraphQL query."""
    lib_dir = _resolve_lib_dir()
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)

    from github_core.api import (  # noqa: E402
        assert_gh_authenticated,
        gh_graphql,
        resolve_repo_params,
    )
    from github_core.review_threads import (  # noqa: E402
        filter_unresolved_threads,
        transform_review_thread,
    )

    assert_gh_authenticated()
    resolved = resolve_repo_params(owner, repo)
    return _fetch_unresolved_threads_with_clients(
        resolved.owner,
        resolved.repo,
        pull_request,
        gh_graphql,
        filter_unresolved_threads,
        transform_review_thread,
    )


def _resolve_lib_dir() -> str:
    """Locate the plugin ``lib`` directory for github_core imports.

    Resolution order: ``COPILOT_PLUGIN_ROOT`` env, ``CLAUDE_PLUGIN_ROOT`` env,
    ``GITHUB_WORKSPACE`` env, then a path relative to this file. Exits 2
    (config error per ADR-035) when no candidate directory exists, so a
    misconfigured install fails loudly rather than importing nothing.
    """
    import os

    plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get(
        "CLAUDE_PLUGIN_ROOT",
    )
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if plugin_root:
        lib_dir = os.path.join(plugin_root, "lib")
    elif workspace:
        lib_dir = os.path.join(workspace, ".claude", "lib")
    else:
        lib_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib")
        )
    if not os.path.isdir(lib_dir):
        print(f"Plugin lib directory not found: {lib_dir}", file=sys.stderr)
        sys.exit(2)
    return lib_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Cluster unresolved PR review threads by shared gist and flag "
            "framing/spec problems before the per-thread fix loop."
        ),
    )
    parser.add_argument("--owner", default="", help="Repository owner")
    parser.add_argument("--repo", default="", help="Repository name")
    parser.add_argument(
        "--pull-request", type=int, required=True, help="Pull request number",
    )
    parser.add_argument(
        "--threads-file",
        default="",
        help=(
            "Read threads from a JSON file instead of fetching. The file is "
            "either a list of thread dicts or an object with a 'threads' key "
            "(the shape get_unresolved_review_threads.py emits). Used for "
            "offline analysis and tests; skips the GitHub fetch."
        ),
    )
    return parser


def _project_root() -> "Path":
    from pathlib import Path
    import os

    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace:
        root = Path(workspace).resolve()
        if (root / "pyproject.toml").is_file():
            return root

    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate

    print("Could not locate project root.", file=sys.stderr)
    sys.exit(2)


def _load_threads_from_file(path: str) -> list[Thread]:
    """Read threads from a JSON file (list or ``{"threads": [...]}``).

    Exits 2 on a missing file, malformed JSON, or a payload that is not a list
    of objects: a bad ``--threads-file`` is a usage error, not a clustering
    result. Non-dict list elements (untrusted input) are dropped rather than
    crashing the clusterer. Relative paths are anchored to the project root so
    the caller's current working directory cannot change what file is read.
    """
    from pathlib import Path

    requested_path = Path(path)
    project_root = _project_root()
    if requested_path.is_absolute():
        print("Threads file must be repository-relative.", file=sys.stderr)
        sys.exit(2)

    threads_path = (project_root / requested_path).resolve()
    try:
        threads_path.relative_to(project_root)
    except ValueError:
        print(
            f"Threads file {path} escapes project root.",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        raw = json.loads(threads_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read threads file {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    payload = raw.get("threads") if isinstance(raw, dict) else raw
    if not isinstance(payload, list):
        print(
            f"Threads file {path} must be a list or an object with a "
            "'threads' list.",
            file=sys.stderr,
        )
        sys.exit(2)
    return [item for item in payload if isinstance(item, dict)]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.pull_request <= 0:
        print("Pull request number must be positive.", file=sys.stderr)
        return 2

    if args.threads_file:
        threads = _load_threads_from_file(args.threads_file)
    else:
        threads = _fetch_unresolved_threads(
            args.owner, args.repo, args.pull_request,
        )

    report = cluster_threads(threads)
    report["pull_request"] = args.pull_request
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
