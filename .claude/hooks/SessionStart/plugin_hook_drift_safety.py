#!/usr/bin/env python3
# taste-lint: ignore naming -- a library imported by the drift-check hook and
# its model, registered as a hook nowhere. The `invoke_` prefix marks a
# registered entry point; using it here would assert the opposite of what is
# true. Same reasoning as `plugin_hook_drift_model.py`.
"""Everything an untrusted manifest is allowed to contribute to the output.

The drift check reads plugin manifests under `~/.claude/plugins` and Copilot's
installed-plugins tree. A same-named plugin root there is attacker-placeable,
and this hook's stdout becomes session context, so every string that crosses
from a manifest into the message passes through this module first.

Two different reductions, because two different risks:

- `sanitize_label` bounds the character set and the length. Enough for a value
  whose *shape* is known, such as an event name or a script basename.
- `command_unit` and `path_token` bound the MEANING. An allowlisted string is
  still free to read "Ignore all previous instructions", so free-form command
  text and attacker-chosen directory names are reduced to digests that
  identify the thing without repeating any of its words.

Refs: issue #5085, CWE-74.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

# Output caps. Everything below is rendered into session context, and an
# installed manifest is attacker-influenceable, so a label is allowlisted
# characters only and bounded in length. `?` marks each dropped character so a
# reader can see that scrubbing happened rather than reading a clean-looking
# name that is not what the manifest said.
MAX_LABEL_CHARS = 80
MAX_PATH_CHARS = 200

_UNSAFE_LABEL_CHARS = re.compile(r"[^A-Za-z0-9._/@:+= -]")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SCRIPT_IN_COMMAND = re.compile(r"[A-Za-z0-9._/\\-]+\.(?:py|sh|ps1)")

def sanitize_label(text: object, limit: int = MAX_LABEL_CHARS) -> str:
    """Reduce untrusted manifest text to inert, length-capped label characters."""
    collapsed = " ".join(str(text).split())
    scrubbed = _UNSAFE_LABEL_CHARS.sub("?", collapsed)
    if len(scrubbed) <= limit:
        return scrubbed
    return scrubbed[:limit] + "[truncated]"


def command_unit(command: str) -> str:
    """Name what a registration runs without echoing the command itself.

    Prefers the basename of the last script path in the command, which is the
    part a reader needs in order to find the hook. A bare identifier is kept as
    written (it is already within the safe alphabet). Anything else, including
    shell text a hostile manifest could have chosen freely, collapses to a
    digest: still stable enough to diff two manifests, but carrying none of the
    attacker's words into the model's context.
    """
    text = " ".join(command.split())
    scripts = _SCRIPT_IN_COMMAND.findall(text)
    if scripts:
        return sanitize_label(PurePosixPath(scripts[-1].replace("\\", "/")).name)
    if _SAFE_TOKEN.match(text):
        return text
    digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]
    return f"unrecognized command (sha256:{digest})"


def path_token(path: object) -> str:
    """Opaque, stable identifier for an install path.

    A marketplace directory name is attacker-choosable, and `sanitize_label`
    bounds the character set and the length without bounding the *meaning*: an
    allowlisted string is still free to read "Ignore all previous instructions"
    once it lands in session context. Install paths are therefore reduced the
    same way an unrecognized command is, to a digest that identifies the
    install without repeating any of its words.

    The real path is not lost: the hook writes the token-to-path mapping to
    stderr, which a human reads in the hook log and which is not injected as
    model context.
    """
    digest = hashlib.sha256(str(path).encode("utf-8", "replace")).hexdigest()[:12]
    return f"install sha256:{digest}"
