"""Gate-state management for ADR-062 conditional LSP-first enforcement.

Ported from the claude-code-lsp-enforcement-kit (nesaminua, MIT, v2.3.2),
files ``kit/hooks/lsp-usage-tracker.js`` and ``kit/hooks/lsp-session-reset.js``.
This is the ONLY stateful module in the LSP-gate library: the PostToolUse
tracker writes it, the SessionStart reset clears it, and the PreToolUse guards
only read it (ADR-062 Section 4, single system-of-record).

State lives OUTSIDE the git working tree in a user-scoped directory, keyed by
``hashlib.sha256(cwd).hexdigest()[:16]``. A missing or unreadable state file is
treated as "needs warmup" and never raises (fail-open). Gate-state is not a
security boundary (CWE-284, Low): tampering degrades to allowing the raw tool.

Canonical kit state shape (``lsp-usage-tracker.js:87-89``), quoted
character-for-character (canonical-source-mirror.md):

    const existing = readFlag(flagPath) || {
      cwd: process.cwd(), warmup_done: false, nav_count: 0, read_count: 0, read_files: [],
    };

Canonical kit warmup-then-nav increment (``lsp-usage-tracker.js:91-99``):

    if (!existing.warmup_done) {
      existing.warmup_done = true;
      existing.cold_start_retries = 0;
    } else {
      existing.nav_count = (existing.nav_count || 0) + 1;
    }
    existing.timestamp = Date.now();
    existing.last_tool = toolName;

Canonical kit thresholds (``lsp-first-read-guard.js:30-32``):

    const FREE_READS = 2;
    const WARN_AT = 3;
    const REQUIRE_NAV_2_AT = 6;

Canonical kit flag path scheme (``lsp-usage-tracker.js:21-27``):

    const STATE_DIR = path.join(os.homedir(), '.claude', 'state');
    const cwd = process.cwd();
    const hash = crypto.createHash('md5').update(cwd).digest('hex').slice(0, 12);
    return path.join(STATE_DIR, `lsp-ready-${hash}`);

Stricter/looser/different than canonical
----------------------------------------
- DIFFERENT hash: the kit keys the flag with ``md5(cwd).slice(0, 12)``. ADR-062
  Section 4 mandates ``hashlib.sha256(cwd).hexdigest()[:16]`` (md5 is forbidden;
  not a security control but the ADR fixes the scheme). This port uses sha256.
- DIFFERENT state dir: the kit writes ``~/.claude/state``. ADR-062 Section 4
  mandates a user-scoped dir OUTSIDE the git working tree, never committed. This
  port uses ``$XDG_STATE_HOME/ai-agents-lsp-gate`` when set, else
  ``~/.cache/ai-agents-lsp-gate`` (kept off ``~/.claude`` so plugin state and
  gate state do not collide).
- DIFFERENT threshold name: the kit's ``REQUIRE_NAV_2_AT = 6`` gate fires at the
  6th read. ADR-062 Section 3 sets ``nav_required = 2`` for the Surgical
  threshold and ``WARN_AT = 3``; the hard block ramps at read 4+ with
  ``nav_count < nav_required``. This port exposes ``NAV_REQUIRED = 2``,
  ``FREE_READS = 2``, ``WARN_AT = 3`` as the canonical names the guards consume;
  the per-tier decision logic lives in the Read-gate guard, not here.
- DROPPED 24h expiry: the kit expires the flag after 24h (``FLAG_EXPIRY_MS``).
  ADR-062 drives reset solely from the SessionStart lifecycle signal, so this
  port has no time-based expiry; reset is explicit and idempotent.
- DROPPED cclsp cold-start fields: the kit tracks ``cold_start_retries`` for a
  cclsp upstream bug. cclsp is not used here; the field is omitted.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

# Gate thresholds (ADR-062 Section 3; canonical names the guards consume).
NAV_REQUIRED = 2
FREE_READS = 2
WARN_AT = 3

_STATE_SUBDIR = "ai-agents-lsp-gate"


def _state_dir() -> Path:
    """Return the user-scoped state directory, outside the git working tree.

    Honors ``$XDG_STATE_HOME`` when set, else ``~/.cache``. Never the repo tree.
    """
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / _STATE_SUBDIR


def _cwd_key(cwd: str) -> str:
    """Return the per-cwd state key: sha256(normalized cwd) truncated to 16 hex chars.

    The path is resolved before hashing so different spellings of the same
    physical directory (relative segments, symlinks, trailing slashes) map to
    one key, keeping the session-reset hook and the guards in agreement.
    """
    try:
        normalized = str(Path(cwd).resolve())
    except (OSError, ValueError):
        normalized = cwd
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest[:16]


def state_path(cwd: str) -> Path:
    """Return the absolute state-file path for ``cwd``.

    Scheme: ``<state_dir>/lsp-gate-<sha256(cwd)[:16]>.json`` where ``state_dir``
    is ``$XDG_STATE_HOME/ai-agents-lsp-gate`` or ``~/.cache/ai-agents-lsp-gate``.
    """
    return _state_dir() / f"lsp-gate-{_cwd_key(cwd)}.json"


def _default_state(cwd: str) -> dict:
    """Return the needs-warmup default state for ``cwd`` (kit default shape)."""
    return {
        "cwd": cwd,
        "warmup_done": False,
        "nav_count": 0,
        "read_count": 0,
        "read_files": [],
        "last_tool": "",
    }


def read_state(cwd: str) -> dict:
    """Read gate state for ``cwd``. Never raises.

    A missing or unreadable or malformed state file returns the needs-warmup
    default (fail-open). The returned dict always has every state key, with
    types normalized so guards never need to defend against a tampered shape.
    """
    default = _default_state(cwd)
    path = state_path(cwd)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return default
    if not isinstance(data, dict):
        return default
    return _normalize_state(data, cwd)


def _normalize_state(data: dict, cwd: str) -> dict:
    """Coerce a loaded state dict to the canonical shape and types."""
    read_files = data.get("read_files")
    if not isinstance(read_files, list):
        read_files = []
    else:
        read_files = [str(f) for f in read_files]
    return {
        "cwd": str(data.get("cwd", cwd)),
        "warmup_done": bool(data.get("warmup_done", False)),
        "nav_count": _coerce_int(data.get("nav_count")),
        "read_count": _coerce_int(data.get("read_count")),
        "read_files": read_files,
        "last_tool": str(data.get("last_tool", "")),
    }


def _coerce_int(value: object) -> int:
    """Coerce a value to a non-negative int, defaulting to 0."""
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        result = int(value)
    except (TypeError, ValueError):
        return 0
    return result if result >= 0 else 0


def write_state(cwd: str, state: dict) -> bool:
    """Persist ``state`` for ``cwd``. Never raises. Returns success.

    Creates the state directory if needed. On any filesystem error returns
    False (fail-open: the tracker degrades to not recording, which the guards
    treat as needs-warmup).
    """
    path = state_path(cwd)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_normalize_state(state, cwd)), encoding="utf-8")
    except OSError:
        return False
    return True


def reset_state(cwd: str) -> bool:
    """Clear gate state for ``cwd`` (SessionStart reset). Idempotent, never raises.

    Returns True whether or not a file existed (idempotent success). Returns
    False only on a filesystem error other than "missing file".
    """
    path = state_path(cwd)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def record_warmup(cwd: str) -> dict:
    """Record that the first warmup LSP call happened. Returns the new state.

    Mirrors the kit's ``if (!existing.warmup_done)`` branch: sets the flag and
    leaves ``nav_count`` at 0. Idempotent: calling again after warmup is a no-op
    on the flag and does not increment nav (use ``record_nav`` for that).
    """
    state = read_state(cwd)
    state["warmup_done"] = True
    write_state(cwd, state)
    return state


def record_nav(cwd: str) -> dict:
    """Record one LSP navigation call. Returns the new state.

    Mirrors the kit's tracker: the first qualifying LSP call performs warmup
    (sets ``warmup_done``); every subsequent call increments ``nav_count``.
    """
    state = read_state(cwd)
    if not state["warmup_done"]:
        state["warmup_done"] = True
    else:
        state["nav_count"] += 1
    write_state(cwd, state)
    return state


# Bounded read budget for conflict-marker scanning. Conflict markers, when
# present, appear at column 0 of their own lines, so scanning a leading window
# of the file is sufficient and bounds worst-case I/O on huge files.
_CONFLICT_MARKER_SCAN_BYTES = 256 * 1024


def _merge_in_progress(project_dir: str) -> bool:
    """True if a merge, rebase, or cherry-pick/revert is in progress.

    Detected via the sentinel paths git itself creates under ``.git``:
    ``MERGE_HEAD`` (``git merge``, ``git cherry-pick``, ``git revert``),
    ``rebase-merge`` (interactive rebase / ``git rebase -i``), and
    ``rebase-apply`` (plain ``git rebase``). ADR-062 Section 7 extends the
    always-bypass set with this signal: while one of these markers exists, files
    on disk may legitimately contain ``<<<<<<<``/``=======``/``>>>>>>>`` and no
    LSP can parse them, so the gate's warmup precondition is unsatisfiable for
    the window (issue #2454).

    Pure stat-only check; no shell-out to ``git`` (CWE-78 safe). Any filesystem
    error degrades to ``False`` (fail-open: do not synthesize a bypass when the
    state cannot be observed).
    """
    if not project_dir:
        return False
    try:
        git_dir = Path(project_dir) / ".git"
        for marker in ("MERGE_HEAD", "rebase-merge", "rebase-apply"):
            if (git_dir / marker).exists():
                return True
    except (OSError, ValueError):
        return False
    return False


def _has_conflict_markers(file_path: str) -> bool:
    """True if the file's leading window starts a line with a conflict marker.

    Reads up to ``_CONFLICT_MARKER_SCAN_BYTES`` (bounded I/O, never the whole
    file) and looks for any line that begins with ``<<<<<<<``, ``=======``, or
    ``>>>>>>>``. These line-start anchors are what ``git merge`` writes; checks
    that match them mid-line would false-positive on prose and on this codebase's
    own merge-resolver tooling, so only ``re.MULTILINE`` ``^`` anchors are used
    (issue #2454).

    Binary files (``UnicodeDecodeError``) and any filesystem error degrade to
    ``False`` (fail-open: do not synthesize a bypass when the file cannot be
    read).
    """
    if not file_path:
        return False
    try:
        with open(file_path, "rb") as fh:
            raw = fh.read(_CONFLICT_MARKER_SCAN_BYTES)
    except (OSError, ValueError):
        return False
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    for line in text.splitlines():
        if line.startswith("<<<<<<<") or line.startswith("=======") or line.startswith(">>>>>>>"):
            return True
    return False


def is_gated_target(file_path: str, project_dir: str) -> bool:
    """True if ``file_path`` is an in-repo, non-dotfile, non-scratch target.

    ADR-062 Section 7 always-bypass set: out-of-repo paths, dotfiles, and
    TMPDIR/scratch are never gated. Paths are resolved before comparison so
    ``..`` traversal cannot escape the bypass (CWE-22 safe). A path that cannot
    be resolved or compared degrades to NOT gated (fail-open: allow).

    The bypass set also covers files that LSP cannot meaningfully parse: any
    file during a merge/rebase/cherry-pick (``.git/MERGE_HEAD``,
    ``.git/rebase-merge``, ``.git/rebase-apply``), and any file whose leading
    window contains a line starting with a conflict marker. During conflict
    resolution the gate's warmup precondition is unsatisfiable, so blocking the
    Read would only force a sed/grep workaround (issue #2454).
    """
    if not file_path:
        return False
    try:
        root = Path(project_dir).resolve()
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
    except (OSError, ValueError):
        return False

    # Out-of-repo targets are never gated.
    if root not in resolved.parents and resolved != root:
        return False

    # Scratch under TMPDIR is never gated (mktemp staging).
    tmpdir = os.environ.get("TMPDIR", "").strip()
    if tmpdir:
        try:
            tmp_root = Path(tmpdir).resolve()
            if tmp_root == resolved or tmp_root in resolved.parents:
                return False
        except (OSError, ValueError):
            return False

    # Dotfiles and dot-directory members (.serena/, .git/, .agents/, ...) are
    # not gated: they are config/state, not navigable source under this gate's
    # intent, and the kit's path-bypass list covered the same shape.
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return False
    if any(part.startswith(".") for part in relative.parts):
        return False

    # Merge/rebase/cherry-pick in progress: files on disk may contain conflict
    # markers and no LSP can parse them. The dotfile bypass above already
    # excluded the merge-resolver skill's intentional fenced examples in
    # ``.claude/`` and ``.serena/``, so this content scan only ever runs on
    # plain in-repo source. (issue #2454, ADR-062 Section 7.)
    if _merge_in_progress(str(root)):
        return False
    if _has_conflict_markers(str(resolved)):
        return False
    return True


def normalize_path(file_path: str, cwd: str) -> str:
    """Normalize a file path to a stable resolved form for deduplication.

    Relative paths are anchored to ``cwd`` (not the process working directory)
    before resolving, so the same tool-supplied path always maps to one key.
    Returns the original path on resolution failure (fail-open).
    """
    if not file_path:
        return file_path
    try:
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = Path(cwd) / candidate
        return str(candidate.resolve())
    except (OSError, ValueError):
        return file_path


def record_read(cwd: str, file_path: str) -> dict:
    """Record a gated Read of ``file_path``. Returns the new state.

    Appends the file to ``read_files`` (deduplicated by normalized path) and
    keeps ``read_count`` in sync with the unique set, matching the kit's read
    tracking. Paths are normalized to resolved absolute form so the same file
    read via different path representations counts once.
    """
    state = read_state(cwd)
    normalized = normalize_path(file_path, cwd)
    if normalized and normalized not in state["read_files"]:
        state["read_files"].append(normalized)
    state["read_count"] = len(state["read_files"])
    write_state(cwd, state)
    return state
