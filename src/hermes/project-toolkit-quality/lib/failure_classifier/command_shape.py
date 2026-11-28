"""The shape of a shell command: what it runs and what it writes.

Three questions the workaround and script detectors ask about a command line,
answered without running a shell:

- ``strip_cd_prefix``: the command without its leading ``cd <path> &&`` part.
- ``action_heads``: the programs it runs that act (a script, ``git push``),
  leaving out programs that only show or shape output (``tail``, ``grep``).
- ``shell_write_targets``: the files it writes by ``>``, ``>>``, or ``tee``.

Parsing is by pattern, so an unusual quoting form can be missed. A miss drops
a lead; it never invents one.

Stdlib only. No imports from the rest of the package.
"""

from __future__ import annotations

import posixpath
import re

# Text past this is not scanned, so a hostile command stays cheap (CWE-400).
SCAN_MAX_CHARS = 8000
HEADS_MAX = 40

_CD_PREFIX = re.compile(r"^\s*cd\s+(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s;&|]+)\s*(?:&&|;)\s*")
_HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1[^\n]*\n")
_QUOTED = re.compile(r"\"(?:[^\"\\\n]|\\.){0,2000}\"|'[^'\n]{0,2000}'")
_SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n`]|\$\(|[(){}]")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_INTERPRETER = re.compile(r"^(?:python[\d.]*|bash|sh|zsh|node|bun|pwsh|ruby|perl)$")
_WRITE = re.compile(r"(?:(?<![&\d<>])>>?(?![&>])|\btee\b(?:[ \t]+-a)?)[ \t]*([^\s|&;()<>]+)")

_QUOTE_MARK = "\x00q"
# Words that take the command after them, and how many words they consume first.
_WRAPPERS: dict[str, int] = {
    "env": 0,
    "sudo": 0,
    "time": 0,
    "nohup": 0,
    "exec": 0,
    "command": 0,
    "timeout": 1,
    "flock": 1,
}
_LAUNCHERS = frozenset({"ptk_run.py"})
_SUBCOMMAND_TOOLS = frozenset({"git", "gh", "npm", "docker", "cargo", "dotnet", "kubectl"})
# Programs that show, shape, or route output, and shell words. A later call made
# only of these looks at a failure; it does not get past it.
_VIEWERS = frozenset(
    {
        "cat", "head", "tail", "sed", "grep", "rg", "cut", "echo", "printf", "wc", "ls",
        "cd", "mkdir", "test", "[", "[[", "true", "false", "export", "set", "sleep", "tee",
        "sort", "uniq", "awk", "tr", "xargs", "find", "jq", "read", "mapfile", "while",
        "for", "do", "done", "if", "then", "else", "fi", "touch", "pwd", "ulimit", "wait",
        "git rev-parse", "git log", "git status", "git diff", "git show", "git ls-files",
        "git ls-remote", "git branch", "git merge-base",
        "git rev-list", "exit", "return",
    }
)  # fmt: skip


def strip_cd_prefix(command: str) -> str:
    """``command`` without leading ``cd <path> &&`` or ``cd <path>;`` parts."""
    text = command
    while (match := _CD_PREFIX.match(text)) is not None:
        text = text[match.end() :]
    return text


def _without_heredoc_bodies(command: str) -> str:
    """Drop each heredoc body: it is data or inline code, not shell words."""
    parts: list[str] = []
    pos = 0
    while (match := _HEREDOC.search(command, pos)) is not None:
        parts.append(command[pos : match.end()])
        closing = re.compile(r"^[ \t]*" + re.escape(match.group(2)) + r"[ \t]*$", re.MULTILINE)
        end = closing.search(command, match.end())
        if end is None:
            return "".join(parts)
        pos = end.end()
    parts.append(command[pos:])
    return "".join(parts)


def _first_plain(words: list[str], start: int) -> tuple[str, int]:
    """The first word at or after ``start`` that is not a flag, and its index."""
    for index in range(start, len(words)):
        if not words[index].startswith("-"):
            return words[index], index
    return "", len(words)


def _interpreter_head(words: list[str], index: int) -> str | None:
    following = words[index + 1] if index + 1 < len(words) else ""
    script, _ = _first_plain(words, index + 1)
    # ``python -c``, ``python -`` and ``python <<EOF`` run an inline program.
    if following in ("-c", "-e", "-") or not script or script.startswith(_QUOTE_MARK):
        return None
    target = posixpath.basename(script)
    if target in _LAUNCHERS:
        # A launcher runs the script named after it: that script is the action.
        launched, _ = _first_plain(words, words.index(script, index + 1) + 1)
        return posixpath.basename(launched) if launched else target
    return target


def _segment_head(segment: str) -> str | None:
    words = segment.split()
    index = 0
    while index < len(words):
        word = words[index]
        if _ASSIGNMENT.match(word):
            index += 1
        elif word in _WRAPPERS:
            index += 1 + _WRAPPERS[word]
        elif word == "uv" and index + 1 < len(words) and words[index + 1] == "run":
            _, index = _first_plain(words, index + 2)
        else:
            break
    if index >= len(words):
        return None
    word = words[index]
    if word.startswith(("-", _QUOTE_MARK, "<", ">", "$")):
        return None
    name = posixpath.basename(word)
    if _INTERPRETER.match(name):
        return _interpreter_head(words, index)
    if name in _SUBCOMMAND_TOOLS:
        sub, _ = _first_plain(words, index + 1)
        return f"{name} {sub}" if sub and not sub.startswith(_QUOTE_MARK) else name
    return name


def action_heads(command: str) -> frozenset[str]:
    """The programs ``command`` runs that act, by name.

    A script run through an interpreter or ``uv run`` is named by its file
    name, so ``python3 a/x.py`` and ``uv run python a/x.py`` share ``x.py``.
    ``git`` and similar tools are named with their subcommand. Programs that
    only view output, and inline programs, are left out.
    """
    text = _without_heredoc_bodies(command[:SCAN_MAX_CHARS])
    text = _QUOTED.sub(_QUOTE_MARK, text)
    heads: set[str] = set()
    for segment in _SEGMENT_SPLIT.split(text)[: HEADS_MAX * 4]:
        head = _segment_head(segment)
        if head and head not in _VIEWERS:
            heads.add(head)
            if len(heads) >= HEADS_MAX:
                break
    return frozenset(heads)


def shell_write_targets(command: str) -> list[str]:
    """Files ``command`` writes by ``> p``, ``>> p``, ``cat > p <<EOF``, or ``tee p``.

    Descriptor forms (``2>&1``, ``>&2``) are not files. A target that holds a
    variable or a substitution is skipped: its path is not known here.
    """
    text = _without_heredoc_bodies(command[:SCAN_MAX_CHARS])
    targets: list[str] = []
    for match in _WRITE.finditer(text):
        target = match.group(1).strip("\"'")
        if target and not any(mark in target for mark in "$`*?"):
            targets.append(target)
    return targets
