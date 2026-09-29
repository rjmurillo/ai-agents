"""One resolver per edge kind for the typed dependency closure (ADR-101).

Each function takes text or a parsed structure plus the tracked-file view and
returns edges, recorded values, and unresolved entries. None of them execute or
import anything from the tree they read: workflow, action and configuration
files are parsed as data, and Python files are read with `ast` only.

A token is treated as naming a repository file when it is a path with a slash
that matches a tracked file exactly. A token that looks repository-rooted (it
starts with `./` or with a top-level directory this repository uses) but matches
no tracked file is UNRESOLVED, not ignored, because a script, action input or
configuration entry that names a missing file is either a typo or a generated
path, and either way the closure cannot vouch for what runs. A token outside
those roots, such as `artifacts/report.xml` or a URL, is not a repository
reference and is skipped.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import tomllib
import yaml
from closure_model import (
    EDGE_ACTION_INPUT,
    EDGE_CONFIG_COMMAND,
    EDGE_WORKFLOW_REF,
    Edge,
    Unresolved,
)

REPO_ROOT_DIRS = frozenset(
    {".github", ".claude", "build", "scripts", "src", "templates", "tests", ".project-toolkit"}
)
EXEC_EXTENSIONS = (".py", ".sh", ".ps1")
FILE_EXTENSIONS = (
    *EXEC_EXTENSIONS,
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".txt",
    ".md",
    ".cfg",
    ".ini",
)
_TOKEN = re.compile(r"(?<![\w./~$@:-])((?:\./)?[A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+-]+)+)")
_SHA = re.compile(r"[0-9a-f]{40}")
_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class RepoTree:
    """The tracked files of a checkout and a way to hash them."""

    root: Path
    tracked: frozenset[str]

    @classmethod
    def from_git(cls, root: Path) -> RepoTree:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git ls-files failed in {root}: {result.stderr.decode(errors='replace')}"
            )
        paths = result.stdout.decode("utf-8", errors="replace").split("\0")
        return cls(root, frozenset(p for p in paths if p))

    def has(self, path: str) -> bool:
        return path in self.tracked

    def digest(self, path: str) -> str:
        return sha256((self.root / path).read_bytes()).hexdigest()


def normalize(token: str) -> str:
    return token[2:] if token.startswith("./") else token


# A missing file is only a finding when it is a kind the closure would have to
# vouch for. A missing `.md`, `.xml` or bare directory is far more often a
# generated report or an example in an `echo` than a dependency.
UNRESOLVED_EXTENSIONS = (*EXEC_EXTENSIONS, ".yml", ".yaml", ".json", ".toml")


def _repo_rooted(token: str) -> bool:
    if not token.endswith(UNRESOLVED_EXTENSIONS):
        return False
    return token.startswith("./") or token.split("/", maxsplit=1)[0] in REPO_ROOT_DIRS


def tokens_in(text: str) -> list[str]:
    """Path-like tokens in ``text``, computed values excluded."""
    return [m.group(1) for m in _TOKEN.finditer(text) if "${{" not in m.group(1)]


def resolve_tokens(
    text: str, source: str, kind: str, tree: RepoTree, base_dir: str = ""
) -> tuple[list[Edge], list[Unresolved]]:
    """Edges for every tracked file ``text`` names, and unresolved repo-rooted misses.

    ``base_dir`` is the directory a `./` token is also tried against, for text
    that lives in a script (`./helper.sh` next to it) rather than in a workflow
    (`./scripts/x.py` from the repository root).
    """
    edges: list[Edge] = []
    unresolved: list[Unresolved] = []
    for token in tokens_in(text):
        path = normalize(token)
        beside = f"{base_dir}/{path}" if base_dir and token.startswith("./") else ""
        if tree.has(path):
            edges.append(Edge(kind, source, path))
        elif beside and tree.has(beside):
            edges.append(Edge(kind, source, beside))
        elif _repo_rooted(token):
            unresolved.append(
                Unresolved(kind, source, f"names {path}, which is not a tracked file")
            )
    return edges, unresolved


def resolve_action_inputs(
    inputs: Mapping[str, Any], source: str, tree: RepoTree
) -> tuple[list[Edge], list[Unresolved]]:
    """Kind 3: `with:` values that name a repository file."""
    edges: list[Edge] = []
    unresolved: list[Unresolved] = []
    for name, value in inputs.items():
        if not isinstance(value, str):
            continue
        found, missing = resolve_tokens(value, f"{source}#with.{name}", EDGE_ACTION_INPUT, tree)
        edges.extend(found)
        unresolved.extend(missing)
    return edges, unresolved


def resolve_uses(
    uses: str, source: str, tree: RepoTree
) -> tuple[list[Edge], dict[str, str], list[Unresolved], str | None]:
    """Kind 4: a `uses:` reference.

    Returns edges, recorded pins, unresolved entries, and the action or workflow
    file to walk next (None for an external reference, which is pinned but not
    readable here).
    """
    if uses.startswith("./"):
        return _resolve_local_uses(uses, source, tree)
    if uses.startswith("docker://"):
        return _resolve_docker_uses(uses, source)
    if "@" not in uses:
        return [], {}, [Unresolved(EDGE_WORKFLOW_REF, source, f"uses {uses!r} names no ref")], None
    ref = uses.rsplit("@", maxsplit=1)[1]
    if _SHA.fullmatch(ref):
        return [], {f"uses:{uses}": "pinned"}, [], None
    return (
        [],
        {},
        [Unresolved(EDGE_WORKFLOW_REF, source, f"uses {uses!r} is not pinned to a commit")],
        None,
    )


def _resolve_local_uses(
    uses: str, source: str, tree: RepoTree
) -> tuple[list[Edge], dict[str, str], list[Unresolved], str | None]:
    target = normalize(uses.split("@", maxsplit=1)[0]).rstrip("/")
    candidates = (
        [target]
        if target.endswith((".yml", ".yaml"))
        else [
            f"{target}/action.yml",
            f"{target}/action.yaml",
        ]
    )
    for candidate in candidates:
        if tree.has(candidate):
            return [Edge(EDGE_WORKFLOW_REF, source, candidate)], {}, [], candidate
    detail = f"local uses {uses!r} resolves to no tracked action or workflow file"
    return [], {}, [Unresolved(EDGE_WORKFLOW_REF, source, detail)], None


def _resolve_docker_uses(
    uses: str, source: str
) -> tuple[list[Edge], dict[str, str], list[Unresolved], str | None]:
    if _DIGEST.search(uses):
        return [], {f"uses:{uses}": "pinned"}, [], None
    return (
        [],
        {},
        [Unresolved(EDGE_WORKFLOW_REF, source, f"docker image {uses!r} has no digest")],
        None,
    )


def _string_leaves(value: object, limit: int = 20_000) -> Iterable[str]:
    stack: list[object] = [value]
    seen = 0
    while stack and seen < limit:
        node = stack.pop()
        seen += 1
        if isinstance(node, str):
            yield node
        elif isinstance(node, Mapping):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def load_config(path: Path) -> object | None:
    """Parse a YAML, JSON or TOML file as data; None when it is not one of those."""
    suffix = path.suffix.lower()
    document: object | None = None
    try:
        raw = path.read_bytes()
        if suffix in {".yml", ".yaml"}:
            document = yaml.safe_load(raw)
        elif suffix == ".json":
            document = json.loads(raw)
        elif suffix == ".toml":
            document = tomllib.loads(raw.decode("utf-8"))
    except (OSError, ValueError, RecursionError, yaml.YAMLError, UnicodeDecodeError):
        return None
    return document


def resolve_config_commands(
    document: object, source: str, tree: RepoTree
) -> tuple[list[Edge], list[Unresolved]]:
    """Kind 2: executable files a configuration file's string values name."""
    edges: list[Edge] = []
    unresolved: list[Unresolved] = []
    for leaf in _string_leaves(document):
        for token in tokens_in(leaf):
            path = normalize(token)
            if not path.endswith(EXEC_EXTENSIONS):
                continue
            if tree.has(path):
                edges.append(Edge(EDGE_CONFIG_COMMAND, source, path))
            elif _repo_rooted(token):
                unresolved.append(
                    Unresolved(
                        EDGE_CONFIG_COMMAND, source, f"names {path}, which is not a tracked file"
                    )
                )
    return edges, unresolved
