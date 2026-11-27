"""Seeded per-kind flagged/unflagged sampling and the private run directory.

Privacy boundary: transcript text is written only to files inside a run
directory that this module creates fresh, outside every source store and
outside the repository holding the current working directory. Files are mode
0600, the directory 0700. Callers print counts, never rows.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from replies_corpus import ConfigError

REPLY_CLIP_HEAD = 2000
REPLY_CLIP_TAIL = 4000
NEXT_CLIP = 1500
EVIDENCE_NAME = "evidence.jsonl"
MANIFEST_NAME = "manifest.json"
RUN_SCHEMA = "reply-friction/run/v1"


@dataclass
class ReplyRec:
    key: str
    kind: str  # final_reply | subagent_handback
    flags: list[str]
    reply: str
    next_class: str
    next_human: str | None = None
    marker_hit: bool = False

    @property
    def flagged(self) -> bool:
        return bool(self.flags)


def clip_reply(text: str) -> str:
    """Keep the head and tail of a long reply. Quotes are checked against this stored form."""
    if len(text) <= REPLY_CLIP_HEAD + REPLY_CLIP_TAIL:
        return text
    return text[:REPLY_CLIP_HEAD] + "\n[...]\n" + text[-REPLY_CLIP_TAIL:]


def make_key(parent: str | None, sid: str, index: int) -> str:
    return hashlib.sha256(f"{parent or ''}/{sid}:{index}".encode()).hexdigest()[:16]


def strata_of(recs: list[ReplyRec]) -> dict[tuple[str, bool], list[ReplyRec]]:
    groups: dict[tuple[str, bool], list[ReplyRec]] = defaultdict(list)
    for rec in recs:
        groups[(rec.kind, rec.flagged)].append(rec)
    return groups


def draw(
    groups: dict[tuple[str, bool], list[ReplyRec]], seed: int, per_kind: int
) -> list[ReplyRec]:
    """Draw up to `per_kind` replies from each (kind, flagged) stratum, seeded and order independent."""
    picked: list[ReplyRec] = []
    for (kind, flagged), members in sorted(groups.items()):
        ordered = sorted(members, key=lambda r: r.key)
        rng = random.Random(f"{seed}|{kind}|{flagged}")
        picked += rng.sample(ordered, min(per_kind, len(ordered)))
    return sorted(picked, key=lambda r: (r.kind, not r.flagged, r.key))


def _repo_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def make_run_dir(raw: str, stores: list[Path], cwd: Path) -> Path:
    """Create the run directory. It must not exist and must sit outside stores and the cwd repo."""
    target = Path(raw).expanduser().resolve()
    if target.exists():
        raise ConfigError("run_dir_exists")
    forbidden = [store.resolve() for store in stores]
    root = _repo_root(cwd.resolve())
    if root is not None:
        forbidden.append(root)
    if any(target == bad or bad in target.parents for bad in forbidden):
        raise ConfigError("run_dir_inside_source_or_repo")
    if not target.parent.is_dir():
        raise ConfigError("run_dir_parent_missing")
    target.mkdir(mode=0o700)
    os.chmod(target, 0o700)
    return target


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def write_run(
    run_dir: Path,
    picked: list[ReplyRec],
    groups: dict[tuple[str, bool], list[ReplyRec]],
    seed: int,
    per_kind: int,
    controls: list[ReplyRec] | tuple[ReplyRec, ...] = (),
) -> str:
    """Write evidence.jsonl and manifest.json. Return the evidence sha256.

    Rows are ordered by key, so a judge cannot tell a control or a stratum from position.
    """
    rows = []
    control_ids = []
    for number, rec in enumerate(sorted([*picked, *controls], key=lambda r: r.key), start=1):
        if rec.marker_hit:
            control_ids.append(f"e{number:04d}")
        rows.append(
            {
                "id": f"e{number:04d}",
                "kind": rec.kind,
                "flagged": rec.flagged,
                "flags": rec.flags,
                "next_class": rec.next_class,
                "reply": clip_reply(rec.reply),
                "next_human": rec.next_human,
            }
        )
    blob = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode("utf-8")
    digest = hashlib.sha256(blob).hexdigest()
    sampled: dict[tuple[str, bool], int] = defaultdict(int)
    for rec in picked:
        sampled[(rec.kind, rec.flagged)] += 1
    manifest = {
        "schema": RUN_SCHEMA,
        "seed": seed,
        "sample_per_kind": per_kind,
        "evidence_rows": len(rows),
        "evidence_sha256": digest,
        "control_ids": control_ids,
        "strata": [
            {"kind": k, "flagged": f, "population": len(m), "sampled": sampled[(k, f)]}
            for (k, f), m in sorted(groups.items())
        ],
    }
    _write_private(run_dir / EVIDENCE_NAME, blob)
    _write_private(run_dir / MANIFEST_NAME, json.dumps(manifest, indent=1).encode("utf-8"))
    return digest
