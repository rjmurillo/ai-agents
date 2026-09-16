#!/usr/bin/env python3
"""Hazards H1 to H6 in `python-frontmatter`'s public API.

Evidence for `.agents/analysis/frontmatter-parser-build-vs-buy.md`. Each block
prints what a caller migrating from a hand-rolled parser would actually observe.
"""

from __future__ import annotations

from typing import Any

import frontmatter
import yaml
from frontmatter.default_handlers import SafeLoader as BoundLoader
from frontmatter.default_handlers import YAMLHandler


class PinnedYAMLHandler(YAMLHandler):
    """Bind ``yaml.SafeLoader`` explicitly, matching ADR-073's mandate (H5)."""

    # ANN401: the signature must match YAMLHandler.load verbatim
    # (frontmatter/default_handlers.py:255) or mypy rejects the override.
    def load(self, fm: str, **kwargs: object) -> Any:  # noqa: ANN401
        # setdefault upstream (default_handlers.py:259) will not overwrite this.
        kwargs["Loader"] = yaml.SafeLoader
        return super().load(fm, **kwargs)


def show(name: str, text: str) -> None:
    """Print metadata and content, or the exception a caller would see."""
    try:
        post = frontmatter.loads(text)
    except Exception as exc:
        first_line = str(exc).splitlines()[0][:90]
        print(f"  {name:<34} RAISES {type(exc).__name__}: {first_line}")
        return
    print(f"  {name:<34} metadata={post.metadata!r} content={post.content!r}")


def main() -> int:
    print("H1: four distinct states collapse to the same empty metadata")
    show("no frontmatter", "Just body text.\n")
    show("unterminated", "---\nid: A\nBody.\n")
    show("empty block", "---\n---\nBody.\n")
    show("non-mapping (list)", "---\n- a\n- b\n---\nBody.\n")
    show("valid", "---\nid: A\n---\nBody.\n")

    print("\nH2: loads() strips the body")
    show("leading/trailing blank lines", "---\nid: A\n---\n\n\n# Title\n\nPara.\n")

    print("\nH3: raises where yaml_utils returns None")
    show("unclosed quote", '---\nid: "ADR-1\n---\nBody.\n')
    show("colon-bearing plain scalar", "---\ndesc: foo: bar\n---\nBody.\n")

    print("\nH4: Loader= injects a bogus metadata key")
    naive = frontmatter.loads("---\nid: A\n---\nB\n", Loader=yaml.SafeLoader)
    pinned = frontmatter.loads("---\nid: A\n---\nB\n", handler=PinnedYAMLHandler())
    print(f"  naive  loads(Loader=...) -> {naive.metadata!r}")
    print(f"  pinned handler           -> {pinned.metadata!r}")

    print("\nH5: loader selection depends on whether libyaml is present")
    print(f"  library binds: {BoundLoader.__name__}   yaml.safe_load uses: SafeLoader")

    print("\nH6: dumps() is not byte-faithful")
    original = "---\nid: A\nstatus: accepted\n---\nBody.\n"
    print(f"  in  {original!r}")
    print(f"  out {frontmatter.dumps(frontmatter.loads(original))!r}")

    print("\ndetect() + split() restore the discrimination loads() loses")
    handler = YAMLHandler()
    for name, text in {
        "no frontmatter": "Just body.\n",
        "unterminated": "---\nid: A\nBody.\n",
        "empty block": "---\n---\nBody.\n",
        "non-mapping (list)": "---\n- a\n---\nBody.\n",
        "valid": "---\nid: A\n---\nBody.\n",
    }.items():
        try:
            handler.split(text)
            split_result = "ok"
        except Exception as exc:
            split_result = type(exc).__name__
        print(f"  {name:<22} detect={handler.detect(text)!s:<6} split={split_result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
