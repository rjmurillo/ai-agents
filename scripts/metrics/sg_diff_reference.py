"""Content-addressed diff-reference model for the security-guidance prompt (#5856).

Evaluation model only. Not wired to any hook, skill, or runtime path. It exists
to test whether an exact artifact reference can replace the inline capped diff
that ``security-guidance``'s agentic reviewer embeds in its investigate prompt,
without losing review correctness, provenance, or fail-safe behavior (see
``.project-toolkit/specs/SPEC-5856-security-guidance-diff-prompt-dedup.md``).

This module owns prompt construction and diff capping: the port of the
plugin's byte-capping helper and the byte-for-byte reproduction of its inline
investigate prompt. The content-addressed artifact store (write, prune,
resolve) lives in ``scripts/metrics/sg_diff_artifact.py``, and the producer
and read-time tool live in ``scripts/metrics/sg_diff_producer.py``. The
producer imports ``assemble_prompt`` and ``capped_diff_text`` from here to
build the reference-mode prompt and the inline fallback text.

Plugin under test: ``security-guidance@claude-plugins-official`` 2.0.8,
marketplace commit ``55b58ec6e5649104f926ba7558b567dc8d33c5ff``.

Canonical sources this module mirrors, cited per
``.claude/rules/canonical-source-mirror.md``:

1. ``review_api.cap_diff_for_prompt`` (installed at
   ``<plugin>/hooks/review_api.py:31-64``) for per-file/total byte capping.
   Verbatim at the time this module was written::

       DIFF_PER_FILE_BYTES = int(os.environ.get("DIFF_PER_FILE_BYTES", "80000"))
       DIFF_TOTAL_BYTES = int(os.environ.get("DIFF_TOTAL_BYTES", "400000"))


       def cap_diff_for_prompt(
           files: list[tuple[str, str]],
       ) -> tuple[list[tuple[str, str]], int]:
           out: list[tuple[str, str]] = []
           dropped = 0
           total = 0
           for fp, content in files:
               if len(content) > DIFF_PER_FILE_BYTES:
                   dropped += len(content) - DIFF_PER_FILE_BYTES
                   content = (
                       content[:DIFF_PER_FILE_BYTES]
                       + "\\n... [truncated by security-guidance: file exceeds per-file byte cap]"
                   )
               room = DIFF_TOTAL_BYTES - total
               if room <= 0:
                   dropped += len(content)
                   out.append(
                       (fp, "[omitted by security-guidance: total diff byte cap reached]")
                   )
                   continue
               if len(content) > room:
                   dropped += len(content) - room
                   content = (
                       content[:room]
                       + "\\n... [truncated by security-guidance: total diff byte cap reached]"
                   )
               total += len(content)
               out.append((fp, content))
           return out, dropped

   ``_cap_diff_for_prompt`` below is that function with the two module-level
   env-derived constants turned into parameters (``per_file_bytes``,
   ``total_bytes``) so a caller can pick caps without mutating process
   environment. The cap comparisons operate on ``len(content)``, i.e. Python
   string length (characters), not UTF-8 byte count, despite the "BYTES"
   naming in the canonical source. That mismatch is inherited, not
   introduced, and this port preserves it so the importlib-compared test
   (below) agrees with the installed plugin byte-for-byte.

2. ``llm.py``'s ``agentic_review`` investigate ``user_prompt`` construction
   (installed at ``<plugin>/hooks/llm.py:1210-1222``), the prompt the real
   hook path actually sends. Verbatim at the time this module was written::

       diff_text = "\\n\\n".join(
           f"=== DIFF: {fp} ===\\n{content}" for fp, content in _cap_files_for_prompt(diff_files)
       )
       user_prompt = (
           "Review this change for security vulnerabilities.\\n\\n"
           f"Changed files (you may Read these and any other file in the repo):\\n"
           + "\\n".join(f"  - {p}" for p in touched_paths[:50])
           + context_note
           + "\\n\\nUnified diff (only + lines are new):\\n\\n"
           + diff_text
           + "\\n\\nInvestigate per the method in your instructions, then return "
           "the findings list."
       )

   ``build_inline_prompt`` below reproduces this exactly.

Stricter/looser/different than canonical
-----------------------------------------

``review_api.py`` also ships an importable ``build_investigate_prompt``
(``<plugin>/hooks/review_api.py:156-176``) that looks like the natural mirror
target instead of ``llm.py``. It is deliberately NOT what ``build_inline_prompt``
mirrors, because it diverges from the real hook path: it appends
``extensibility.guidance_block()`` (a user-configurable
``<project-security-guidance>`` block, empty unless the installing user has
project-specific security guidance configured) immediately before the
"Investigate per the method..." tail, and ``agentic_review``'s own inline
construction in ``llm.py`` does not call ``extensibility.guidance_block()`` at
all. Mirroring ``review_api.build_investigate_prompt`` would therefore produce
a prompt the real hook never sends whenever a user has that config file. This
module mirrors ``llm.py`` instead, since that is the code path that actually
runs, and the plugin-comparison test below asserts against ``llm.py``'s
literal format, not ``review_api``'s.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

# Defaults mirror review_api.py's env-parsed defaults ("80000" / "400000");
# see the module docstring's citation. Parameters here replace the env
# indirection so a caller need not mutate process environment to override.
DEFAULT_PER_FILE_BYTES = 80_000
DEFAULT_TOTAL_BYTES = 400_000

_DIFF_SECTION_RE = re.compile(r"^=== DIFF: (.+) ===$")


GIT_TIMEOUT_S = 30
"""Upper bound for one git subprocess; a locked repository raises instead of hanging."""


def run_git(repo_dir: str | Path, args: list[str]) -> str:
    """Run a git subcommand in ``repo_dir`` and return trimmed stdout.

    Shared by this module and ``sg_reference_ab_fixtures`` so the subprocess
    convention has one owner. Raises ``subprocess.TimeoutExpired`` after
    ``GIT_TIMEOUT_S`` seconds.

    Raises ``subprocess.CalledProcessError`` on a non-zero exit so callers can
    distinguish "git says no" (e.g. no configured remote) from "git ran fine
    and said nothing". ``encoding="utf-8", errors="replace"`` per the
    subprocess-capture convention this repository enforces
    (``scripts/validation/check_subprocess_encoding.py``).
    """
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=GIT_TIMEOUT_S,
    )
    return result.stdout.strip()


def repo_identity(repo_dir: str | Path) -> str:
    """A stable identity for the repository that owns ``repo_dir``.

    sha256 over the realpath of ``git rev-parse --git-common-dir`` (the
    directory every worktree of one repository shares, so two worktrees of
    the same repository resolve to the same identity) plus
    ``git config --get remote.origin.url`` (empty string when unset). Two
    unrelated repositories with no remote configured still differ, because
    their ``--git-common-dir`` realpaths differ.
    """
    common_dir_raw = run_git(repo_dir, ["rev-parse", "--git-common-dir"])
    common_dir = Path(common_dir_raw)
    if not common_dir.is_absolute():
        common_dir = Path(repo_dir).resolve() / common_dir
    realpath = os.path.realpath(common_dir)
    try:
        remote_url = run_git(repo_dir, ["config", "--get", "remote.origin.url"])
    except subprocess.CalledProcessError:
        remote_url = ""
    digest_input = f"{realpath}\x00{remote_url}".encode()
    return hashlib.sha256(digest_input).hexdigest()


def _cap_diff_for_prompt(
    files: Sequence[tuple[str, str]],
    per_file_bytes: int,
    total_bytes: int,
) -> tuple[list[tuple[str, str]], int]:
    """Port of ``review_api.cap_diff_for_prompt``; see module docstring citation 1."""
    out: list[tuple[str, str]] = []
    dropped = 0
    total = 0
    for fp, content in files:
        if len(content) > per_file_bytes:
            dropped += len(content) - per_file_bytes
            content = (
                content[:per_file_bytes]
                + "\n... [truncated by security-guidance: file exceeds per-file byte cap]"
            )
        room = total_bytes - total
        if room <= 0:
            dropped += len(content)
            out.append((fp, "[omitted by security-guidance: total diff byte cap reached]"))
            continue
        if len(content) > room:
            dropped += len(content) - room
            content = (
                content[:room]
                + "\n... [truncated by security-guidance: total diff byte cap reached]"
            )
        total += len(content)
        out.append((fp, content))
    return out, dropped


def _capped_diff_text(
    diff_files: Sequence[tuple[str, str]],
    per_file_bytes: int,
    total_bytes: int,
) -> tuple[str, int]:
    capped, dropped = _cap_diff_for_prompt(list(diff_files), per_file_bytes, total_bytes)
    diff_text = "\n\n".join(f"=== DIFF: {fp} ===\n{content}" for fp, content in capped)
    return diff_text, dropped


def capped_diff_text(
    diff_files: Sequence[tuple[str, str]],
    *,
    per_file_bytes: int = DEFAULT_PER_FILE_BYTES,
    total_bytes: int = DEFAULT_TOTAL_BYTES,
) -> tuple[str, int]:
    """Public accessor for the same capped diff text :func:`build_inline_prompt` embeds.

    Exists so a caller holding an ``ArtifactRef`` (see ``sg_diff_artifact``;
    for example ``sg_diff_producer.produce_prompt``'s fail-safe fallback) can reconstruct the
    exact inline diff text without duplicating the capping logic.
    """
    return _capped_diff_text(diff_files, per_file_bytes, total_bytes)


def assemble_prompt(touched_paths: Sequence[str], diff_text: str, context_note: str) -> str:
    """Byte-for-byte port of ``llm.py``'s inline ``user_prompt``; see docstring citation 2.

    Public (not module-private) because ``sg_diff_producer.build_referenced_prompt``
    reuses it verbatim to assemble the reference-mode prompt around a pointer
    block instead of the capped diff text, so both prompt shapes share exactly
    one header/footer implementation.
    """
    return (
        "Review this change for security vulnerabilities.\n\n"
        "Changed files (you may Read these and any other file in the repo):\n"
        + "\n".join(f"  - {p}" for p in touched_paths[:50])
        + context_note
        + "\n\nUnified diff (only + lines are new):\n\n"
        + diff_text
        + "\n\nInvestigate per the method in your instructions, then return "
        "the findings list."
    )


def build_inline_prompt(
    touched_paths: Sequence[str],
    diff_files: Sequence[tuple[str, str]],
    context_note: str = "",
    *,
    per_file_bytes: int = DEFAULT_PER_FILE_BYTES,
    total_bytes: int = DEFAULT_TOTAL_BYTES,
) -> str:
    """The plugin's inline investigate prompt, reproduced byte for byte."""
    diff_text, _dropped = _capped_diff_text(diff_files, per_file_bytes, total_bytes)
    return assemble_prompt(touched_paths, diff_text, context_note)


def diff_line_semantics(diff_text: str) -> dict[str, Counter[str]]:
    """Multiset of ``+``/``-`` lines per ``=== DIFF: path ===`` section.

    ``+++``/``---`` unified-diff file headers are excluded, matching the
    task's REQ-6 semantics-equivalence contract: what matters is the set of
    real additions and deletions, not the diff format's own file markers.
    Keyed by the full line (including its ``+``/``-`` prefix) so two runs'
    outputs can be compared for exact multiset equality with ``==``.
    """
    result: dict[str, Counter[str]] = {}
    counter: Counter[str] | None = None
    for line in diff_text.splitlines():
        section = _DIFF_SECTION_RE.match(line)
        if section:
            counter = result.setdefault(section.group(1), Counter())
            continue
        if counter is None:
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") or line.startswith("-"):
            counter[line] += 1
    return result
