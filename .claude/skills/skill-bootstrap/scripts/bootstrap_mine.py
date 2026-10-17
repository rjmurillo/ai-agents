#!/usr/bin/env python3
"""Mine a repository for skill-bootstrap candidates and check authored skill text.

Both subcommands are read-only. They read the repository from one named ref
(`--rev`, default HEAD) with `git ls-tree -r -z --name-only`, `git log`,
`git grep`, and `git cat-file`. They never use `git log --all` and never walk
the working tree to learn what the repository contains.

Subcommands:

    candidates  Rank candidate cases from git history: reverts, the files
                touched by the most recent commits (churn), files with the most
                TODO/FIXME/XXX/HACK lines, and, when `--prs-json` is given, the
                pull requests with the most review rounds. Findings are
                candidates for a human or model to judge, not violations.
    claims      Check the repository paths named in authored markdown against
                the ref. Each reference is `ok`, `missing`, `untracked`, or
                `line-out-of-range`. Each finding carries a `context` label
                (`historical` or `current`) derived from the source line. A
                path missing from the repository root is also tried against
                the nearest directory above the target that holds a tracked
                SKILL.md, so a skill's own `scripts/x.py` resolves. The
                script labels; the reader judges.

Exit codes:

    0  Success. For `candidates`, always on success. For `claims`, no finding
       has context `current`.
    1  `claims` found a non-ok reference whose context is `current`.
    2  Configuration error: bad arguments, not a git repository, a bad rev, a
       missing or unreadable TARGET or `--prs-json` file, or an `--out` path
       inside the repository.
    3  External error: git is missing or a git command failed, or the `--out`
       file could not be written.

Every run prints one JSON document on stdout. A successful run carries an
`examined` object whose counts are printed even when they are zero, so a caller
can tell "nothing found in N items" from "nothing was examined". `--out FILE`
also writes the same JSON to FILE, which must be outside the repository.

Limits: `claims` recognizes paths that begin with a top-level directory tracked
at the ref, plus a bare top-level file name written in backticks. A path under
a directory that is not tracked at the ref is not recognized. A reference
preceded by a path character (for example a URL or `../`) is skipped. The
placeholder filter is a heuristic. Stdlib only, so the script runs from any
plugin root.

Stricter/looser/different than `bootstrap_boundary.py`: that script treats a
non-repository path as an external failure (exit 3) because it only verifies
state. This one exits 2 for a bad repository path or rev, because the caller
chose the input.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

Payload = dict[str, Any]

RECORD_SEP = "\x1e"
FIELD_SEP = "\x1f"
SHORT_SHA = 9

# `Revert ...`, with a word boundary so `Reverted` and `Reverts` do not match.
REVERT_SUBJECT_RE = re.compile(r"^revert\b", re.IGNORECASE)
# `<type>(<optional scope>)!?: revert`
REVERT_CONVENTIONAL_RE = re.compile(r"^[A-Za-z][\w-]*(?:\([^)]*\))?!?:\s*revert\b", re.IGNORECASE)
REVERT_BODY_RE = re.compile(
    r"^This reverts commit ([0-9a-fA-F]{7,40})(?![0-9a-fA-F])", re.MULTILINE
)

TODO_PATTERN = r"\b(TODO|FIXME|XXX|HACK)\b"

HISTORICAL_RE = re.compile(
    r"\b(retired|deleted|removed|formerly|was|were|until|superseded|no longer|legacy|used to)\b",
    re.IGNORECASE,
)
PATH_CHARS = r"A-Za-z0-9_.\-/"
PLACEHOLDER_CHARS = frozenset("<>{}[]*?$")
# `[` before a token and `]` after it are markdown link brackets, not globs.
PLACEHOLDER_BEFORE = PLACEHOLDER_CHARS - {"["}
PLACEHOLDER_AFTER = PLACEHOLDER_CHARS - {"]"}
PLACEHOLDER_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:NAME|NNN|NN|YYYY|MM-DD|SCRIPT)(?![A-Za-z0-9])"
)
NODE_TAIL_RE = re.compile(r"::[^\s`'\")>,;]*")
ANCHOR_TAIL_RE = re.compile(r"#[^\s`'\")>,;]*")
LINE_TAIL_RE = re.compile(r":(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)")
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
BARE_NAME_RE = re.compile(r"^([A-Za-z0-9_.\-]+)((?:::|#|:\d).*)?$")


class ConfigError(Exception):
    """Bad input: exit 2."""


class GitError(Exception):
    """git is missing or failed: exit 3."""


# ---------------------------------------------------------------- git access


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc


def _git(repo: Path, *args: str, ok: tuple[int, ...] = (0,)) -> str:
    proc = _run_git(repo, *args)
    if proc.returncode not in ok:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def repo_root(path: Path) -> Path:
    """Return the work-tree root that contains `path`, or raise ConfigError."""
    if not path.is_dir():
        raise ConfigError(f"repository path is not a directory: {path}")
    proc = _run_git(path, "rev-parse", "--show-toplevel")
    if proc.returncode != 0:
        raise ConfigError(f"not a git repository: {path}")
    return Path(proc.stdout.strip()).resolve()


def resolve_rev(root: Path, rev: str) -> str:
    """Return the full commit SHA for `rev`, or raise ConfigError."""
    if rev.startswith("-"):
        raise ConfigError(f"rev may not start with '-': {rev!r}")
    proc = _run_git(root, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    if proc.returncode != 0:
        raise ConfigError(f"rev does not name a commit: {rev!r}")
    return proc.stdout.strip()


def tracked_files(root: Path, sha: str) -> list[str]:
    """Every path tracked at `sha`, from `git ls-tree -r -z --name-only`."""
    raw = _git(root, "ls-tree", "-r", "-z", "--name-only", sha)
    return [p for p in raw.split("\0") if p]


def top_level_entries(root: Path, sha: str) -> tuple[list[str], list[str]]:
    """Return (directories, files) tracked at the top level of `sha`."""
    raw = _git(root, "ls-tree", "-z", sha)
    dirs: list[str] = []
    files: list[str] = []
    for entry in raw.split("\0"):
        meta, _, name = entry.partition("\t")
        kind = meta.split(" ")[1] if meta.count(" ") >= 2 else ""
        if kind == "tree":
            dirs.append(name)
        elif kind == "blob":
            files.append(name)
    return dirs, files


# ---------------------------------------------------------------- shared


def top_with_ties(ranked: list[Payload], top: int) -> tuple[list[Payload], bool]:
    """Return the first `top` rows plus any row tied with the last kept count.

    `ranked` is sorted by count descending. The flag is True when ties pushed
    the result past `top` rows.
    """
    if len(ranked) <= top:
        return ranked, False
    cutoff = ranked[top - 1]["count"]
    kept = [row for row in ranked if row["count"] >= cutoff]
    return kept, len(kept) > top


def _rank(counts: dict[str, int]) -> list[Payload]:
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"path": path, "count": count} for path, count in ordered]


def _excluded(path: str, prefixes: Sequence[str]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def _positive(value: int, flag: str) -> int:
    if value < 1:
        raise ConfigError(f"{flag} must be at least 1")
    return value


# ---------------------------------------------------------------- candidates


def parse_reverts(raw: str) -> tuple[list[Payload], int]:
    """Parse `git log --format=%H%x1f%aI%x1f%s%x1f%b%x1e` into revert items."""
    reverts: list[Payload] = []
    commits = 0
    for record in raw.split(RECORD_SEP):
        record = record.lstrip("\n")
        if not record:
            continue
        commits += 1
        sha, date, subject, body = record.split(FIELD_SEP, 3)
        rules = _revert_rules(subject, body)
        if rules:
            reverts.append(
                {
                    "sha": sha,
                    "short": sha[:SHORT_SHA],
                    "date": date,
                    "subject": subject,
                    "rule": rules,
                    "reverted": [m.lower() for m in REVERT_BODY_RE.findall(body)],
                }
            )
    return reverts, commits


def _revert_rules(subject: str, body: str) -> list[str]:
    rules = []
    if REVERT_SUBJECT_RE.search(subject):
        rules.append("subject")
    if REVERT_CONVENTIONAL_RE.search(subject):
        rules.append("conventional")
    if REVERT_BODY_RE.search(body):
        rules.append("body")
    return rules


def mine_reverts(root: Path, sha: str, max_commits: int) -> tuple[list[Payload], int]:
    raw = _git(
        root,
        "log",
        "-n",
        str(max_commits),
        "--format=%H%x1f%aI%x1f%s%x1f%b%x1e",
        sha,
        "--",
    )
    return parse_reverts(raw)


def mine_churn(
    root: Path, sha: str, window: int, exclude: Sequence[str]
) -> tuple[dict[str, int], int]:
    """Count commits per file over the `window` most recent commits."""
    raw = _git(root, "log", "-n", str(window), "-z", "--name-only", "--format=%x1e%H", sha, "--")
    counts: dict[str, int] = {}
    commits = 0
    for chunk in raw.split(RECORD_SEP):
        if not chunk:
            continue
        commits += 1
        _, _, rest = chunk.partition("\0")
        for path in {p for p in rest.lstrip("\n").split("\0") if p}:
            if not _excluded(path, exclude):
                counts[path] = counts.get(path, 0) + 1
    return counts, commits


def mine_todos(
    root: Path, sha: str, files: list[str], exclude: Sequence[str]
) -> tuple[dict[str, int], int]:
    """Count TODO-style lines per file at `sha`, returning counts and files in scope."""
    in_scope = [f for f in files if not _excluded(f, exclude)]
    raw = _git(root, "grep", "-z", "-I", "-c", "-E", TODO_PATTERN, sha, "--", ok=(0, 1))
    counts: dict[str, int] = {}
    prefix = f"{sha}:"
    for entry in raw.split("\n"):
        name, sep, number = entry.partition("\0")
        if not sep:
            continue
        path = name[len(prefix) :] if name.startswith(prefix) else name
        if not _excluded(path, exclude):
            counts[path] = int(number)
    return counts, len(in_scope)


def load_review_rounds(path: str, top: int) -> tuple[list[Payload], int]:
    """Read `--prs-json` and return the top pull requests by review rounds."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read --prs-json {path}: {exc}") from exc
    if not isinstance(data, list):
        raise ConfigError(f"--prs-json {path} must hold a JSON list")
    rows = [_review_row(item, index, path) for index, item in enumerate(data)]
    rows.sort(key=lambda r: (-r["review_rounds"], r["number"]))
    return rows[:top], len(rows)


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _review_row(item: object, index: int, path: str) -> Payload:
    where = f"--prs-json {path} item {index}"
    if not isinstance(item, dict):
        raise ConfigError(f"{where} is not an object")
    number = item.get("number")
    if not _is_count(number):
        raise ConfigError(f"{where} needs an integer `number`")
    rounds = item["review_rounds"] if "review_rounds" in item else item.get("reviews")
    if isinstance(rounds, list):
        rounds = len(rounds)
    if not _is_count(rounds):
        raise ConfigError(f"{where} needs `review_rounds` or `reviews` (int or list)")
    return {"number": number, "review_rounds": rounds}


def candidates(args: argparse.Namespace) -> tuple[int, Payload]:
    root = repo_root(Path(args.repo))
    _out_outside_repo(root, args.out)
    max_commits = _positive(args.max_commits, "--max-commits")
    window = _positive(args.churn_window, "--churn-window")
    top = _positive(args.top, "--top")
    exclude = args.exclude or []
    sha = resolve_rev(root, args.rev)
    prs: tuple[list[Payload], int] | None = (
        load_review_rounds(args.prs_json, top) if args.prs_json else None
    )

    reverts, commits = mine_reverts(root, sha, max_commits)
    churn_counts, churn_commits = mine_churn(root, sha, window, exclude)
    churn, churn_tie = top_with_ties(_rank(churn_counts), top)
    todo_counts, grepped = mine_todos(root, sha, tracked_files(root, sha), exclude)
    todos, todo_tie = top_with_ties(_rank(todo_counts), top)

    payload: Payload = {
        "repo": root.as_posix(),
        "rev": args.rev,
        "sha": sha,
        "reverts": reverts,
        "churn": [{"path": r["path"], "commits": r["count"]} for r in churn],
        "churn_tie_at_cutoff": churn_tie,
        "todo_hotspots": [{"path": r["path"], "todos": r["count"]} for r in todos],
        "todo_tie_at_cutoff": todo_tie,
        "examined": {
            "commits": commits,
            "churn_commits": churn_commits,
            "files_grepped": grepped,
        },
    }
    if prs is not None:
        payload["review_rounds"] = prs[0]
        payload["examined"]["prs"] = prs[1]
    return 0, payload


# ---------------------------------------------------------------- claims


def _expand_targets(targets: Sequence[str]) -> list[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            found = sorted(path.rglob("*.md"), key=lambda p: p.as_posix())
        elif path.is_file():
            found = [path]
        else:
            raise ConfigError(f"TARGET is not a file or directory: {target}")
        for item in found:
            key = item.resolve()
            if key not in seen:
                seen.add(key)
                ordered.append(item)
    return ordered


def _display(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_placeholder(path: str, before: str, after: str) -> bool:
    if before in PLACEHOLDER_BEFORE or after in PLACEHOLDER_AFTER:
        return True
    if PLACEHOLDER_WORD_RE.search(path):
        return True
    return "slug" in path.split("/")


def _tail(text: str) -> tuple[str, int | None]:
    """Parse what follows a path: `::node`, `#anchor`, or a line spec.

    Returns the consumed text and the largest line number it names, if any.
    """
    for pattern in (NODE_TAIL_RE, ANCHOR_TAIL_RE):
        match = pattern.match(text)
        if match:
            return match.group(0), None
    match = LINE_TAIL_RE.match(text)
    if match:
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        return match.group(0), max(numbers)
    return "", None


class PathFinder:
    """Extract repo-path references from one line of text."""

    def __init__(self, dirs: Sequence[str], files: Sequence[str]) -> None:
        names = sorted(dirs, key=len, reverse=True)
        self._files = frozenset(files)
        self._dir_re = (
            re.compile(
                rf"(?<![{PATH_CHARS}])(?:{'|'.join(re.escape(n) for n in names)})/[{PATH_CHARS}]*"
            )
            if names
            else None
        )

    def find(self, line: str) -> list[tuple[str, str, int | None]]:
        """Return (ref, path, max_line) for each reference on the line."""
        found = self._dir_refs(line)
        found.extend(self._bare_refs(line))
        return found

    def _dir_refs(self, line: str) -> list[tuple[str, str, int | None]]:
        if self._dir_re is None:
            return []
        found = []
        for match in self._dir_re.finditer(line):
            raw = match.group(0)
            path = raw.rstrip(".,")
            before = line[match.start() - 1] if match.start() else ""
            rest = line[match.end() :]
            after = rest[:1] if path == raw else ""
            if _is_placeholder(path, before, after):
                continue
            tail, max_line = _tail(rest) if path == raw else ("", None)
            found.append((path + tail, path, max_line))
        return found

    def _bare_refs(self, line: str) -> list[tuple[str, str, int | None]]:
        found = []
        for match in INLINE_CODE_RE.finditer(line):
            span = match.group(1)
            parsed = BARE_NAME_RE.match(span)
            if not parsed or parsed.group(1) not in self._files:
                continue
            name = parsed.group(1)
            tail, max_line = _tail(span[len(name) :])
            if tail == span[len(name) :]:
                found.append((span, name, max_line))
        return found


class RepoView:
    """Answer path questions about one ref."""

    def __init__(self, root: Path, sha: str) -> None:
        self._root = root
        self._sha = sha
        self._tracked = frozenset(tracked_files(root, sha))
        self._dir_prefixes = frozenset(
            "/".join(p.split("/")[:i]) for p in self._tracked for i in range(1, len(p.split("/")))
        )
        self._lines: dict[str, int] = {}

    def line_count(self, path: str) -> int:
        if path not in self._lines:
            text = _git(self._root, "cat-file", "-p", f"{self._sha}:{path}")
            self._lines[path] = text.count("\n") + (0 if not text or text.endswith("\n") else 1)
        return self._lines[path]

    def status(self, path: str, max_line: int | None) -> str:
        bare = path.rstrip("/")
        if bare in self._tracked:
            if path.endswith("/"):
                return "missing"
            if max_line is not None and max_line > self.line_count(bare):
                return "line-out-of-range"
            return "ok"
        if bare in self._dir_prefixes:
            return "ok"
        return "untracked" if self._on_disk(bare) else "missing"

    def _on_disk(self, path: str) -> bool:
        if ".." in path.split("/"):
            return False
        return (self._root / path).exists()


def _skill_base(display: str, view: RepoView) -> str | None:
    """Return the nearest ancestor directory of `display` that holds a tracked SKILL.md."""
    parts = display.split("/")[:-1]
    while parts:
        base = "/".join(parts)
        if view.status(f"{base}/SKILL.md", None) == "ok":
            return base
        parts.pop()
    return None


def _resolve(view: RepoView, base: str | None, path: str, max_line: int | None) -> str:
    """Status from the repository root, else from the skill directory when one holds it."""
    status = view.status(path, max_line)
    if status == "ok" or base is None:
        return status
    relative = view.status(f"{base}/{path}", max_line)
    return relative if relative in ("ok", "line-out-of-range") else status


def _scan_file(
    finder: PathFinder, view: RepoView, display: str, text: str
) -> dict[tuple[str, str], Payload]:
    refs: dict[tuple[str, str], Payload] = {}
    base = _skill_base(display, view)
    for number, line in enumerate(text.splitlines(), start=1):
        context = "historical" if HISTORICAL_RE.search(line) else "current"
        for ref, path, max_line in finder.find(line):
            key = (display, ref)
            known = refs.get(key)
            if known is not None and not (
                known["context"] == "historical" and context == "current"
            ):
                continue
            refs[key] = {
                "file": display,
                "line": number,
                "ref": ref,
                "path": path,
                "status": _resolve(view, base, path, max_line),
                "context": context,
            }
    return refs


def _read_target(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ConfigError(f"cannot read TARGET {path}: {exc}") from exc


def claims(args: argparse.Namespace) -> tuple[int, Payload]:
    root = repo_root(Path(args.repo))
    _out_outside_repo(root, args.out)
    sha = resolve_rev(root, args.rev)
    targets = _expand_targets(args.targets)
    finder = PathFinder(*top_level_entries(root, sha))
    view = RepoView(root, sha)
    references: list[Payload] = []
    for target in targets:
        text = _read_target(target)
        references.extend(_scan_file(finder, view, _display(root, target), text).values())
    findings = [r for r in references if r["status"] != "ok"]
    summary: Payload = {"status": {}, "context": {}}
    for finding in findings:
        for key in ("status", "context"):
            summary[key][finding[key]] = summary[key].get(finding[key], 0) + 1
    blocking = any(f["context"] == "current" for f in findings)
    return (1 if blocking else 0), {
        "repo": root.as_posix(),
        "rev": args.rev,
        "sha": sha,
        "findings": findings,
        "examined": {"files": len(targets), "references": len(references)},
        "summary": summary,
    }


# ---------------------------------------------------------------- CLI


def _out_outside_repo(root: Path, out: str | None) -> None:
    """Refuse an `--out` path inside the repository, so a run never writes there."""
    if out is None:
        return
    target = Path(out).resolve()
    if target == root or root in target.parents:
        raise ConfigError(f"--out {out} is inside the repository {root}; write it elsewhere")
    if target.is_dir():
        raise ConfigError(f"--out {out} is a directory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bootstrap_mine", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo", required=True)
        p.add_argument("--rev", default="HEAD")
        p.add_argument("--out", help="also write the JSON to FILE, outside the repository")

    p_cand = sub.add_parser("candidates", help="rank candidate cases from git history")
    common(p_cand)
    p_cand.add_argument("--max-commits", type=int, default=3000)
    p_cand.add_argument("--churn-window", type=int, default=300)
    p_cand.add_argument("--top", type=int, default=10)
    p_cand.add_argument("--exclude", action="append", metavar="PREFIX")
    p_cand.add_argument("--prs-json", metavar="FILE")

    p_claims = sub.add_parser("claims", help="check repo paths named in authored markdown")
    common(p_claims)
    p_claims.add_argument("targets", nargs="+", metavar="TARGET")
    return parser


def _emit(payload: Payload, out: str | None) -> None:
    text = json.dumps(payload, indent=2)
    if out is not None:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    print(text)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"candidates": candidates, "claims": claims}
    try:
        code, payload = handlers[args.command](args)
        _emit(payload, args.out)
    except ConfigError as exc:
        print(json.dumps({"error": "config", "message": str(exc)}))
        return 2
    except GitError as exc:
        print(json.dumps({"error": "git", "message": str(exc)}))
        return 3
    except OSError as exc:
        print(json.dumps({"error": "io", "message": str(exc)}))
        return 3
    return code


if __name__ == "__main__":
    sys.exit(main())
