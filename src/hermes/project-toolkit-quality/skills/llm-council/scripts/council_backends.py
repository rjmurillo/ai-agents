"""Model backends for the LLM council script route (the last-resort route).

Each member goes to its own vendor's harness CLI when it is installed, then to
Copilot CLI, then to GitHub Models REST:

- ``claude``: Claude members through ``claude -p --model <id> --tools ""``.
  No tools, prompt on stdin. Copilot-style ids such as ``claude-opus-5.5``
  become ``claude-opus-5-5``.
- ``codex``: GPT members through ``codex exec -m <id> -s read-only -``.
- ``copilot``: any id in the Copilot catalog through ``copilot -p --model <id>``.
  Charges Copilot AI Credits.
- ``github-models``: open-weight models through https://models.github.ai REST.
  Free tier; uses the ``gh auth token``.

Security: model output from earlier stages reaches later prompts, so each CLI
call is restricted as far as its harness allows:

- ``claude``: ``--tools ""`` and ``--strict-mcp-config`` with no MCP config.
- ``codex``: ``-s read-only`` blocks writes but does not block reads outside
  the temp directory, so the call is not tool-free. ``--ignore-user-config``
  (no user MCP servers) and ``--disable apps`` (no account app connectors)
  narrow it further. Nothing here blocks network access.
- ``copilot``: ``--available-tools view`` hides every tool except ``view``,
  which also hides MCP servers that installed Copilot plugins add. The deny
  rules (which win over every allow) remove shell, write, url, and memory, and
  built-in MCP servers plus every server in the user's ``mcp-config.json`` are
  disabled; these stay as a second layer. ``--allow-all-tools`` stays so a
  permission prompt cannot wedge the run. Copilot runs in an empty temp
  directory, never the caller's working directory. Its ``view`` tool can still
  read the system temp directory, which Copilot allows by default, so the empty
  working directory limits the workspace but not temp.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
from pathlib import Path

from council_core import is_copilot_model

API_HOST = "models.github.ai"
API_PATH = "/inference/chat/completions"
API = f"https://{API_HOST}{API_PATH}"

# One line of the metadata block Copilot CLI prints after the answer, matched
# whole (``fullmatch``) in these shapes only: "Changes    +0 -0",
# "AI Credits 21.8 (1m 20s)", "Tokens \u2191 34.8k" (optionally followed by
# " \u2022 \u2193 1.2k" counts), and "Resume     copilot --resume=<id>". Only a trailing run of these
# lines (and blanks) is stripped, never a match inside the answer, and prose
# such as "AI Credits 5 reviews remain." or "Tokens \u2191 grew a lot" is kept.
_COPILOT_FOOTER_LINE = re.compile(
    r"\s*(?:Changes\s+[+-]\d+\s+[+-]\d+"
    r"|AI Credits\s+\d+(?:\.\d+)?\s+\((?:\d+m(?:\s*\d+(?:\.\d+)?s)?|\d+(?:\.\d+)?s)\)"
    r"|Tokens\s+[\u2191\u2193]\s+\d+(?:\.\d+)?[kM]?"
    r"(?:\s+(?:[\u2022\u00b7]\s+)?[\u2191\u2193]\s+\d+(?:\.\d+)?[kM]?)*"
    r"|Resume\s+copilot --resume=\S+)\s*"
)
# The tool list Copilot prints before the answer when --available-tools is set:
# " \u25cf Disabled tools: a, b,\n   c, d\n\n".
_COPILOT_DISABLED_TOOLS = re.compile(r"\A\s*\u25cf\s*Disabled tools:[^\n]*(?:\n {3}[^\n]*)*\n*")
# Strip the "Read foo.txt" tool preamble Copilot prints when the prompt is fed
# through a file (the trampoline below).
_COPILOT_TOOL_PREAMBLE = re.compile(
    r"^\s*\u25cf\s+Read\s+\S+\s*\n(?:\s*[\u2502\u2514\u2500].*\n)*", re.M
)

# Above this size the prompt goes through a temp file instead of the -p
# argument. Windows CreateProcess caps a command line at 32,767 characters,
# and the Stage 3 chairman prompt routinely exceeds 30 KB.
_COPILOT_ARG_LIMIT = 8000

COPILOT_READ_ONLY = (
    "--deny-tool",
    "shell",
    "--deny-tool",
    "write",
    "--deny-tool",
    "url",
    "--deny-tool",
    "memory",
    "--disable-builtin-mcps",
)


def _copilot_user_mcp_servers() -> list[str]:
    """Server names in the user's Copilot MCP config, or [] when it is unreadable."""
    home = Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot")
    try:
        servers = json.loads((home / "mcp-config.json").read_text(encoding="utf-8")).get(
            "mcpServers"
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return []
    return sorted(servers) if isinstance(servers, dict) else []


def copilot_read_only_args() -> list[str]:
    """Deny rules plus one disable and one deny per user MCP server."""
    args = list(COPILOT_READ_ONLY)
    for name in _copilot_user_mcp_servers():
        args += ["--disable-mcp-server", name, "--deny-tool", name]
    return args


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


def _github_models_text(raw: bytes) -> str:
    """The first choice's message text, or RuntimeError when the body has another shape."""
    try:
        content = json.loads(raw)["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        detail = f"{type(exc).__name__}: {str(exc)[:100]}"
        raise RuntimeError(f"GitHub Models returned a malformed reply: {detail}") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("GitHub Models returned a malformed reply: empty or non-string content")
    return content


def call_github_models(
    token: str, model: str, prompt: str, max_tokens: int = 2048, timeout: int = 180
) -> str:
    """POST one chat completion to GitHub Models over HTTPS to a fixed host."""
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
    conn = http.client.HTTPSConnection(
        API_HOST, timeout=timeout, context=ssl.create_default_context()
    )
    try:
        conn.request("POST", API_PATH, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
    finally:
        conn.close()
    if not 200 <= resp.status < 300:
        # Surface the API error body: 401/403 = auth, 429 = rate limit,
        # 404 = unknown model id. Generic codes alone are not actionable.
        detail = raw.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub Models {resp.status} {resp.reason}: {detail}")
    return _github_models_text(raw)


def native_cli(model: str) -> str:
    """Return the member's own vendor CLI when it is installed, else ""."""
    if model.startswith("claude-") and shutil.which("claude"):
        return "claude"
    if model.startswith("gpt-") and shutil.which("codex"):
        return "codex"
    return ""


def claude_cli_model(model: str) -> str:
    """Map a Copilot-style Claude id to the Claude CLI's id (dots become dashes).

    Verified 2026-11-17 with Claude Code 2.1.325: ``claude-opus-5.5`` fails with
    "unknown provider", ``claude-opus-5-5`` and ``claude-sonnet-5`` answer.
    """
    return model.replace(".", "-")


def call_claude(model: str, prompt: str, timeout: int = 300) -> str:
    """One Claude Code turn with no tools; the prompt goes on stdin."""
    with tempfile.TemporaryDirectory(prefix="council-claude-", ignore_cleanup_errors=True) as tmp:
        proc = subprocess.run(
            [
                "claude",
                "-p",
                "--model",
                claude_cli_model(model),
                "--tools",
                "",
                "--strict-mcp-config",
            ],
            input=prompt,
            cwd=tmp,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    if proc.returncode != 0 or not proc.stdout.strip():
        detail = ((proc.stderr or proc.stdout).strip() or "empty reply")[:400]
        raise RuntimeError(f"claude rc={proc.returncode}: {detail}")
    return proc.stdout.strip()


def call_codex(model: str, prompt: str, timeout: int = 300) -> str:
    """One Codex turn with ``-s read-only`` in an empty directory; the prompt goes on stdin.

    ``-s read-only`` blocks writes. It does not block reads outside the temp directory.
    """
    with tempfile.TemporaryDirectory(prefix="council-codex-", ignore_cleanup_errors=True) as tmp:
        out = Path(tmp) / "last.txt"
        proc = subprocess.run(
            [
                "codex",
                "exec",
                "-m",
                model,
                "-s",
                "read-only",
                "--ephemeral",
                "--skip-git-repo-check",
                "--ignore-user-config",
                "--disable",
                "apps",
                "-C",
                tmp,
                "-o",
                str(out),
                "-",
            ],
            input=prompt,
            cwd=tmp,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        text = out.read_text(encoding="utf-8", errors="replace") if out.is_file() else ""
    if proc.returncode != 0 or not text.strip():
        raise RuntimeError(f"codex rc={proc.returncode}: {(proc.stderr or proc.stdout)[-400:]}")
    return text.strip()


def _copilot(args: list[str], timeout: int, cwd: str) -> subprocess.CompletedProcess[str]:
    """One ``copilot -p`` run in ``cwd``; ``args`` start with the prompt text.

    ``--available-tools view`` hides every other tool. ``cwd`` is always an
    empty or private temp directory, because Copilot's default file access
    covers the working directory.
    """
    return subprocess.run(
        [
            "copilot",
            "--allow-all-tools",
            "--no-color",
            "--available-tools",
            "view",
            "-p",
            *args,
        ],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _copilot_via_file(model: str, prompt: str, timeout: int) -> subprocess.CompletedProcess[str]:
    """Write a long prompt to a private temp file and tell Copilot to read it.

    Copilot CLI exposes no stdin or file flag for the prompt itself, so this
    read-this-file trampoline is the only portable path. The file sits in its
    own owner-only directory, and only that directory is granted with
    ``--add-dir``, never the shared temp root.
    """
    with tempfile.TemporaryDirectory(
        prefix="council-prompt-", ignore_cleanup_errors=True
    ) as prompt_dir:
        prompt_path = Path(prompt_dir) / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        cmd_prompt = (
            f"Read the file at {prompt_path} verbatim, then respond to the instructions it contains. "
            "Output ONLY the final response: no preamble, no tool-call narration, no 'Read file' headers."
        )
        return _copilot(
            [cmd_prompt, "--model", model, *copilot_read_only_args(), "--add-dir", prompt_dir],
            timeout,
            prompt_dir,
        )


def _strip_copilot_footer(text: str) -> str:
    """Drop the trailing metadata block: blank lines and footer lines, from the end up."""
    lines = text.split("\n")
    while lines and (not lines[-1].strip() or _COPILOT_FOOTER_LINE.fullmatch(lines[-1])):
        lines.pop()
    return "\n".join(lines)


def call_copilot(model: str, prompt: str, timeout: int = 240) -> str:
    """Drive `copilot -p` as a one-shot read-only subprocess. Returns the text response."""
    if len(prompt) > _COPILOT_ARG_LIMIT:
        proc = _copilot_via_file(model, prompt, timeout)
    else:
        with tempfile.TemporaryDirectory(
            prefix="council-copilot-", ignore_cleanup_errors=True
        ) as empty_dir:
            # A short prompt needs no file at all; a deny rule with no path
            # matches every read, and deny wins over --allow-all-tools.
            args = [prompt, "--model", model, *copilot_read_only_args(), "--deny-tool", "read"]
            proc = _copilot(args, timeout, empty_dir)
    if proc.returncode != 0:
        raise RuntimeError(f"copilot rc={proc.returncode}: {(proc.stderr or proc.stdout)[:400]}")
    out = _COPILOT_DISABLED_TOOLS.sub("", proc.stdout, count=1)
    out = _COPILOT_TOOL_PREAMBLE.sub("", out)
    return _strip_copilot_footer(out).strip()


def backend_for(model: str) -> str:
    """Name the backend a member routes to: claude, codex, copilot, or github-models."""
    return native_cli(model) or ("copilot" if is_copilot_model(model) else "github-models")


def call_model(token: str | None, model: str, prompt: str, **kw) -> str:
    backend = backend_for(model)
    timeout = kw.get("timeout", 300)
    if backend == "claude":
        return call_claude(model, prompt, timeout=timeout)
    if backend == "codex":
        return call_codex(model, prompt, timeout=timeout)
    if backend == "copilot":
        # Copilot CLI controls its own output budget; drop max_tokens.
        return call_copilot(model, prompt, timeout=timeout)
    if token is None:
        raise RuntimeError(
            f"Model '{model}' routes to GitHub Models but no gh token is available. "
            "Run `gh auth login` and retry, or pass only Copilot-backed models."
        )
    return call_github_models(token, model, prompt, **kw)
