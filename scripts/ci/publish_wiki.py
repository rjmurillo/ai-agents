#!/usr/bin/env python3
"""Mirror docs/training/ to the GitHub wiki, one way (issue #7202, epic #7201).

``docs/training/`` is the source of truth. The wiki repo is a read-only mirror:
every run rebuilds the wiki's Markdown pages from the source tree, so a wiki
edit lasts until the next publish. ``.github/workflows/publish-wiki.yml`` is a
thin caller (ADR-006). All decisions live here (ADR-042).

What it builds from the source tree:

* ``README.md`` becomes ``Home.md`` with a banner that says the wiki is a mirror.
* Every other ``<name>.md`` becomes the wiki page ``<name>``. Files that start
  with ``_`` (``_template.md``) are not published.
* Relative links between pages become wiki links (``./a.md#x`` -> ``a#x``). Any
  other repo-relative link becomes an absolute github.com blob or tree URL,
  because a wiki cannot resolve repo paths.
* ``_Sidebar.md`` lists the pages in the order their links appear in README.md.

It refuses a source tree it cannot mirror faithfully: sub-directories, symbolic
links, names that are not kebab-case, YAML front matter, a page README.md never
links, and a link to a missing file or one that resolves outside the repo.
Wiki pages the source no longer produces are deleted. A second run with no
source change makes no commit.

Usage: python3 scripts/ci/publish_wiki.py [--dry-run]   (https needs WIKI_TOKEN)

Environment: ``GITHUB_REPOSITORY`` (owner/name), ``GITHUB_SERVER_URL``,
``WIKI_TOKEN`` (push credential), ``WIKI_DRY_RUN=true`` (same as --dry-run),
``GITHUB_SHA`` (named in the wiki commit message), ``GITHUB_STEP_SUMMARY``.

Exit codes (AGENTS.md contract):
    0  published, nothing to change, dry run, or a typed SKIP (no credential,
       or the wiki repo does not exist yet)
    1  source tree cannot be mirrored (see the list above)
    2  configuration error (no repository, source directory missing, git absent)
    3  external failure (clone or push failed for a reason other than auth)
    4  auth rejected: the wiki refused the credential (BLOCKED)
"""

from __future__ import annotations

import argparse
import base64
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK, EXIT_LOGIC, EXIT_CONFIG, EXIT_EXTERNAL, EXIT_AUTH = 0, 1, 2, 3, 4

SOURCE_DIR = "docs/training"
HOME = "Home"
TOKEN_SECRET = "WIKI_PUSH_TOKEN"
BRANCH = "main"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")
SCHEME_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")
INLINE_LINK_RE = re.compile(r'(!?\[[^\]\n]*\]\()(<[^>\n]+>|[^)\s]+)((?:\s+"[^"\n]*")?\))')
REF_LINK_RE = re.compile(r"^(\s{0,3}\[[^\]\n]+\]:\s+)(\S+)")
CODE_SPAN_RE = re.compile(r"(`+[^`\n]*`+)")
FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")


def safe(text: str) -> str:
    """Neutralize text before it reaches a log line: no workflow commands, no line breaks."""
    return text.replace("::", ":\u200b:").replace("\n", "\\n").replace("\r", "\\r")


class SourceError(Exception):
    """The source tree cannot be mirrored faithfully (exit 1)."""


@dataclass(frozen=True)
class Plan:
    """Wiki files to write, keyed by file name, plus the sidebar order."""

    files: dict[str, str]
    order: list[tuple[str, str]]  # (title, page name) in README link order


def split_fenced(text: str) -> list[tuple[str, bool]]:
    """Return (line, in_fence) pairs. Fence delimiter lines count as fenced."""
    out: list[tuple[str, bool]] = []
    fenced = False
    for line in text.split("\n"):
        if FENCE_RE.match(line):
            out.append((line, True))
            fenced = not fenced
        else:
            out.append((line, fenced))
    return out


def rewrite_target(
    target: str, *, repo_root: Path, repo_url: str, published: Mapping[str, str], image: bool
) -> str:
    """Rewrite one link target. ``published`` maps source file name to wiki page name."""
    if target.startswith("#") or SCHEME_RE.match(target):
        return target
    path, hash_, frag = target.partition("#")
    path, query_sep, query = path.partition("?")
    resolved = posixpath.normpath(posixpath.join(SOURCE_DIR, path))
    if resolved == ".." or resolved.startswith("../") or posixpath.isabs(resolved):
        raise SourceError(f"link leaves the repository: {safe(target)}")
    parent, base = posixpath.split(resolved)
    if parent == SOURCE_DIR and base in published:
        return published[base] + hash_ + frag
    on_disk = repo_root / resolved
    if not on_disk.exists():
        raise SourceError(f"link target does not exist: {safe(target)} (resolved {safe(resolved)})")
    if not on_disk.resolve().is_relative_to(repo_root.resolve()):
        raise SourceError(f"link target resolves outside the repository: {safe(target)}")
    kind = "tree" if on_disk.is_dir() else "blob"
    url = f"{repo_url}/{kind}/{BRANCH}/{resolved}"
    if image and kind == "blob":
        url += "?raw=true"
    elif query_sep:
        url += "?" + query
    return url + hash_ + frag


def rewrite_links(
    text: str, *, repo_root: Path, repo_url: str, published: Mapping[str, str]
) -> str:
    """Rewrite links outside fenced blocks and inline code spans."""

    def one(target: str, image: bool) -> str:
        return rewrite_target(
            target, repo_root=repo_root, repo_url=repo_url, published=published, image=image
        )

    def inline(match: re.Match[str]) -> str:
        opener, raw, closer = match.groups()
        angle = raw.startswith("<")
        new = one(raw[1:-1] if angle else raw, opener.startswith("!"))
        return opener + (f"<{new}>" if angle else new) + closer

    def ref(match: re.Match[str]) -> str:
        return match.group(1) + one(match.group(2), False)

    lines = []
    for line, fenced in split_fenced(text):
        if fenced:
            lines.append(line)
            continue
        parts = CODE_SPAN_RE.split(line)
        for i in range(0, len(parts), 2):
            parts[i] = INLINE_LINK_RE.sub(inline, REF_LINK_RE.sub(ref, parts[i]))
        lines.append("".join(parts))
    return "\n".join(lines)


def readme_page_order(readme: str) -> list[str]:
    """Source file names README.md links to, first occurrence only, in order."""
    seen: list[str] = []
    for line, fenced in split_fenced(readme):
        if fenced:
            continue
        for part in CODE_SPAN_RE.split(line)[::2]:
            targets = [m.group(2).strip("<>") for m in INLINE_LINK_RE.finditer(part)]
            targets += [m.group(2) for m in REF_LINK_RE.finditer(part)]
            for target in targets:
                if SCHEME_RE.match(target) or target.startswith("#"):
                    continue
                resolved = posixpath.normpath(posixpath.join(SOURCE_DIR, target.split("#")[0]))
                parent, base = posixpath.split(resolved)
                if parent == SOURCE_DIR and base not in seen:
                    seen.append(base)
    return seen


def first_heading(text: str, fallback: str) -> str:
    for line, fenced in split_fenced(text):
        if not fenced and line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def classify_entry(entry: Path) -> tuple[str | None, str | None]:
    """Return (published name, problem) for one source entry. ``(None, None)`` skips it."""
    label = safe(entry.name)
    if entry.is_symlink():
        return None, f"{label}: symbolic links are not allowed, the publisher would follow them"
    if entry.is_dir():
        return None, f"{label}/: sub-directories are not allowed, the wiki is flat"
    if entry.name.startswith("_"):
        return None, None
    if entry.name == "README.md":
        return entry.name, None
    if entry.suffix != ".md":
        return None, f"{label}: only .md files may live here"
    if not NAME_RE.match(entry.name):
        return None, f"{label}: use kebab-case, lowercase letters, digits, hyphens"
    return entry.name, None


def validate_source(source: Path) -> list[str]:
    """Return published source file names (sorted). Raise SourceError on a bad tree."""
    problems: list[str] = []
    names: list[str] = []
    for entry in sorted(source.iterdir()):
        name, problem = classify_entry(entry)
        if problem:
            problems.append(problem)
        if name:
            names.append(name)
    if "README.md" not in names:
        problems.append("README.md is missing, it is the index and becomes Home")
    for name in names:
        head = (source / name).read_text(encoding="utf-8").lstrip("\ufeff")
        if head.startswith("---"):
            problems.append(f"{name}: YAML front matter is not allowed, the wiki shows it as text")
    if problems:
        raise SourceError("\n".join(problems))
    return names


def page_name(source_name: str) -> str:
    return HOME if source_name == "README.md" else source_name[: -len(".md")]


def banner(repo_url: str) -> str:
    return (
        "> **This wiki is a read-only mirror.** Edit the pages in "
        f"[`{SOURCE_DIR}/`]({repo_url}/tree/{BRANCH}/{SOURCE_DIR}), not here. "
        "A wiki edit is overwritten on the next publish.\n\n"
    )


def build_plan(source: Path, repo_root: Path, repo_url: str) -> Plan:
    names = validate_source(source)
    published = {n: page_name(n) for n in names}
    linked = readme_page_order((source / "README.md").read_text(encoding="utf-8"))
    orphans = sorted(set(names) - set(linked) - {"README.md"})
    if orphans:
        raise SourceError(
            "pages on disk that README.md does not link: "
            + ", ".join(safe(o) for o in orphans)
            + ". Add each to the index so the sidebar lists it."
        )
    files: dict[str, str] = {}
    titles: dict[str, str] = {}
    for name in names:
        body = (source / name).read_text(encoding="utf-8")
        try:
            body = rewrite_links(body, repo_root=repo_root, repo_url=repo_url, published=published)
        except SourceError as exc:
            raise SourceError(f"{name}: {exc}") from exc
        titles[name] = first_heading(body, published[name])
        src = f"{SOURCE_DIR}/{name}"
        footer = f"\n\n---\nSource: [{src}]({repo_url}/blob/{BRANCH}/{src})\n"
        prefix = banner(repo_url) if name == "README.md" else ""
        files[published[name] + ".md"] = prefix + body.rstrip("\n") + footer
    order = [(titles[n], published[n]) for n in linked if n in published and n != "README.md"]
    side = [f"**[Feature training]({HOME})**", ""] + [f"- [{t}]({p})" for t, p in order]
    files["_Sidebar.md"] = "\n".join(side) + "\n"
    return Plan(files=files, order=order)


# --- git ---------------------------------------------------------------------


def git_env(token: str | None, url: str) -> dict[str, str]:
    """Environment for git. The token travels in an extraheader, never in the URL or argv."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token and url.startswith("https://"):
        slot = int(env.get("GIT_CONFIG_COUNT", "0") or "0")
        creds = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env["GIT_CONFIG_COUNT"] = str(slot + 1)
        env[f"GIT_CONFIG_KEY_{slot}"] = "http.extraheader"
        env[f"GIT_CONFIG_VALUE_{slot}"] = f"AUTHORIZATION: basic {creds}"
    return env


def run_git(
    args: Sequence[str], cwd: Path | None, env: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=dict(env), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )  # fmt: skip


def classify_failure(stderr: str) -> str:
    """Return ``missing``, ``auth`` or ``external`` for a failed clone or push."""
    low = stderr.lower()
    if (
        "repository not found" in low
        or "does not appear to be a git repository" in low
        or "does not exist" in low
    ):
        return "missing"
    markers = (
        "403",
        "401",
        "authentication failed",
        "permission denied",
        "denied to",
        "invalid username",
    )
    return "auth" if any(m in low for m in markers) else "external"


def redact(text: str, token: str | None) -> str:
    """Mask the token and the base64 credential git sends in the auth header."""
    if not token:
        return text
    creds = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return text.replace(creds, "***").replace(token, "***")


def summary(line: str, environ: Mapping[str, str]) -> None:
    print(line)
    path = environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def apply_plan(plan: Plan, wiki: Path) -> None:
    """Make the wiki working tree hold exactly the planned Markdown pages."""
    for stale in sorted(p for p in wiki.glob("*.md") if p.name not in plan.files):
        stale.unlink()
    for name, content in plan.files.items():
        target = wiki / name
        if target.is_symlink():
            target.unlink()  # never write through a link a wiki committer planted
        target.write_text(content, encoding="utf-8", newline="\n")


@dataclass(frozen=True)
class Config:
    repo_root: Path
    repo_url: str
    wiki_url: str
    dry: bool
    token: str | None
    sha: str


def load_config(args: argparse.Namespace, environ: Mapping[str, str]) -> Config | str:
    """Return a Config, or a CONFIG error message."""
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / SOURCE_DIR).is_dir():
        return f"CONFIG: {SOURCE_DIR} not found under {repo_root}"
    repo = args.repo or environ.get("GITHUB_REPOSITORY", "")
    if not repo and not args.wiki_url:
        return "CONFIG: set --repo or GITHUB_REPOSITORY"
    if shutil.which("git") is None:
        return "CONFIG: git is not on PATH"
    server = environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repo_url = f"{server}/{repo}"
    return Config(
        repo_root=repo_root,
        repo_url=repo_url,
        wiki_url=args.wiki_url or f"{repo_url}.wiki.git",
        dry=args.dry_run or environ.get("WIKI_DRY_RUN", "").lower() == "true",
        token=environ.get("WIKI_TOKEN") or None,
        sha=environ.get("GITHUB_SHA", "unknown")[:12],
    )


def blocked_auth(where: str, detail: str, environ: Mapping[str, str]) -> int:
    summary(
        f"BLOCKED: auth rejected {where} the wiki. Add the secret {TOKEN_SECRET} "
        f"to the wiki-publish environment (PAT, contents write).\n{detail}",
        environ,
    )
    return EXIT_AUTH


def clone_wiki(
    cfg: Config, wiki: Path, env: Mapping[str, str], environ: Mapping[str, str]
) -> int | None:
    """Clone the wiki into ``wiki``. Return an exit code to stop, or None to continue."""
    clone = run_git(
        ["-c", "core.symlinks=false", "clone", "--quiet", "--depth", "1", cfg.wiki_url, str(wiki)],
        None,
        env,
    )
    if clone.returncode == 0:
        return None
    kind = classify_failure(clone.stderr)
    detail = redact(clone.stderr.strip(), cfg.token)
    if kind == "auth":
        return blocked_auth("cloning", detail, environ)
    if kind == "external":
        print(f"EXTERNAL: git clone failed:\n{detail}", file=sys.stderr)
        return EXIT_EXTERNAL
    note = (
        "SKIP: the wiki repo does not exist yet. A person must create the first page once "
        "in the GitHub UI (Wiki tab, Create the first page). GitHub gives the same answer "
        "when the credential cannot see the repository. Nothing was published."
    )
    if not cfg.dry:
        summary(note, environ)
        return EXIT_OK
    print(
        note.replace("SKIP:", "NOTE:", 1).replace(" Nothing was published.", "")
        + " Planning against an empty wiki."
    )
    wiki.mkdir(parents=True)
    run_git(["init", "--quiet"], wiki, env)
    return None


def commit_and_push(
    cfg: Config, wiki: Path, env: Mapping[str, str], environ: Mapping[str, str]
) -> int:
    ident = [
        "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
    ]  # fmt: skip
    message = f"docs(wiki): mirror {SOURCE_DIR} from {cfg.sha}"
    commit = run_git([*ident, "commit", "--quiet", "-m", message], wiki, env)
    if commit.returncode != 0:
        print(f"EXTERNAL: git commit failed:\n{commit.stderr}", file=sys.stderr)
        return EXIT_EXTERNAL
    push = run_git(["push", "--quiet", "origin", "HEAD"], wiki, env)
    if push.returncode == 0:
        return EXIT_OK
    detail = redact(push.stderr.strip(), cfg.token)
    if classify_failure(push.stderr) == "auth":
        return blocked_auth("pushing to", detail, environ)
    print(f"EXTERNAL: git push failed:\n{detail}", file=sys.stderr)
    return EXIT_EXTERNAL


def sync(cfg: Config, plan: Plan, environ: Mapping[str, str]) -> int:
    env = git_env(cfg.token, cfg.wiki_url)
    with tempfile.TemporaryDirectory(prefix="wiki-") as tmp:
        wiki = Path(tmp) / "wiki"
        stop = clone_wiki(cfg, wiki, env, environ)
        if stop is not None:
            return stop
        apply_plan(plan, wiki)
        run_git(["add", "-A", "-f"], wiki, env)
        diff = run_git(["diff", "--cached", "--name-status"], wiki, env).stdout
        changes = [ln for ln in diff.splitlines() if ln.strip()]
        pages = len(plan.files)
        if not changes:
            summary(f"0 changes in {pages} files. Wiki already matches {SOURCE_DIR}.", environ)
            return EXIT_OK
        print("Planned wiki diff:\n" + "\n".join(changes))
        if cfg.dry:
            summary(f"DRY RUN: {len(changes)} changes in {pages} files. Nothing pushed.", environ)
            return EXIT_OK
        code = commit_and_push(cfg, wiki, env, environ)
        if code == EXIT_OK:
            summary(f"PUBLISHED: {len(changes)} changes in {pages} files.", environ)
        return code


def run(args: argparse.Namespace, environ: Mapping[str, str]) -> int:
    cfg = load_config(args, environ)
    if isinstance(cfg, str):
        print(cfg, file=sys.stderr)
        return EXIT_CONFIG
    try:
        plan = build_plan(cfg.repo_root / SOURCE_DIR, cfg.repo_root, cfg.repo_url)
    except SourceError as exc:
        print(f"SOURCE: cannot mirror {SOURCE_DIR}:\n{exc}", file=sys.stderr)
        return EXIT_LOGIC
    print(
        f"Planned {len(plan.files)} wiki files from {SOURCE_DIR}: " + ", ".join(sorted(plan.files))
    )
    if not cfg.dry and cfg.token is None and cfg.wiki_url.startswith("https://"):
        summary(
            f"SKIP: no credential. Add the secret {TOKEN_SECRET} to the wiki-publish "
            "environment (PAT, contents write), or pass a token that can push to the "
            "wiki as WIKI_TOKEN. Nothing was published.",
            environ,
        )
        return EXIT_OK
    return sync(cfg, plan, environ)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Mirror docs/training to the GitHub wiki.")
    p.add_argument(
        "--dry-run", action="store_true", help="print the planned wiki diff, push nothing"
    )
    p.add_argument("--repo", help="owner/name; defaults to GITHUB_REPOSITORY")
    p.add_argument("--repo-root", default=".", help="repository root (default: cwd)")
    p.add_argument("--wiki-url", help="override the wiki remote (tests use a local bare repo)")
    return p


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    return run(build_parser().parse_args(argv), os.environ if environ is None else environ)


if __name__ == "__main__":
    sys.exit(main())
