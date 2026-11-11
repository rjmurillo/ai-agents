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
The repository comes from --repo, GITHUB_REPOSITORY, or the origin remote.

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
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.ci._wiki_links import (  # noqa: E402
    BRANCH,
    readme_page_order,
)
from scripts.ci._wiki_links import SOURCE_DIR as SOURCE_DIR  # noqa: E402  (re-export)
from scripts.ci._wiki_links import SourceError as SourceError  # noqa: E402  (re-export)
from scripts.ci._wiki_links import rewrite_links as rewrite_links  # noqa: E402  (re-export)
from scripts.ci._wiki_links import safe as safe  # noqa: E402  (re-export)
from scripts.ci._wiki_links import split_fenced as split_fenced  # noqa: E402  (re-export)

EXIT_OK, EXIT_LOGIC, EXIT_CONFIG, EXIT_EXTERNAL, EXIT_AUTH = 0, 1, 2, 3, 4

HOME = "Home"
PUSH_SETTING_NAME = "WIKI_PUSH_TOKEN"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")


@dataclass(frozen=True)
class Plan:
    """Wiki files to write, keyed by file name, plus the sidebar order."""

    files: dict[str, str]
    order: list[tuple[str, str]]  # (title, page name) in README link order


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
        if "\x00" in head:
            problems.append(f"{name}: contains a NUL character, the link masker reserves it")
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


def clear_entry(path: Path) -> None:
    """Remove a file, a symbolic link (never its target), or a directory."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def apply_plan(plan: Plan, wiki: Path) -> None:
    """Make the wiki working tree hold exactly the planned Markdown pages."""
    for stale in sorted(p for p in wiki.glob("*.md") if p.name not in plan.files):
        clear_entry(stale)
    for name, content in plan.files.items():
        target = wiki / name
        if target.is_symlink() or target.is_dir():
            clear_entry(target)  # never write through a link or into a directory
        target.write_text(content, encoding="utf-8", newline="\n")


@dataclass(frozen=True)
class Config:
    repo_root: Path
    repo_url: str
    wiki_url: str
    dry: bool
    token: str | None
    sha: str


ORIGIN_RE = re.compile(r"github\.com[:/]+([^/\s]+/[^/\s]+?)(?:\.git)?/?$")


def origin_repo(repo_root: Path) -> str:
    """owner/name from the ``origin`` remote of ``repo_root``, or an empty string."""
    done = run_git(["config", "--get", "remote.origin.url"], repo_root, os.environ)
    match = ORIGIN_RE.search(done.stdout.strip()) if done.returncode == 0 else None
    return match.group(1) if match else ""


def load_config(args: argparse.Namespace, environ: Mapping[str, str]) -> Config | str:
    """Return a Config, or a CONFIG error message."""
    repo_root = Path(args.repo_root).resolve()
    if not (repo_root / SOURCE_DIR).is_dir():
        return f"CONFIG: {SOURCE_DIR} not found under {repo_root}"
    if shutil.which("git") is None:
        return "CONFIG: git is not on PATH"
    repo = args.repo or environ.get("GITHUB_REPOSITORY", "") or origin_repo(repo_root)
    if not repo:
        return "CONFIG: set --repo or GITHUB_REPOSITORY, or add a github.com origin remote"
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
    detail = safe(detail)
    summary(
        f"BLOCKED: auth rejected {where} the wiki. Add the secret {PUSH_SETTING_NAME} "
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
    detail = safe(redact(clone.stderr.strip(), cfg.token))
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
        detail = safe(redact(commit.stderr, cfg.token))
        print(f"EXTERNAL: git commit failed:\n{detail}", file=sys.stderr)
        return EXIT_EXTERNAL
    push = run_git(["push", "--quiet", "origin", "HEAD"], wiki, env)
    if push.returncode == 0:
        return EXIT_OK
    detail = safe(redact(push.stderr.strip(), cfg.token))
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
            f"SKIP: no credential. Add the secret {PUSH_SETTING_NAME} to the wiki-publish "
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
