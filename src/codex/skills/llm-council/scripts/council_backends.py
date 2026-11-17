"""Model backends for the LLM council script route.

- ``copilot``: frontier models through ``copilot -p --model <id>``. Charges
  Copilot AI Credits.
- ``github-models``: open-weight models through https://models.github.ai REST.
  Free tier; uses the ``gh auth token``.

Security: ``call_copilot`` runs ``copilot -p`` with ``--allow-all-tools`` so a
permission prompt cannot wedge the subprocess. The councillor prompt tells the
model not to use tools, but the CLI does not enforce it. Only send questions
you would run in an unattended Copilot session.
"""

from __future__ import annotations

import http.client
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from council_core import is_copilot_model

API = "https://models.github.ai/inference/chat/completions"

# Strip the "AI Credits / Tokens / Changes" footer Copilot CLI emits.
_COPILOT_FOOTER = re.compile(r"\n*(Changes\s+[+-]?\d|AI Credits\s+\d|Tokens\s+[↑↓])", re.M)
# Strip the "Read foo.txt" tool preamble Copilot prints when the prompt is fed
# through a file (the trampoline below).
_COPILOT_TOOL_PREAMBLE = re.compile(r"^\s*●\s+Read\s+\S+\s*\n(?:\s*[│└─].*\n)*", re.M)

# Above this size the prompt goes through a temp file instead of the -p
# argument. Windows CreateProcess caps a command line at 32,767 characters,
# and the Stage 3 chairman prompt routinely exceeds 30 KB.
_COPILOT_ARG_LIMIT = 8000


def gh_token() -> str:
    r = subprocess.run(
        ["gh", "auth", "token"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return r.stdout.strip()


def call_github_models(
    token: str, model: str, prompt: str, max_tokens: int = 2048, timeout: int = 180
) -> str:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
    ).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = urllib.request.Request(API, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        # Surface the API error body: 401/403 = auth, 429 = rate limit,
        # 404 = unknown model id. Generic codes alone are not actionable.
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except (OSError, http.client.HTTPException):
            detail = ""
        raise RuntimeError(f"GitHub Models {e.code} {e.reason}: {detail}") from e


def _run_copilot(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["copilot", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _copilot_via_file(model: str, prompt: str, timeout: int) -> subprocess.CompletedProcess:
    """Write a long prompt to a private temp file and tell Copilot to read it.

    Copilot CLI exposes no stdin or file flag for the prompt itself, so this
    read-this-file trampoline is the only portable path. The file sits in its
    own owner-only directory, and only that directory is granted with
    ``--add-dir``, never the shared temp root.
    """
    prompt_dir = Path(tempfile.mkdtemp(prefix="council-prompt-"))
    try:
        prompt_path = prompt_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        cmd_prompt = (
            f"Read the file at {prompt_path} verbatim, then respond to the instructions it contains. "
            "Output ONLY the final response: no preamble, no tool-call narration, no 'Read file' headers."
        )
        args = ["-p", cmd_prompt, "--model", model, "--allow-all-tools", "--no-color", "--add-dir"]
        return _run_copilot([*args, str(prompt_dir)], timeout)
    finally:
        shutil.rmtree(prompt_dir, ignore_errors=True)


def call_copilot(model: str, prompt: str, timeout: int = 240) -> str:
    """Drive `copilot -p` as a one-shot subprocess. Returns the model's text response."""
    if len(prompt) > _COPILOT_ARG_LIMIT:
        proc = _copilot_via_file(model, prompt, timeout)
    else:
        proc = _run_copilot(
            ["-p", prompt, "--model", model, "--allow-all-tools", "--no-color"], timeout
        )
    if proc.returncode != 0:
        raise RuntimeError(f"copilot rc={proc.returncode}: {(proc.stderr or proc.stdout)[:400]}")
    out = _COPILOT_TOOL_PREAMBLE.sub("", proc.stdout)
    # Cut at the FIRST footer match so a multi-line footer block goes whole.
    footer = _COPILOT_FOOTER.search(out)
    if footer:
        out = out[: footer.start()]
    return out.strip()


def call_model(token: str | None, model: str, prompt: str, **kw) -> str:
    if is_copilot_model(model):
        # Copilot CLI controls its own output budget; drop max_tokens.
        return call_copilot(model, prompt, timeout=kw.get("timeout", 300))
    if token is None:
        raise RuntimeError(
            f"Model '{model}' routes to GitHub Models but no gh token is available. "
            "Run `gh auth login` and retry, or pass only Copilot-backed models."
        )
    return call_github_models(token, model, prompt, **kw)
