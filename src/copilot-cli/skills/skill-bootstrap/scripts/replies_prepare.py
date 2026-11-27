"""The `prepare` pipeline: parse, window, limit, classify, aggregate, sample.

Returns an aggregate payload. The payload holds counts, reason codes, and the
run directory path. It never holds transcript text, session ids, or project
paths.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import replies_flags as fl
from replies_corpus import (
    MAX_FILE_BYTES,
    ConfigError,
    Source,
    Transcript,
    discover,
    parse_transcript,
    parse_ts,
    read_meta,
)
from replies_sample import (
    NEXT_CLIP,
    ReplyRec,
    discard_run_dir,
    draw,
    make_key,
    make_run_dir,
    strata_of,
    write_run,
)

SCHEMA = "reply-friction/prepare/v1"
KIND_FINAL = "final_reply"
KIND_HANDBACK = "subagent_handback"
PUSH_FLAGS = frozenset({"ownjob", "generic_nudge", "prior_authority"})
MAX_CONTROLS = 20
TAG_OPENER = re.compile(r"</?[A-Za-z][\w:-]*[\s>/]")


@dataclass
class Config:
    stores: list[Path]
    before: datetime
    since: datetime | None
    exclude: set[str]
    limit: int
    run_dir: str
    seed: int
    per_kind: int
    replay_min: int
    markers: list[re.Pattern[str]]
    cwd: Path
    relays: list[re.Pattern[str]] = field(default_factory=list)
    machine_first: list[re.Pattern[str]] = field(default_factory=list)
    entrypoints: set[str] = field(default_factory=set)


def _mark_relays(turns: list[Any], cfg: Config) -> None:
    """Reclass a user turn the host or another agent wrote, so it is not a typed follow-up.

    A turn that opens with a tag (`<name>` or `</name>`) is host markup. `--machine-turn` adds the
    relay openers of one setup, matched at the start of the turn.
    """
    for turn in turns:
        if turn.role != "human":
            continue
        head = turn.text.lstrip()
        if TAG_OPENER.match(head) or any(p.match(head) for p in cfg.relays):
            turn.role, turn.reason = "machine", "relay"


@dataclass
class Summary:
    src: Source
    first: datetime
    last: datetime
    prompt_fp: str | None = None
    eval_marked: bool = False
    replies: list[ReplyRec] = field(default_factory=list)
    machine: Counter[str] = field(default_factory=Counter)
    turns: Counter[str] = field(default_factory=Counter)
    errors: Counter[str] = field(default_factory=Counter)
    authority: Counter[str] = field(default_factory=Counter)
    meta_present: bool = False
    agent_type: str | None = None
    undated: int = 0
    parse_errors: int = 0
    entrypoint: str | None = None
    human_prompts: int = 0
    machine_opener: bool = False
    finished: bool | None = None
    followup_flags: Counter[str] = field(default_factory=Counter)
    pushes: Counter[str] = field(default_factory=Counter)


def _in_window(cfg: Config, ts: str | None) -> bool | None:
    """None when the turn has no usable timestamp."""
    when = parse_ts(ts)
    if when is None:
        return None
    return (cfg.since is None or when >= cfg.since) and when < cfg.before


def _next_class(nxt: Any) -> str:
    if nxt is None:
        return "none"
    if nxt.role == "human":
        return "human"
    if nxt.role == "machine":
        return "host_continue" if nxt.reason == "host_continue" else "machine"
    return nxt.role


def summarize(tr: Transcript, cfg: Config) -> Summary | None:
    """Reduce a transcript to counters and reply records. None when it has no usable span."""
    first, last = parse_ts(tr.first), parse_ts(tr.last)
    if first is None or last is None:
        return None
    sm = Summary(tr.src, first, last, parse_errors=tr.parse_errors, entrypoint=tr.entrypoint)
    sm.machine.update(tr.skipped)
    sm.meta_present, sm.agent_type, sm.finished = read_meta(tr.src)
    turns = tr.turns
    _mark_relays(turns, cfg)
    sm.human_prompts = sum(t.role == "human" for t in turns)
    opener = next((t for t in turns if t.role in ("human", "machine")), None)
    if opener is not None:
        sm.prompt_fp = fl.prompt_fingerprint(opener.text)
        sm.eval_marked = fl.is_eval_marked(opener.text)
        head = opener.text.lstrip()
        sm.machine_opener = not tr.src.child and (
            opener.reason == "relay" or any(p.match(head) for p in cfg.machine_first)
        )
    for i, turn in enumerate(turns):
        usable = _in_window(cfg, turn.ts)
        if usable is None:
            sm.undated += 1
            continue
        if not usable:
            continue
        _count_turn(sm, turns, i, cfg)
    if tr.src.child and sm.replies:
        sm.replies = sm.replies[-1:]
        sm.replies[0].kind = KIND_HANDBACK
    return sm


def _count_turn(sm: Summary, turns: list[Any], i: int, cfg: Config) -> None:
    turn = turns[i]
    nxt = turns[i + 1] if i + 1 < len(turns) else None
    if nxt is not None and not _in_window(cfg, nxt.ts):
        nxt = None
    if turn.role == "reply":
        sm.replies.append(_reply_rec(sm, turn, nxt, i, cfg))
    elif turn.role == "human":
        sm.turns["human"] += 1
        if i > 0 and turns[i - 1].role == "reply" and _in_window(cfg, turns[i - 1].ts):
            _count_followup(sm, turn.text, len(turns[i - 1].text))
    elif turn.role == "machine":
        sm.machine[turn.reason] += 1
    elif turn.role == "error":
        sm.errors[turn.reason] += 1
        if nxt is not None and nxt.role == "machine" and nxt.reason == "host_continue":
            sm.errors["then_host_continue"] += 1
    else:
        sm.turns["interrupt"] += 1


def _count_followup(sm: Summary, text: str, prev_len: int) -> None:
    """Count a typed follow-up. `prev_len` is the length of the reply it answers."""
    sm.turns["typed_followup"] += 1
    flags = fl.human_flags(text, prev_len)
    sm.followup_flags.update(flags)
    for flag in flags:
        if flag in ("prior_authority", "generic_nudge"):
            sm.authority[flag] += 1
    if PUSH_FLAGS.intersection(flags):
        # Order alone cannot tell whether either push grants authority.
        sm.pushes["later" if sm.pushes else "first_in_thread"] += 1


def _reply_rec(sm: Summary, turn: Any, nxt: Any, index: int, cfg: Config) -> ReplyRec:
    flags = fl.agent_flags(turn.text)
    next_human = None
    next_class = _next_class(nxt)
    if next_class == "human":
        flags += ["h_" + f for f in fl.human_flags(nxt.text, len(turn.text))]
        next_human = nxt.text[:NEXT_CLIP]
    hit = any(m.search(turn.text) for m in cfg.markers)
    return ReplyRec(
        key=make_key(sm.src.parent, sm.src.sid, index),
        kind=KIND_FINAL,
        flags=flags,
        reply=turn.text,
        next_class=next_class,
        next_human=next_human,
        marker_hit=hit,
    )


def collect(cfg: Config, excluded: Counter[str]) -> tuple[list[Summary], Counter[str]]:
    seen: set[Path] = set()
    found: Counter[str] = Counter()
    kept: list[Summary] = []
    for store in cfg.stores:
        for src in discover(store):
            real = src.path.resolve()
            if real in seen:
                continue
            seen.add(real)
            found["child" if src.child else "main"] += 1
            sm = _load(src, cfg, excluded)
            if sm is not None:
                kept.append(sm)
    return kept, found


def _load(src: Source, cfg: Config, excluded: Counter[str]) -> Summary | None:
    if src.sid in cfg.exclude or src.parent in cfg.exclude:
        excluded["session_flag"] += 1
        return None
    try:
        if src.path.stat().st_size > MAX_FILE_BYTES:
            excluded["oversize"] += 1
            return None
        tr = parse_transcript(src)
    except OSError:
        excluded["unreadable"] += 1
        return None
    sm = summarize(tr, cfg)
    if sm is None:
        excluded["no_timestamp"] += 1
        return None
    if sm.first >= cfg.before or (cfg.since is not None and sm.last < cfg.since):
        excluded["outside_window"] += 1
        return None
    return sm


def split_population(kept: list[Summary], cfg: Config, excluded: Counter[str]) -> list[Summary]:
    """Keep threads a person started. Drop a wrong entrypoint or a machine-written opener."""
    drop: dict[str, str] = {}
    for sm in kept:
        if sm.src.child:
            continue
        if cfg.entrypoints and (sm.entrypoint or "unknown") not in cfg.entrypoints:
            drop[sm.src.sid] = "entrypoint"
        elif sm.machine_opener:
            drop[sm.src.sid] = "machine_opener"
    out = []
    for sm in kept:
        reason = drop.get(sm.src.sid) or drop.get(sm.src.parent or "")
        if reason:
            excluded[reason + ("_children" if sm.src.child else "")] += 1
        else:
            out.append(sm)
    return out


def handback_counts(used: list[Summary]) -> dict[str, int]:
    """Subagent runs that returned nothing, did not finish, or repeat one brief."""
    kids = [s for s in used if s.src.child]
    briefs = Counter((s.src.parent, s.agent_type, s.prompt_fp) for s in kids if s.prompt_fp)
    repeats = [n for n in briefs.values() if n >= 2]
    return {
        "transcripts": len(kids),
        "no_reply": sum(1 for s in kids if not s.replies),
        "unfinished": sum(1 for s in kids if s.finished is False),
        "finish_not_recorded": sum(1 for s in kids if s.meta_present and s.finished is None),
        "repeat_groups": len(repeats),
        "repeat_transcripts": sum(repeats),
    }


def apply_limit(kept: list[Summary], limit: int, excluded: Counter[str]) -> list[Summary]:
    ordered = sorted(kept, key=lambda s: (-s.first.timestamp(), s.src.sid))
    excluded["limit"] += max(0, len(ordered) - limit)
    return ordered[:limit]


def split_replay(kept: list[Summary], replay_min: int, excluded: Counter[str]) -> list[Summary]:
    """Drop sessions that look like replayed eval prompts, and their subagent children."""
    mains = [s for s in kept if not s.src.child and s.prompt_fp and s.human_prompts == 1]
    counts = Counter(s.prompt_fp for s in mains)
    replay = {
        s.src.sid
        for s in kept
        if not s.src.child
        and (s.eval_marked or (s.human_prompts == 1 and counts[s.prompt_fp] >= replay_min))
    }
    out = []
    for sm in kept:
        if sm.src.sid in replay or sm.src.parent in replay:
            excluded["eval_replay_children" if sm.src.child else "eval_replay"] += 1
            excluded["eval_replay_replies"] += len(sm.replies)
        else:
            out.append(sm)
    return out


def aggregate(used: list[Summary]) -> dict[str, Any]:
    turns: Counter[str] = Counter()
    machine: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    authority: Counter[str] = Counter()
    meta: Counter[str] = Counter()
    followup: Counter[str] = Counter()
    pushes: Counter[str] = Counter()
    for sm in used:
        followup.update(sm.followup_flags)
        pushes.update(sm.pushes)
        pushes["threads"] += int(bool(sm.pushes))
        turns.update(sm.turns)
        machine.update(sm.machine)
        errors.update(sm.errors)
        authority.update(sm.authority)
        if sm.meta_present:
            meta[sm.agent_type or "unnamed"] += 1
    return {
        "turns": dict(turns),
        "machine": dict(machine),
        "errors": {k: v for k, v in errors.items() if k != "then_host_continue"},
        "errors_then_host_continue": errors["then_host_continue"],
        "host_continues": machine["host_continue"],
        "authority": {
            "prior_authority": authority["prior_authority"],
            "generic_nudge": authority["generic_nudge"],
        },
        "subagent_meta": dict(meta),
        "followups": {
            "typed": turns["typed_followup"],
            "flags": dict(sorted(followup.items())),
            "pushes": {k: pushes[k] for k in ("first_in_thread", "later", "threads")},
        },
        "handbacks": handback_counts(used),
    }


def reply_composition(recs: list[ReplyRec]) -> dict[str, Any]:
    by_kind: dict[str, Counter[str]] = {}
    flag_counts: Counter[str] = Counter()
    for rec in recs:
        bucket = by_kind.setdefault(rec.kind, Counter())
        bucket["total"] += 1
        bucket["flagged"] += int(rec.flagged)
        bucket["next_" + rec.next_class] += 1
        flag_counts.update(rec.flags)
    return {
        "by_kind": {k: dict(v) for k, v in sorted(by_kind.items())},
        "flags": dict(sorted(flag_counts.items())),
        "marker_hits": sum(1 for r in recs if r.marker_hit),
    }


def run_prepare(cfg: Config) -> dict[str, Any]:
    excluded: Counter[str] = Counter()
    kept, found = collect(cfg, excluded)
    parse_errors = sum(s.parse_errors for s in kept)
    entrypoints = Counter(s.entrypoint or "unknown" for s in kept if not s.src.child)
    people = split_population(kept, cfg, excluded)
    used = apply_limit(split_replay(people, cfg.replay_min, excluded), cfg.limit, excluded)
    recs = [rec for sm in used for rec in sm.replies]
    if not recs:
        raise ConfigError("no_replies_in_population")
    # A marker hit is a positive control: always sampled, never part of a rate.
    controls = sorted((r for r in recs if r.marker_hit), key=lambda r: r.key)[:MAX_CONTROLS]
    if cfg.markers and not controls:
        raise ConfigError("control_not_found")
    run_dir = make_run_dir(cfg.run_dir, cfg.stores, cfg.cwd)
    groups = strata_of([r for r in recs if not r.marker_hit])
    picked = draw(groups, cfg.seed, cfg.per_kind)
    try:
        digest = write_run(run_dir, picked, groups, cfg.seed, cfg.per_kind, controls)
    except OSError:
        discard_run_dir(run_dir)
        raise
    return {
        "command": "prepare",
        "schema": SCHEMA,
        "window": {
            "since": cfg.since.isoformat() if cfg.since else None,
            "before": cfg.before.isoformat(),
        },
        "params": {
            "seed": cfg.seed,
            "limit": cfg.limit,
            "sample_per_kind": cfg.per_kind,
            "replay_min": cfg.replay_min,
        },
        "population": {
            "stores": len(cfg.stores),
            "found": dict(found),
            "entrypoints": dict(sorted(entrypoints.items())),
            "used": {
                "main": sum(1 for s in used if not s.src.child),
                "children": sum(1 for s in used if s.src.child),
            },
            "excluded": dict(sorted(excluded.items())),
            "parse_errors": parse_errors,
        },
        **aggregate(used),
        "replies": reply_composition(recs),
        "strata": [
            {"kind": k, "flagged": f, "population": len(m)} for (k, f), m in sorted(groups.items())
        ],
        "sampled": len(picked),
        "controls_sampled": len(controls),
        "run_dir": str(run_dir),
        "evidence_sha256": digest,
    }
