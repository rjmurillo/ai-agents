"""Fixture repositories for the inline-vs-referenced diff A/B harness (#5856).

Evaluation harness support module only. Not wired to any hook. Split out of
``scripts/metrics/sg_reference_ab.py`` under the taste-lints file-size gate:
this module owns the four seeded git repositories (``f_repeat``, ``f_paths``,
``f_trunc``, ``f_mismatch``) the harness reviews, each reproducing one of the
REQ-6/REQ-7 scenarios (repeated diffs, renamed/deleted/added paths, per-file
and total byte-cap truncation, and a checkout-mismatch context directory).
Transport, tool handlers, and orchestration live in the sibling modules
``sg_reference_ab_api.py`` and ``sg_reference_ab.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.metrics import sg_diff_reference as sgd


@dataclass(frozen=True, slots=True)
class Fixture:
    """One reviewable change: a real repo on disk plus the diff text a caller
    (production hook or this harness) would send to the reviewer.
    ``fixture_dir`` is what the tool loop's ``read_file``/``grep`` operate
    against; for ``f_mismatch`` it differs from the repo whose ``repo_id``
    and ``head`` are used, reproducing the checkout-mismatch case REQ-7 covers.
    """

    name: str
    fixture_dir: Path
    touched_paths: list[str]
    diff_files: list[tuple[str, str]]
    context_note: str
    seeded_path: str
    preexisting_path: str
    per_file_bytes: int
    total_bytes: int
    repo_id: str
    head: str


def _write_repo_file(repo_dir: Path, rel_path: str, content: str) -> None:
    path = repo_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _init_fixture_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    sgd.run_git(repo_dir, ["init", "-q"])
    sgd.run_git(repo_dir, ["config", "user.email", "sg-ab@example.com"])
    sgd.run_git(repo_dir, ["config", "user.name", "sg-ab"])


def _commit_all(repo_dir: Path, message: str) -> str:
    sgd.run_git(repo_dir, ["add", "-A"])
    sgd.run_git(repo_dir, ["commit", "-q", "-m", message])
    return sgd.run_git(repo_dir, ["rev-parse", "HEAD"])


def _build_f_repeat(root: Path) -> Fixture:
    """Seeded: subprocess ``shell=True`` on attacker-influenced input."""
    repo_dir = root / "f_repeat"
    _init_fixture_repo(repo_dir)
    seeded_path, preexisting_path = "handler.py", "legacy.py"
    _write_repo_file(
        repo_dir,
        seeded_path,
        "import subprocess\n\ndef run_command(user_cmd):\n"
        "    subprocess.run(user_cmd, shell=True)\n",
    )
    _write_repo_file(
        repo_dir,
        preexisting_path,
        "import subprocess\n\ndef legacy_run(cmd):\n"
        "    subprocess.run(cmd, shell=True)  # pre-existing, unrelated to this diff\n",
    )
    head = _commit_all(repo_dir, "seed fixture")
    diff_files = [
        (
            seeded_path,
            "+import subprocess\n+\n+def run_command(user_cmd):\n"
            "+    subprocess.run(user_cmd, shell=True)\n",
        ),
        (
            preexisting_path,
            " import subprocess\n \n def legacy_run(cmd):\n"
            "     subprocess.run(cmd, shell=True)  # pre-existing, unrelated to this diff\n",
        ),
    ]
    return Fixture(
        name="f_repeat",
        fixture_dir=repo_dir,
        touched_paths=[seeded_path, preexisting_path],
        diff_files=diff_files,
        context_note="",
        seeded_path=seeded_path,
        preexisting_path=preexisting_path,
        per_file_bytes=sgd.DEFAULT_PER_FILE_BYTES,
        total_bytes=sgd.DEFAULT_TOTAL_BYTES,
        repo_id=sgd.repo_identity(repo_dir),
        head=head,
    )


def _build_f_paths(root: Path) -> Fixture:
    """Seeded: SQL built by string concatenation. Rename, delete, new file."""
    repo_dir = root / "f_paths"
    _init_fixture_repo(repo_dir)
    old_name, new_name = "queries_old.py", "queries.py"
    deleted_path, preexisting_path = "obsolete.py", "legacy_query.py"
    _write_repo_file(
        repo_dir,
        new_name,
        "def find_user(username):\n"
        "    query = \"SELECT * FROM users WHERE name = '\" + username + \"'\"\n"
        "    return db.execute(query)\n",
    )
    _write_repo_file(
        repo_dir,
        preexisting_path,
        "def find_order(order_id):\n"
        "    query = \"SELECT * FROM orders WHERE id = '\" + order_id + \"'\"  # pre-existing\n"
        "    return db.execute(query)\n",
    )
    head = _commit_all(repo_dir, "seed fixture")
    diff_files = [
        (old_name, "-def find_user_v1(username):\n-    pass\n"),
        (
            new_name,
            "+def find_user(username):\n"
            "+    query = \"SELECT * FROM users WHERE name = '\" + username + \"'\"\n"
            "+    return db.execute(query)\n",
        ),
        (deleted_path, "-def obsolete():\n-    pass\n"),
        (
            preexisting_path,
            " def find_order(order_id):\n"
            "     query = \"SELECT * FROM orders WHERE id = '\" + order_id"
            " + \"'\"  # pre-existing\n"
            "     return db.execute(query)\n",
        ),
    ]
    return Fixture(
        name="f_paths",
        fixture_dir=repo_dir,
        touched_paths=[old_name, new_name, deleted_path, preexisting_path],
        diff_files=diff_files,
        context_note="",
        seeded_path=new_name,
        preexisting_path=preexisting_path,
        per_file_bytes=sgd.DEFAULT_PER_FILE_BYTES,
        total_bytes=sgd.DEFAULT_TOTAL_BYTES,
        repo_id=sgd.repo_identity(repo_dir),
        head=head,
    )


def _build_f_trunc(root: Path) -> Fixture:
    """Seeded: path traversal via ``open(user_path)``. A large generated file
    that exceeds a small per-file cap sits after the vuln file in ordering.
    """
    repo_dir = root / "f_trunc"
    _init_fixture_repo(repo_dir)
    seeded_path, preexisting_path = "downloader.py", "legacy_reader.py"
    generated_path = "generated_data.json"
    _write_repo_file(
        repo_dir,
        seeded_path,
        "def read_upload(user_path):\n    with open(user_path) as f:\n        return f.read()\n",
    )
    _write_repo_file(
        repo_dir,
        preexisting_path,
        "def read_legacy(user_path):\n"
        "    with open(user_path) as f:  # pre-existing\n        return f.read()\n",
    )
    _write_repo_file(repo_dir, generated_path, "x" * 20_000)
    head = _commit_all(repo_dir, "seed fixture")
    diff_files = [
        (
            seeded_path,
            "+def read_upload(user_path):\n+    with open(user_path) as f:\n"
            "+        return f.read()\n",
        ),
        (
            preexisting_path,
            " def read_legacy(user_path):\n"
            "     with open(user_path) as f:  # pre-existing\n         return f.read()\n",
        ),
        (generated_path, "+" + ("x" * 20_000) + "\n"),
    ]
    return Fixture(
        name="f_trunc",
        fixture_dir=repo_dir,
        touched_paths=[seeded_path, preexisting_path, generated_path],
        diff_files=diff_files,
        context_note="",
        seeded_path=seeded_path,
        preexisting_path=preexisting_path,
        per_file_bytes=6_000,
        total_bytes=20_000,
        repo_id=sgd.repo_identity(repo_dir),
        head=head,
    )


_CONTEXT_MISMATCH_NOTE = (
    "\n\nNOTE: your working directory is the full repository for "
    "context (Grep for callers, read related files). The DIFF below "
    "is authoritative for what changed: the repo checkout may be at "
    "a different commit, so if a touched file looks different on "
    "disk than in the diff, trust the diff.\n"
)


def _build_f_mismatch(root: Path) -> Fixture:
    """Seeded: unsafe deserialization via ``yaml.load``. The context directory
    the tool loop reads from is checked out at the PARENT commit, so the
    on-disk file predates the seeded vulnerability the diff shows.
    """
    repo_dir = root / "f_mismatch"
    _init_fixture_repo(repo_dir)
    seeded_path, preexisting_path = "config_loader.py", "legacy_loader.py"
    _write_repo_file(repo_dir, seeded_path, "def load(s):\n    return None\n")
    _write_repo_file(
        repo_dir, preexisting_path, "def load_legacy(s):\n    return None  # pre-existing\n"
    )
    parent_head = _commit_all(repo_dir, "parent commit")

    _write_repo_file(
        repo_dir,
        seeded_path,
        "import yaml\n\ndef load(config_text):\n    return yaml.load(config_text)\n",
    )
    _write_repo_file(
        repo_dir,
        preexisting_path,
        "import yaml\n\ndef load_legacy(config_text):\n"
        "    return yaml.load(config_text)  # pre-existing\n",
    )
    head = _commit_all(repo_dir, "seed vuln commit")

    context_dir = root / "f_mismatch-context"
    sgd.run_git(repo_dir, ["worktree", "add", str(context_dir), parent_head])

    diff_files = [
        (
            seeded_path,
            "+import yaml\n+\n+def load(config_text):\n+    return yaml.load(config_text)\n",
        ),
        (
            preexisting_path,
            " import yaml\n \n def load_legacy(config_text):\n"
            "     return yaml.load(config_text)  # pre-existing\n",
        ),
    ]
    return Fixture(
        name="f_mismatch",
        fixture_dir=context_dir,
        touched_paths=[seeded_path, preexisting_path],
        diff_files=diff_files,
        context_note=_CONTEXT_MISMATCH_NOTE,
        seeded_path=seeded_path,
        preexisting_path=preexisting_path,
        per_file_bytes=sgd.DEFAULT_PER_FILE_BYTES,
        total_bytes=sgd.DEFAULT_TOTAL_BYTES,
        repo_id=sgd.repo_identity(repo_dir),
        head=head,
    )


_FIXTURE_BUILDERS = {
    "f_repeat": _build_f_repeat,
    "f_paths": _build_f_paths,
    "f_trunc": _build_f_trunc,
    "f_mismatch": _build_f_mismatch,
}

FIXTURE_NAMES = tuple(_FIXTURE_BUILDERS)
"""Every fixture name, in run order. The CLI validates ``--fixtures`` against it."""


def build_fixtures(root: Path, names: Sequence[str]) -> list[Fixture]:
    return [_FIXTURE_BUILDERS[name](root) for name in names]
