"""Link handling for scripts/ci/publish_wiki.py (issue #7202).

Rewrites the links in a docs/training page for the wiki and reads the page order
from README.md. Fenced blocks are never touched. Inline code spans are never
rewritten, but link text may contain one, as in ``[`page.md`](page.md)``.

Raises ``SourceError`` for a link the wiki could not serve: a target that leaves
the repository (lexically or through a symbolic link) or does not exist.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from pathlib import Path

SOURCE_DIR = "docs/training"
BRANCH = "main"
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


def mask_code(line: str) -> tuple[str, list[str]]:
    """Swap each inline code span for a placeholder, so link text may hold a code span."""
    spans: list[str] = []

    def hide(match: re.Match[str]) -> str:
        spans.append(match.group(0))
        return f"\x00{len(spans) - 1}\x00"

    return CODE_SPAN_RE.sub(hide, line), spans


def unmask_code(line: str, spans: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], line)


def strip_target(target: str) -> str:
    """The path part of a link target, without ``#fragment`` or ``?query``."""
    return target.partition("#")[0].partition("?")[0]


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
        masked, spans = mask_code(line)
        masked = INLINE_LINK_RE.sub(inline, REF_LINK_RE.sub(ref, masked))
        lines.append(unmask_code(masked, spans))
    return "\n".join(lines)


def readme_page_order(readme: str) -> list[str]:
    """Source file names README.md links to, first occurrence only, in order."""
    seen: list[str] = []
    for line, fenced in split_fenced(readme):
        if fenced:
            continue
        masked, _ = mask_code(line)
        targets = [m.group(2).strip("<>") for m in INLINE_LINK_RE.finditer(masked)]
        targets += [m.group(2) for m in REF_LINK_RE.finditer(masked)]
        for target in targets:
            if SCHEME_RE.match(target) or target.startswith("#"):
                continue
            resolved = posixpath.normpath(posixpath.join(SOURCE_DIR, strip_target(target)))
            parent, base = posixpath.split(resolved)
            if parent == SOURCE_DIR and base not in seen:
                seen.append(base)
    return seen
