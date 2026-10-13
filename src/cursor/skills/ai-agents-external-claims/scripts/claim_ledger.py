#!/usr/bin/env python3
"""Validate an external claims ledger before a research artifact is written.

The ``research`` skill writes durable artifacts: an analysis document, a
Serena memory, and an issue body. Before each write it records every external
claim (vendor, API, statistic, legal, project status, comparative) in a JSON
ledger and runs this script. The script checks that each claim names its
source, dates, and confidence, and that its disposition matches the evidence.
With ``--artifact`` it also checks that the artifact carries the checked
wording, not the unreviewed draft.

The script is a pure function of its two input files, so the same ledger and
artifact always get the same result. It opens no network connection.

EXIT CODES (ADR-035):
    0 - The ledger passed. A JSON summary is on stdout.
    1 - The ledger has defects. The JSON summary lists them.
    2 - Config error: a file is unreadable, the ledger is not valid JSON, or
        the arguments are bad.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DECISIONS = ("activate", "skip")
CATEGORIES = ("vendor", "api", "statistic", "legal", "project-status", "comparative")
SOURCE_KINDS = ("primary", "secondary", "none")
CONFIDENCES = ("high", "medium", "low", "none")
DISPOSITIONS = ("verified", "narrowed", "qualified", "removed")
TOP_LEVEL_KEYS = ("artifact", "activation", "claims")
CLAIM_TEXT_KEYS = ("id", "claim")
CLAIM_ENUMS = {
    "category": CATEGORIES,
    "confidence": CONFIDENCES,
    "disposition": DISPOSITIONS,
}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_AS_OF = re.compile(r"\bas of\b", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s)>\]\"'`]+")


def _text(value: object) -> bool:
    """Return True when value is a string with non-space content."""
    return isinstance(value, str) and bool(value.strip())


def _normalize(value: str) -> str:
    """Lowercase and collapse whitespace so a line wrap does not hide a match."""
    return " ".join(value.lower().split())


def _date_defect(where: str, key: str, value: object) -> list[str]:
    """Return a defect when a non-null date is not a real ISO date."""
    if value is None:
        return []
    if isinstance(value, str) and _DATE.match(value):
        try:
            dt.date.fromisoformat(value)
            return []
        except ValueError:
            pass
    return [f"{where}: source.{key} must be an ISO date YYYY-MM-DD, got {value!r}"]


def _activation_defects(ledger: dict[str, Any]) -> list[str]:
    """Check the activation decision against the claim list."""
    activation = ledger["activation"]
    if not isinstance(activation, dict):
        return ["activation must be an object with `decision` and `reason`"]
    decision = activation.get("decision")
    if decision not in DECISIONS:
        return [f"activation.decision must be one of {', '.join(DECISIONS)}, got {decision!r}"]
    defects: list[str] = []
    if not _text(activation.get("reason")):
        defects.append("activation.reason must be a non-empty string")
    claims = ledger["claims"]
    if decision == "skip" and claims:
        defects.append("activation.decision `skip` must carry no claims")
    if decision == "activate" and not claims:
        defects.append("activation.decision `activate` needs one or more claims")
    return defects


def _field_defects(where: str, claim: dict[str, Any]) -> list[str]:
    """Check presence and allowed values of the claim's own fields."""
    defects = [
        f"{where}: `{key}` must be a non-empty string"
        for key in CLAIM_TEXT_KEYS
        if not _text(claim.get(key))
    ]
    for key, allowed in CLAIM_ENUMS.items():
        if claim.get(key) not in allowed:
            defects.append(f"{where}: `{key}` must be one of {', '.join(allowed)}")
    if not isinstance(claim.get("time_sensitive"), bool):
        defects.append(f"{where}: `time_sensitive` must be true or false")
    if not isinstance(claim.get("final_wording"), str):
        defects.append(f"{where}: `final_wording` must be a string")
    if not isinstance(claim.get("gap"), str):
        defects.append(f"{where}: `gap` must be a string")
    return defects


def _source_defects(where: str, source: object) -> list[str]:
    """Check the source block: kind, url, dates, and the secondary reason."""
    if not isinstance(source, dict):
        return [f"{where}: `source` must be an object"]
    kind = source.get("kind")
    if kind not in SOURCE_KINDS:
        return [f"{where}: source.kind must be one of {', '.join(SOURCE_KINDS)}"]
    defects = _date_defect(where, "accessed", source.get("accessed"))
    defects += _date_defect(where, "published", source.get("published"))
    if kind == "none":
        return defects
    for key in ("url", "accessed"):
        if not _text(source.get(key)):
            defects.append(f"{where}: a {kind} source needs source.{key}")
    if kind == "secondary" and not _text(source.get("secondary_reason")):
        defects.append(f"{where}: a secondary source needs source.secondary_reason")
    return defects


def _evidence_defects(where: str, claim: dict[str, Any], kind: str) -> list[str]:
    """Check that disposition and confidence do not exceed the source kind."""
    disposition = claim["disposition"]
    confidence = claim["confidence"]
    defects: list[str] = []
    if disposition == "verified" and kind != "primary":
        defects.append(f"{where}: `verified` needs a primary source, not {kind}")
    if disposition == "verified" and confidence not in ("high", "medium"):
        defects.append(f"{where}: `verified` needs high or medium confidence")
    if kind == "secondary" and confidence == "high":
        defects.append(f"{where}: a secondary source caps confidence at medium")
    if kind == "none" and disposition not in ("qualified", "removed"):
        defects.append(f"{where}: source kind `none` allows only qualified or removed")
    if kind == "none" and confidence not in ("low", "none"):
        defects.append(f"{where}: source kind `none` allows only low or none confidence")
    if disposition != "verified" and not claim["gap"].strip():
        defects.append(f"{where}: a {disposition} claim needs a non-empty `gap`")
    return defects


def _wording_defects(where: str, claim: dict[str, Any], source: dict[str, Any]) -> list[str]:
    """Check the final wording against the disposition and time sensitivity."""
    wording = claim["final_wording"]
    if claim["disposition"] == "removed":
        if wording.strip():
            return [f"{where}: a removed claim needs an empty `final_wording`"]
        return []
    if not wording.strip():
        return [f"{where}: a kept claim needs a non-empty `final_wording`"]
    if not claim["time_sensitive"]:
        return []
    defects: list[str] = []
    if not _AS_OF.search(wording):
        defects.append(f"{where}: a time-sensitive claim needs `as of` in `final_wording`")
    if source["kind"] != "none" and not _text(source.get("published")):
        defects.append(f"{where}: a time-sensitive claim needs source.published")
    return defects


def _claim_defects(index: int, claim: object) -> list[str]:
    """Return every defect for one claim entry."""
    where = f"claims[{index}]"
    if not isinstance(claim, dict):
        return [f"{where}: each claim must be an object"]
    missing = [key for key in ("source", *CLAIM_ENUMS) if key not in claim]
    if missing:
        return [f"{where}: missing `{key}`" for key in missing]
    defects = _field_defects(where, claim) + _source_defects(where, claim["source"])
    if defects:
        return defects
    kind = claim["source"]["kind"]
    return _evidence_defects(where, claim, kind) + _wording_defects(where, claim, claim["source"])


def _spans(text: str, phrase: str) -> list[tuple[int, int]]:
    """Return the spans where phrase occurs in text on word boundaries."""
    pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)")
    return [match.span() for match in pattern.finditer(text)]


def _stray_draft(text: str, draft: str, kept: list[str]) -> bool:
    """Return True when the draft occurs outside every kept wording that contains it.

    A kept wording may legitimately repeat a shorter draft sentence. The reverse
    case, a narrowed wording cut from a longer draft, never forgives the draft.
    """
    covers = [span for wording in kept if draft in wording for span in _spans(text, wording)]
    return any(
        not any(start <= s and e <= end for start, end in covers) for s, e in _spans(text, draft)
    )


def _artifact_defects(claims: list[dict[str, Any]], artifact: str) -> list[str]:
    """Check that the artifact carries the checked wording, not the draft."""
    text = _normalize(artifact)
    kept = [_normalize(c["final_wording"]) for c in claims if c["disposition"] != "removed"]
    defects: list[str] = []
    for claim in claims:
        where = f"claim {claim['id']}"
        draft = _normalize(claim["claim"])
        if claim["disposition"] == "removed":
            if _stray_draft(text, draft, kept):
                defects.append(f"{where}: the artifact still carries the removed claim")
            continue
        if not _spans(text, _normalize(claim["final_wording"])):
            defects.append(f"{where}: final_wording is absent from the artifact")
        elif _stray_draft(text, draft, kept):
            defects.append(f"{where}: the artifact still carries the unreviewed draft wording")
    return defects


def _skip_defects(ledger: dict[str, Any], artifact: str) -> list[str]:
    """Refuse an internal-only skip over an artifact that cites an outside URL."""
    activation = ledger["activation"]
    if activation.get("decision") != "skip":
        return []
    urls = sorted(set(_URL.findall(artifact)))
    if not urls:
        return []
    return [
        "activation.decision `skip` but the artifact cites an outside URL "
        f"({urls[0]}); record its claims or cite repository files by path"
    ]


def validate(ledger: dict[str, Any], artifact: str | None = None) -> list[str]:
    """Return every ledger defect. An empty list means the ledger passed."""
    if not isinstance(ledger, dict):
        return ["ledger must be a JSON object"]
    missing = [key for key in TOP_LEVEL_KEYS if key not in ledger]
    if missing:
        return [f"ledger is missing `{key}`" for key in missing]
    claims = ledger["claims"]
    if not isinstance(claims, list):
        return ["`claims` must be a list"]
    defects = [] if _text(ledger["artifact"]) else ["`artifact` must be a non-empty string"]
    defects += _activation_defects(ledger)
    for index, claim in enumerate(claims):
        defects += _claim_defects(index, claim)
    ids = [c.get("id") for c in claims if isinstance(c, dict) and isinstance(c.get("id"), str)]
    defects += [f"duplicate claim id `{i}`" for i, n in Counter(ids).items() if n > 1]
    if artifact is not None and not defects:
        defects += _skip_defects(ledger, artifact) + _artifact_defects(claims, artifact)
    return defects


def _summary(
    ledger: object, defects: list[str], ledger_path: Path, artifact_path: Path | None
) -> dict[str, Any]:
    """Build the stdout summary for a validated ledger."""
    data = ledger if isinstance(ledger, dict) else {}
    activation = data.get("activation")
    claims = data.get("claims")
    claims = claims if isinstance(claims, list) else []
    dispositions = Counter(
        c.get("disposition")
        for c in claims
        if isinstance(c, dict) and isinstance(c.get("disposition"), str)
    )
    return {
        "ok": not defects,
        "ledger": str(ledger_path),
        "artifact": str(artifact_path) if artifact_path else None,
        "decision": activation.get("decision") if isinstance(activation, dict) else None,
        "claims": len(claims),
        "dispositions": dict(sorted(dispositions.items())),
        "defects": defects,
    }


def _read(path: Path) -> str:
    """Read a UTF-8 file, raising OSError with the path on failure."""
    return path.read_text(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the ledger named on the command line and print a summary."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, required=True, help="claim ledger JSON")
    parser.add_argument("--artifact", type=Path, help="artifact text to check")
    args = parser.parse_args(argv)
    try:
        raw = _read(args.ledger)
        artifact = _read(args.artifact) if args.artifact else None
    except OSError as exc:
        print(f"cannot read input: {exc}", file=sys.stderr)
        return 2
    try:
        ledger = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"{args.ledger}: not valid JSON: {exc}", file=sys.stderr)
        return 2
    defects = validate(ledger, artifact)
    print(json.dumps(_summary(ledger, defects, args.ledger, args.artifact), sort_keys=True))
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(main())
