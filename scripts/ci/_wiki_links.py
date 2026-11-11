"""Link handling for scripts/ci/publish_wiki.py (issue #7202).

Rewrites the links in a docs/training page for the wiki and reads the page order
from README.md. Fenced blocks are never touched. Inline code spans are never
rewritten, but link text may contain one, as in ``[`page.md`](page.md)``.
Reference definitions follow the same rules as inline links: an angle bracket
destination is unwrapped, and a definition that an image reference uses gets
``?raw=true``.

Raises ``SourceError`` for a link the wiki could not serve: a target that leaves
the repository (lexically or through a symbolic link) or does not exist.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable, Mapping
from pathlib import Path

SOURCE_DIR = "docs/training"
BRANCH = "main"
SCHEME_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")
# The destination of an inline link or image: ](dest "title"). The text before it is
# paired by bracket_pairs, not by this pattern, so link text may hold brackets, code
# spans, and images (a clickable image) without any nested or ambiguous quantifier.
DEST_RE = re.compile(r'\]\((?P<dest><[^>\n]+>|[^)\s]+)(?P<title>\s+"[^"\n]*")?\)')
REF_LINK_RE = re.compile(
    r"^(?P<pre>\s{0,3}\[(?P<label>[^\]^\n][^\]\n]*)\]:\s+)(?P<target>(?:<[^>\n]+>|\S+))"
)
IMAGE_REF_RE = re.compile(r"!\[(?P<alt>[^\]\n]*)\](?:\[(?P<label>[^\]\n]*)\])?(?!\()")
CODE_SPAN_RE = re.compile(r"(`+[^`\n]*`+)")
FENCE_RE = re.compile(r"^ {0,3}(?P<mark>`{3,}|~{3,})(?P<info>.*)$")


def safe(text: str) -> str:
    """Neutralize text before it reaches a log line: no workflow commands, no line breaks."""
    return text.replace("::", ":\u200b:").replace("\n", "\\n").replace("\r", "\\r")


class SourceError(Exception):
    """The source tree cannot be mirrored faithfully (exit 1)."""


def split_fenced(text: str) -> list[tuple[str, bool]]:
    """Return (line, in_fence) pairs. Fence delimiter lines count as fenced.

    A fence opens with three or more backticks or tildes. It closes only on the
    same character, at least as many of them, and nothing after, so a four
    backtick wrapper can hold a three backtick example. An unclosed fence runs
    to the end of the text.
    """
    out: list[tuple[str, bool]] = []
    opened = ""
    for line in text.split("\n"):
        found = FENCE_RE.match(line)
        if not opened:
            if found and not (found.group("mark")[0] == "`" and "`" in found.group("info")):
                opened = found.group("mark")
            out.append((line, bool(opened)))
            continue
        out.append((line, True))
        if found and not found.group("info").strip():
            mark = found.group("mark")
            if mark[0] == opened[0] and len(mark) >= len(opened):
                opened = ""
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


def label_key(label: str) -> str:
    """Normalize a reference label the way Markdown matches it."""
    return " ".join(label.split()).casefold()


def image_labels(text: str) -> set[str]:
    """Labels that an image reference uses: ``![alt][label]``, ``![label][]``, ``![label]``."""
    found: set[str] = set()
    for line, fenced in split_fenced(text):
        if fenced:
            continue
        masked, _ = mask_code(line)
        for match in IMAGE_REF_RE.finditer(masked):
            found.add(label_key(match.group("label") or match.group("alt")))
    return found


def rewrite_links(
    text: str, *, repo_root: Path, repo_url: str, published: Mapping[str, str]
) -> str:
    """Rewrite links outside fenced blocks and inline code spans."""
    images = image_labels(text)

    def one(target: str, image: bool) -> str:
        return rewrite_target(
            target, repo_root=repo_root, repo_url=repo_url, published=published, image=image
        )

    def rewrite_dest(raw: str, image: bool) -> str:
        """Rewrite a destination, keeping its angle brackets when it had them."""
        angle = raw.startswith("<")
        new = one(raw[1:-1] if angle else raw, image)
        return f"<{new}>" if angle else new

    def ref(match: re.Match[str]) -> str:
        image = label_key(match.group("label")) in images
        return match.group("pre") + rewrite_dest(match.group("target"), image)

    lines = []
    for line, fenced in split_fenced(text):
        if fenced:
            lines.append(line)
            continue
        masked, spans = mask_code(line)
        masked = rewrite_inline(REF_LINK_RE.sub(ref, masked), rewrite_dest)
        lines.append(unmask_code(masked, spans))
    return "\n".join(lines)


def bracket_pairs(line: str) -> dict[int, int]:
    """Map the index of each ``]`` to the index of the ``[`` that opens it. One pass, linear."""
    stack: list[int] = []
    pairs: dict[int, int] = {}
    for index, char in enumerate(line):
        if char == "[":
            stack.append(index)
        elif char == "]" and stack:
            pairs[index] = stack.pop()
    return pairs


def rewrite_inline(masked: str, rewrite_dest: Callable[[str, bool], str]) -> str:
    """Rewrite the destination of every inline link and image on a masked line."""
    pairs = bracket_pairs(masked)

    def inline(match: re.Match[str]) -> str:
        opener = pairs.get(match.start())
        if opener is None:
            return match.group(0)  # a stray "](x)" with no "[" is prose, not a link
        image = opener > 0 and masked[opener - 1] == "!"
        dest = rewrite_dest(match.group("dest"), image)
        return f"]({dest}{match.group('title') or ''})"

    return DEST_RE.sub(inline, masked)


def link_targets(masked: str) -> list[str]:
    """Every destination on a masked line: inline links and images, and definitions.

    A clickable image, ``[![alt](img)](page)``, yields both ``img`` and ``page``.
    """
    pairs = bracket_pairs(masked)
    found = [m.group("dest").strip("<>") for m in DEST_RE.finditer(masked) if m.start() in pairs]
    found += [m.group("target").strip("<>") for m in REF_LINK_RE.finditer(masked)]
    return found


def readme_page_order(readme: str) -> list[str]:
    """Source file names README.md links to, first occurrence only, in order."""
    seen: list[str] = []
    for line, fenced in split_fenced(readme):
        if fenced:
            continue
        masked, _ = mask_code(line)
        for target in link_targets(masked):
            if SCHEME_RE.match(target) or target.startswith("#"):
                continue
            resolved = posixpath.normpath(posixpath.join(SOURCE_DIR, strip_target(target)))
            parent, base = posixpath.split(resolved)
            if parent == SOURCE_DIR and base not in seen:
                seen.append(base)
    return seen
