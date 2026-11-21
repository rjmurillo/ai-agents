#!/usr/bin/env python3
# taste-lint: ignore complexity -- pre-existing debt, unlinted before the ADR-119 source classification
"""Search repository notes, legacy memories, and session episodes.

Agent-facing script that searches local memory stores and
reports a token budget warning for large memories.

The lexical path also searches the Tier 2 episode store. Before that was
wired, nothing outside the episode tests read those records, so the write
cost on every session-log commit bought nothing (Issue #3630).

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (invalid query or search failed)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

TOKEN_WARN_THRESHOLD = 5000
TOKEN_DECOMPOSE_THRESHOLD = 10000

# Credit for a keyword that matches only a parent directory, not the file name.
# Matching moved from the bare stem to the relative path so nested memories
# become reachable. That let a topic directory hand a perfect score to every
# file under it, burying the top-level file the query actually named. Full
# credit for a stem match and partial credit for a directory-only match keeps
# the recall and leaves top-level scoring unchanged, since a top-level stem is
# its whole relative path.
DIRECTORY_MATCH_WEIGHT = 0.5

# Every episode filename opens with `episode-<date>-` and often `session-<n>-`.
# Those tokens are metadata, not content: leaving them in the haystack made the
# keywords "episode" and "session" match nearly the whole corpus.
EPISODE_NAME_PREFIX = re.compile(r"^episode-\d{4}-\d{2}-\d{2}-(?:session-\d+-?)?")

# Same shape as EPISODE_NAME_PREFIX, but capturing so the recency sort can read
# the date and the session number instead of comparing the raw string.
EPISODE_RECENCY = re.compile(r"^episode-(\d{4}-\d{2}-\d{2})-(?:session-(\d+)\b)?")


def _recency_key(name: str) -> tuple[str, int, str]:
    """Order an episode name newest-first under a reverse sort.

    The date is fixed-width ISO, so it compares correctly as a string. The
    session number does not: a reverse string sort reads it digit by digit, so
    `session-9` outranks `session-10` at every power of ten. Parsing it as an
    integer fixes that without disturbing the date, which stays the primary key
    because session numbers are globally increasing and would otherwise let a
    high-numbered old session outrank a low-numbered new one.

    Names that carry no parseable date return an empty date, which sorts last
    under a reverse sort rather than first as the raw string did. Names with a
    date but no session number use -1, placing them below any numbered session
    on the same date: a numbered session is the more specific record. Four of
    the 302 episodes in `.project-toolkit/memory/episodes` are in that shape.

    The full name is the final element so the order is total and stable across
    runs when the date and session number both tie.
    """
    match = EPISODE_RECENCY.match(name)
    if not match:
        return ("", -1, name)
    return (match.group(1), int(match.group(2)) if match.group(2) else -1, name)


def estimate_tokens(file_path: Path) -> int:
    """Estimate token count from file size (chars / 4)."""
    if not file_path.is_file():
        return 0
    try:
        return round(len(file_path.read_text(encoding="utf-8")) / 4)
    except (OSError, UnicodeError):
        return 0


def _corpus_scope(corpus: Path) -> Path:
    resolved = corpus.resolve()
    return _find_checkout(resolved) or resolved


def _is_corpus_file(path: Path, scope: Path) -> bool:
    return path.is_file() and (not path.is_symlink() or path.resolve().is_relative_to(scope))


def search_serena(
    query: str,
    memory_path: Path,
    max_results: int,
    *,
    source: str = "Serena",
) -> list[dict[str, Any]]:
    """Search Markdown memories by keyword matching on memory names.

    A name is the path relative to ``memory_path``, without ``.md``. Content
    is read only for the result preview and is never matched.
    """
    if not memory_path.is_dir():
        return []

    keywords = query_keywords(query)
    scope = _corpus_scope(memory_path)

    results: list[dict[str, Any]] = []
    for md_file in sorted(memory_path.rglob("*.md")):
        if not _is_corpus_file(md_file, scope):
            continue
        rel = md_file.relative_to(memory_path).with_suffix("")
        name = rel.as_posix().lower()
        stem = name.rpartition("/")[2]
        stem_hits = sum(1 for kw in keywords if kw in stem)
        matching = [kw for kw in keywords if kw in name]
        if not matching:
            continue
        weighted = stem_hits + DIRECTORY_MATCH_WEIGHT * (len(matching) - stem_hits)
        score = weighted / len(keywords) if keywords else 0
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        preview = re.sub(r"\s+", " ", content).strip()
        results.append(
            {
                "Name": rel.as_posix(),
                "Source": source,
                "Score": round(score, 2),
                "Path": str(md_file),
                "Content": preview[:200] if preview else "",
            }
        )

    results.sort(key=lambda r: float(r["Score"]), reverse=True)
    return results[:max_results]


def query_keywords(query: str) -> list[str]:
    """Split a query into match keywords, dropping very short noise words."""
    keywords = [kw for kw in query.lower().split() if len(kw) > 2]
    return keywords or query.lower().split()


def search_episodes(
    query: str,
    episodes_path: Path,
    max_results: int,
) -> list[dict[str, Any]]:
    """Search Tier 2 episode records by keyword.

    Matches the name slug, the task, and any lessons. Structural filename
    tokens are stripped first so that generic words do not match everything.
    """
    if not episodes_path.is_dir():
        return []

    keywords = query_keywords(query)
    results: list[dict[str, Any]] = []
    for episode_file in sorted(episodes_path.glob("episode-*.json")):
        try:
            episode = json.loads(episode_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(episode, dict):
            continue

        slug = EPISODE_NAME_PREFIX.sub("", episode_file.stem).replace("-", " ")
        task = str(episode.get("task") or "")
        lessons = episode.get("lessons")
        lesson_text = (
            " ".join(str(lesson) for lesson in lessons) if isinstance(lessons, list) else ""
        )
        haystack = f"{slug} {task} {lesson_text}".lower()

        matching = [kw for kw in keywords if kw in haystack]
        if not matching:
            continue
        score = len(matching) / len(keywords) if keywords else 0
        preview = re.sub(r"\s+", " ", task or slug).strip()
        results.append(
            {
                "Name": episode_file.stem,
                "Source": "Episodes",
                "Score": round(score, 2),
                "Path": str(episode_file),
                "Content": preview[:200],
            }
        )

    # Ties are common because scoring is a fraction of matched keywords. Within
    # a score tier the newest episode is the most useful, so order by the date
    # and session number the filename carries rather than by the raw string.
    # A reverse string sort compares digit by digit, so `session-9` outranks
    # `session-10` and any name that fails the pattern outranks every dated one.
    # Measured across the 302-episode corpus in `.project-toolkit/memory/episodes`, no
    # date yet spans a digit-width boundary, so this was a latent trap rather
    # than an observed regression (issue #3630 review).
    results.sort(key=lambda r: _recency_key(str(r["Name"])), reverse=True)
    results.sort(key=lambda r: float(r["Score"]), reverse=True)
    return results[:max_results]


def get_memory_router_status(
    serena_path: Path | None, episodes_path: Path | None = None, notes_path: Path | None = None
) -> dict[str, dict[str, object]]:
    """Return diagnostic status of memory systems."""
    serena_available = serena_path is not None and serena_path.is_dir()
    serena_count = 0
    if serena_available and serena_path is not None:
        serena_count = len(list(serena_path.rglob("*.md")))

    episodes_available = False
    episode_count = 0
    if episodes_path is not None and episodes_path.is_dir():
        episodes_available = True
        episode_count = len(list(episodes_path.glob("episode-*.json")))

    status: dict[str, dict[str, object]] = {
        "Serena": {
            "Available": serena_available,
            "MemoryCount": serena_count,
            "Path": str(serena_path) if serena_path is not None else "",
        },
        "Episodes": {
            "Available": episodes_available,
            "MemoryCount": episode_count,
            "Path": str(episodes_path) if episodes_path is not None else "",
        },
    }
    if notes_path is not None:
        notes_scope = _corpus_scope(notes_path)
        status["RepositoryNotes"] = {
            "Available": True,
            "MemoryCount": sum(
                1 for path in notes_path.rglob("*.md") if _is_corpus_file(path, notes_scope)
            ),
            "Path": str(notes_path),
        }
    return status


_HELP_EPILOG = """\
examples:
  %(prog)s "session protocol"
  %(prog)s "git hooks" --max-results 5 --format table

exit codes:
  0  search ran (results may be empty)
  1  query failed validation (1-500 characters)
  2  a store path contains '..', or AI_AGENTS_REPO_ROOT is not a directory
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search repository notes, legacy memories, and session episodes.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "query",
        help="Search query (1-500 chars, alphanumeric + common punctuation)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum results to return (1-100, default 10)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        dest="output_format",
        help="Output format: json (default) or table",
    )
    parser.add_argument(
        "--serena-path",
        type=Path,
        default=None,
        help="Path to Serena memories directory",
    )
    parser.add_argument(
        "--episodes-path",
        type=Path,
        default=None,
        help="Path to the Tier 2 episode store directory",
    )
    return parser


def validate_query(query: str) -> str | None:
    """Validate query string. Returns error message or None."""
    if not query or len(query) > 500:
        return "Query must be 1-500 characters"
    if not re.match(r"^[a-zA-Z0-9\s\-.,_()\&:]+$", query):
        return "Query contains invalid characters"
    return None


SERENA_REL = Path(".serena", "memories")
EPISODES_REL = Path(".project-toolkit", "memory", "episodes")
NOTES_REL = EPISODES_REL.with_name("notes")


def _find_checkout(start: Path) -> Path | None:
    return next(
        (
            parent
            for parent in (start, *start.parents)
            if (parent / ".git").exists()
            or (parent / SERENA_REL).is_dir()
            or (parent / EPISODES_REL.parent).is_dir()
        ),
        None,
    )


def resolve_repo_root(script_dir: Path) -> Path:
    """Pick the checkout that owns the memory stores.

    An installed plugin lives outside the consumer checkout, so the path
    relative to this file points at the plugin directory. Prefer the
    consumer project (CLAUDE_PROJECT_DIR, then the working directory).
    """
    candidates = [os.environ.get("CLAUDE_PROJECT_DIR", ""), str(Path.cwd())]
    for candidate in candidates:
        if not candidate:
            continue
        root = _find_checkout(Path(candidate).resolve())
        if root is not None:
            return root
    return script_dir.parent.parent.parent.parent


def checkout_corpus(repo_root: Path, relative: Path) -> Path | None:
    """Find an existing corpus whose resolved path stays inside the checkout."""
    path = repo_root / relative
    if not path.is_dir():
        return None
    resolved = path.resolve()
    return resolved if resolved != repo_root and resolved.is_relative_to(repo_root) else None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    query = args.query
    max_results = max(1, min(100, args.max_results))
    output_format = args.output_format

    validation_error = validate_query(query)
    if validation_error:
        error_output = {"Error": validation_error, "Query": query}
        print(json.dumps(error_output, indent=2))
        return 1

    # Determine store paths
    script_dir = Path(__file__).resolve().parent
    repo_root = resolve_repo_root(script_dir)

    if args.serena_path:
        if ".." in args.serena_path.parts:
            msg = "Security: path must not contain traversal sequences."
            print(json.dumps({"Error": msg}, indent=2))
            return 2
        serena_path = args.serena_path.resolve()
    else:
        serena_path = checkout_corpus(repo_root, SERENA_REL)

    if args.episodes_path:
        if ".." in args.episodes_path.parts:
            msg = "Security: path must not contain traversal sequences."
            print(json.dumps({"Error": msg}, indent=2))
            return 2
        episodes_path = args.episodes_path.resolve()
    else:
        episodes_path = repo_root / EPISODES_REL

    search_status: dict[str, Any] = {
        "SerenaQueried": True,
        "EpisodesQueried": True,
        "SerenaSucceeded": False,
        "EpisodesSucceeded": False,
    }

    results = search_serena(query, serena_path, max_results) if serena_path else []
    search_status["SerenaSucceeded"] = True
    notes_path = checkout_corpus(repo_root, NOTES_REL) if serena_path is None else None
    if notes_path is not None:
        results = search_serena(query, notes_path, max_results, source="RepositoryNotes")
        search_status["RepositoryNotesQueried"] = True
        search_status["RepositoryNotesSucceeded"] = True
    results += search_episodes(query, episodes_path, max_results)
    search_status["EpisodesSucceeded"] = True
    results.sort(key=lambda r: float(r["Score"]), reverse=True)
    results = results[:max_results]

    # Compute token estimates
    token_budget: dict[str, Any] = {"TotalEstimate": 0, "Warnings": []}
    for result in results:
        path = Path(result.get("Path", ""))
        estimate = estimate_tokens(path)
        result["TokenEstimate"] = estimate
        token_budget["TotalEstimate"] += estimate
        if estimate >= TOKEN_DECOMPOSE_THRESHOLD:
            token_budget["Warnings"].append(
                f"DECOMPOSE: {result['Name']} ({estimate} tokens) "
                f"exceeds {TOKEN_DECOMPOSE_THRESHOLD}",
            )
        elif estimate >= TOKEN_WARN_THRESHOLD:
            token_budget["Warnings"].append(
                f"LARGE: {result['Name']} ({estimate} tokens) exceeds {TOKEN_WARN_THRESHOLD}",
            )

    if output_format == "table":
        if not results:
            print(f"No results found for: {query}")
        else:
            print(f"{'Name':<40} {'Source':<10} {'Score':<8} {'Tokens':<10} Preview")
            print("-" * 100)
            for r in results:
                preview = r.get("Content", "")
                if len(preview) > 60:
                    preview = preview[:57] + "..."
                print(
                    f"{r['Name']:<40} {r['Source']:<10} "
                    f"{r['Score']:<8} {r.get('TokenEstimate', 0):<10} "
                    f"{preview}",
                )
            print(
                f"\nToken budget: {token_budget['TotalEstimate']} tokens "
                f"(cumulative for {len(results)} results)",
            )
            for warning in token_budget["Warnings"]:
                print(f"WARNING: {warning}", file=sys.stderr)
    else:
        output = {
            "Query": query,
            "Count": len(results),
            # Unchanged: this was the value every flagless caller already got.
            "Source": "Unified",
            "SearchStatus": search_status,
            "TokenBudget": token_budget,
            "Results": results,
            "Diagnostic": get_memory_router_status(serena_path, episodes_path, notes_path),
        }
        print(json.dumps(output, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
