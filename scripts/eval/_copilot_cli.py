"""GitHub Copilot CLI transport for the eval harness.

Split out of `_providers.py` because that module crossed the 500-line taste
ceiling once this provider landed. The provider shares no helpers with the
HTTP-based providers, so the seam is clean: nothing here imports `_providers`,
which keeps the dependency one-directional and rules out an import cycle.

`_providers.resolve_provider("copilot-cli")` remains the only supported entry
point. Import the class directly only from tests.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

__all__ = ["_CopilotCLIProvider"]


class _CopilotCLIProvider:
    """GitHub Copilot CLI transport, driven as a subprocess.

    Distinct from every other provider here in one way that matters: it needs
    no API key. It reuses the operator's existing Copilot authentication, so an
    eval can run against the models the owner actually works in
    (`claude-opus-5`, `gpt-5.6-sol`) without separate Anthropic or OpenAI
    billing. That is why it is the preferred transport for this repository.

    Two isolation decisions, both load-bearing:

    1. `cwd` is a caller-supplied empty directory, not the repository. The CLI
       loads `AGENTS.md`, `CLAUDE.md`, and `.github/instructions/**` from its
       working directory. In this repo those files are frequently the variable
       under test, so running from the repo root would put the treatment into
       the control cell and silently destroy the comparison.
    2. Built-in MCP servers are disabled. Their tool definitions occupy the
       same context the eval is measuring, and they add latency for no signal
       on a text-completion eval.

    Ambient user-level configuration (`~/.copilot/`) is NOT isolated, because
    the auth token lives there. It is therefore a constant across every cell of
    a single run, which is the same control argument ADR-058 makes for not
    comparing scores across providers. Do not compare a copilot-cli score to an
    HTTP-provider score.
    """

    # The CLI prints a stats block after the answer, formatted as a fixed-width
    # label column. Matching on "2+ spaces" is wrong: the widest label
    # ("AI Credits") fills the column and leaves a single space before its
    # value. Match the label, then require the padded prefix to reach the
    # column width, which is what separates a stats line from prose that
    # happens to open with the same word ("Tokens are the unit of billing").
    _FOOTER_LABEL_RE = re.compile(
        r"^(?:Changes|AI Credits|Tokens|Resume|Total duration|Wall time)( +)",
    )
    _FOOTER_COLUMN = 11

    #: Where the CLI records structured per-session events. Overridable so the
    #: tests can point at a fixture tree instead of the operator's real one.
    _SESSION_STATE_ENV = "COPILOT_SESSION_STATE_DIR"

    def __init__(self, *, executable: str = "copilot", timeout: float = 900.0) -> None:
        self.name = "copilot-cli"
        self._provider_label = "Copilot CLI"
        self._executable = executable
        self._timeout = timeout
        self.system_fingerprint: str | None = None

    @classmethod
    def _session_state_root(cls) -> Path:
        override = os.environ.get(cls._SESSION_STATE_ENV)
        if override:
            return Path(override)
        return Path.home() / ".copilot" / "session-state"

    @classmethod
    def _read_session_transcript(
        cls, sandbox: str, *, since: float
    ) -> tuple[str, str | None] | None:
        """Return ``(answer, model_actually_used)`` from the session event log.

        The CLI writes one `events.jsonl` per session under its session-state
        directory, where `assistant.message` carries the reply text and tool
        calls sit in a sibling `toolRequests` field. Reading that is strictly
        better than scraping stdout, where tool-call traces and the stats
        footer are interleaved with the answer and have to be guessed apart.

        Sessions are matched on `session.start.data.context.cwd`, which is the
        unique temp directory this call created. That is race-free when several
        models run at once, unlike picking the newest file. ``since`` bounds the
        scan to logs touched by this call, so the cost does not grow with the
        operator's session history.

        Returns ``None`` when no matching session is found, which leaves the
        caller on the stdout path rather than failing the eval.
        """
        root = cls._session_state_root()
        try:
            candidates = sorted(root.glob("*/events.jsonl"))
        except OSError:
            return None
        for path in candidates:
            try:
                if path.stat().st_mtime < since:
                    continue
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            matched = False
            model_used: str | None = None
            chunks: list[str] = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                data = event.get("data")
                if not isinstance(data, dict):
                    continue
                kind = event.get("type")
                if kind == "session.start":
                    context = data.get("context")
                    cwd = context.get("cwd") if isinstance(context, dict) else None
                    if cwd != sandbox:
                        break
                    matched = True
                    selected = data.get("selectedModel")
                    model_used = selected if isinstance(selected, str) else None
                elif kind == "assistant.message" and matched:
                    content = data.get("content")
                    if isinstance(content, str) and content.strip():
                        chunks.append(content.strip())
            if matched:
                return "\n\n".join(chunks), model_used
        return None

    @classmethod
    def _is_footer_line(cls, line: str) -> bool:
        match = cls._FOOTER_LABEL_RE.match(line)
        if match is None:
            return False
        # Either the label is padded out to the value column, or it is followed
        # by a run of spaces no prose would use. Both are stats formatting.
        return len(match.group(0)) >= cls._FOOTER_COLUMN or len(match.group(1)) >= 2

    @classmethod
    def _strip_footer(cls, text: str) -> str:
        """Remove the CLI's trailing stats block.

        Walks backwards from the end, dropping blank lines and footer-shaped
        lines, and stops at the first line that is neither. Anchoring at the
        end (rather than searching forward for the first match) keeps a model
        answer that legitimately contains the word "Tokens" intact.
        """
        lines = text.splitlines()
        end = len(lines)
        while end > 0:
            candidate = lines[end - 1]
            if not candidate.strip() or cls._is_footer_line(candidate):
                end -= 1
                continue
            break
        return "\n".join(lines[:end]).strip()

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> str:
        # Copilot CLI takes a single prompt with no separate system channel and
        # no sampling controls. Fold the system text in as a leading block;
        # ignore max_tokens/temperature/seed rather than failing, so the same
        # fixture runs unchanged across providers. Callers that need sampling
        # determinism must use an HTTP provider.
        del max_tokens, temperature, seed
        parts = [system.strip()] if system.strip() else []
        parts.extend(
            str(m.get("content", "")).strip()
            for m in messages
            if str(m.get("content", "")).strip()
        )
        prompt = "\n\n".join(parts)
        if not prompt:
            raise RuntimeError(
                f"{self._provider_label} requires a non-empty prompt; "
                "system and messages were both blank."
            )

        argv = [
            self._executable,
            "--prompt",
            prompt,
            "--model",
            model,
            "--allow-all-tools",
            "--disable-builtin-mcps",
            "--no-ask-user",
            "--no-color",
            "--log-level",
            "none",
        ]
        with tempfile.TemporaryDirectory(prefix="eval-copilot-") as sandbox:
            started = time.time()
            try:
                # argv is built above from literals and validated fields, and
                # shell=False is the default, so nothing here reaches a shell.
                completed = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=self._timeout,
                    cwd=sandbox,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"{self._provider_label} API request timed out after "
                    f"{self._timeout:.0f}s. The service may be slow or unreachable."
                ) from exc
            except FileNotFoundError as exc:
                raise RuntimeError(
                    f"{self._provider_label} network error: executable "
                    f"{self._executable!r} not found on PATH. Install the "
                    "GitHub Copilot CLI or pass a different executable."
                ) from exc
            except OSError as exc:
                raise RuntimeError(
                    f"{self._provider_label} API network error: {type(exc).__name__}. "
                    "Check that the Copilot CLI is installed and authenticated."
                ) from exc
            transcript = self._read_session_transcript(sandbox, since=started - 5.0)

        if completed.returncode != 0:
            # CWE-200: short ascii excerpt only, never the full stderr body.
            stderr = completed.stderr or completed.stdout or ""
            excerpt = "".join(ch for ch in stderr if 32 <= ord(ch) < 127)[:200]
            raise RuntimeError(
                f"{self._provider_label} API returned HTTP "
                f"{completed.returncode}: {excerpt}"
            )
        answer = ""
        if transcript is not None:
            answer, model_used = transcript
            # The CLI accepts --model without confirming it. Silent substitution
            # would attribute one model's behavior to another, which is worse
            # than a failed run, so treat it as an error rather than a note.
            if model_used is not None and model_used != model:
                raise RuntimeError(
                    f"{self._provider_label} API returned no choices for model "
                    f"{model}: the session ran {model_used} instead."
                )
        if not answer:
            answer = self._strip_footer(completed.stdout or "")
        if not answer:
            raise RuntimeError(
                f"{self._provider_label} API returned no choices for model {model}."
            )
        return answer
