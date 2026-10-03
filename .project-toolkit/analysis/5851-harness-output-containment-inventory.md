# Analysis: Which hook seams can bound command output, per harness

Refs #5851. Phase one of option C: inventory before build.

## Question

Issue #5851 wants large command output kept out of model context. Full output stays recoverable outside it, and the model sees a bounded receipt. Which hook seam can do that in Claude Code, Copilot CLI, and Codex?

## Method and evidence labels

- PROBED: run on 2026-09-30 against the real binary with a throwaway hook. The result is the tool_result content the host sent toward the model, read from the host's stream-json event log, with a negative control. A model's own report does not qualify; see the next label.
- PROBED, model report only: run the same way, but the result is what the model said it saw. No event-log check. Weaker than PROBED; read it as a lead, not a confirmed result.
- DOCUMENTED: stated in the vendor hook reference, fetched the same day. Not run here.
- BINARY: string present in the installed binary. Effect not run.
- NOT RUN: attempted and blocked, reason named.

Versions: Claude Code 2.1.285, Copilot CLI 1.0.90, Codex CLI 0.157.1.

## Sources

Every DOCUMENTED row below comes from one of these pages. The vendor pages are unversioned, so each fetch date is the pin. A page listed with two dates was fetched on the first and rechecked on the second; the second date is the snapshot behind the claims noted in the last column.

| Harness | Page | Fetched | Sections used |
|---|---|---|---|
| Claude Code | https://code.claude.com/docs/en/hooks | 2026-09-30 | "Decision control" table (PreToolUse `updatedInput`, PostToolUse `updatedToolOutput`), "JSON output" (10,000 character cap) |
| Claude Code | https://code.claude.com/docs/en/tools-reference | 2026-10-02 | "Output limits" (valid and failure inline ceilings, 2,000 character preview, `bashOutputMaxChars`) |
| Claude Code | https://code.claude.com/docs/en/env-vars | 2026-10-02 | `BASH_MAX_OUTPUT_LENGTH` default, maximum, and precedence |
| Copilot CLI | https://docs.github.com/en/copilot/reference/hooks-configuration | 2026-09-30, rechecked 2026-10-02 | "`preToolUse` decision control" (`modifiedArgs`), "`postToolUse` output" (`modifiedResult`), hook output bound (10 MiB) |
| Codex | https://learn.chatgpt.com/docs/hooks (redirect from https://developers.openai.com/codex/hooks) | 2026-09-30, rechecked 2026-10-02 | "PreToolUse" rewriting, "PostToolUse" output handling, "Large hook output" spill (about 2,500 tokens), `additionalContextLimit` |
| Codex | https://developers.openai.com/codex/config-reference | 2026-10-02 | `tool_output_token_limit` |

The Copilot rows also match the repo's own record in `.claude/skills/agent-harness-reference/references/official-hook-contracts.md`.

BINARY rows come from `strings` on the Codex 0.157.1 binary shipped in the `@openai/codex-linux-x64` package.

## Findings

### Claude Code

| Seam | Can replace or bound output? | Evidence |
|---|---|---|
| PreToolUse `hookSpecificOutput.updatedInput.command` | Yes. Rewrites the command before it runs, so a wrapper can spill and bound output. | PROBED, model report only. Command `echo REALOUTPUT-12345` was rewritten to `echo REWRITTEN-BY-PRE-HOOK`. The model reported the rewritten output (model report only, no event-log check). |
| PostToolUse `hookSpecificOutput.updatedToolOutput`, object form | Yes, for a successful Bash call. The object must match `tool_response`: `stdout`, `stderr`, `interrupted`, `isImage`, `noOutputExpected`. | PROBED. The host's tool_result held only `CONTAINED-BY-HOOK-PROBE`. The original marker was absent. |
| PostToolUse `updatedToolOutput`, bare string | No. Ignored with no error. | PROBED. Negative control: the host's tool_result still held `REALOUTPUT-12345`. |
| PostToolUseFailure (nonzero exit) | No. The hook fires with `error` set to `Exit code 3\n<stderr>\n<stdout>` and no `tool_response`. Returning `updatedToolOutput` or `additionalContext` changed nothing the model reported. | PROBED, model report only. Exit 3 command; the model quoted the original text. |
| `additionalContext` | Adds context. Capped at 10,000 characters; larger text spills to a file with a 2,000 character preview. | DOCUMENTED. |
| `bashOutputMaxChars` setting (characters) | Native inline ceiling on a valid Bash result. Default about 30,000 characters, up to 128,000. Past the ceiling the result becomes a saved file path plus a 2,000 character preview. Failures get about 10,000 characters inline. `BASH_MAX_OUTPUT_LENGTH` (default 30,000, maximum 150,000) is ignored once the setting is set. | DOCUMENTED. tools-reference ("Output limits") and env-vars, both fetched 2026-10-02. |

Gap: a failing command's output cannot be replaced after the fact. Only the PreToolUse wrapper covers it.

### Copilot CLI

| Seam | Can replace or bound output? | Evidence |
|---|---|---|
| preToolUse `modifiedArgs` | Yes. Replaces tool arguments. | DOCUMENTED. Also recorded in `.claude/skills/agent-harness-reference/references/official-hook-contracts.md`. |
| postToolUse `modifiedResult` | Yes, for any tool that completes successfully; omit the matcher to receive every tool. Replacement needs `resultType: "success"`. Honored for command and HTTP config-file hooks. | DOCUMENTED. NOT RUN: a throwaway repo with `.github/hooks/probe.json` never fired the hook in two tries, cause unknown. The model saw the real output. |
| Hook output size | Bounded at 10 MiB per invocation, then truncated. | DOCUMENTED. |

The repo adapter emits only `additionalContext` for successful PostToolUse observers (same contract file, "Repository consequence"). Using `modifiedResult` needs a change there.

### Codex

| Seam | Can replace or bound output? | Evidence |
|---|---|---|
| PreToolUse `updatedInput.command` | Yes for Bash and `apply_patch`. Needs a string `command`. | DOCUMENTED. |
| PostToolUse | No replacement of tool output. `decision: "block"` replaces the result with the hook's feedback text. | DOCUMENTED. |
| Hook output spill | Hook `additionalContext` above about 2,500 tokens spills to disk with a head and tail preview. The limit is `additionalContextLimit`. | DOCUMENTED. `additionalContextLimit` is in the binary. BINARY. |
| `tool_output_token_limit` in `config.toml` | Documented as a token budget for storing individual tool outputs in history. It is not documented as a cap on what the model sees this turn. The binary also contains the key. | DOCUMENTED (config-reference, fetched 2026-10-02). BINARY. NOT RUN: `codex exec` returned "Your workspace is out of credits". |

Hooks do load in this install: SessionStart and UserPromptSubmit hooks ran during the attempted probe.

## Recommended seam for the build phase

| Harness | Seam | Why | First build step |
|---|---|---|---|
| Claude Code | PostToolUse `updatedToolOutput` (object form) for success. PreToolUse wrapper only if failing-command output proves too large. | Replaces output with no command rewrite, and the command identity stays intact. PROBED. | Write the receipt object with `stdout` set to the bounded text and the full output in an artifact file. Rely on the native inline ceiling (`bashOutputMaxChars`, about 30,000 characters by default) as the backstop. |
| Copilot CLI | postToolUse `modifiedResult` through the generated adapter. | Documented for shell. No command rewrite. | Probe it inside this repo's own `.github/hooks` first, since the temp-repo probe never fired. If it does not fire, fall back to a preToolUse `modifiedArgs` wrapper. |
| Codex | Native `tool_output_token_limit` if the probe shows it bounds model-visible output. Otherwise a PreToolUse `updatedInput` wrapper script. | PostToolUse cannot replace output, so a wrapper is the only hook seam. | Re-run the config probe with credits. Unsupported: PostToolUse replacement. |

## What this does not settle

- Whether the Copilot `modifiedResult` and Codex `tool_output_token_limit` work. Both are NOT RUN.
- The wrapper's effect on command identity in receipts and on approval prompts.
- Secret redaction before the artifact is written. That is build-phase work from the issue.
- Measurement through #5400. No before and after numbers exist yet.

## Probe artifacts

Each PROBED row used one throwaway hook, inlined here so the result can be rechecked.

Probe A, PostToolUse replacement (settings file registers the hook for matcher `Bash`):

```python
import json, sys
d = json.load(sys.stdin)
tr = d.get("tool_response")
new = dict(tr, stdout="CONTAINED-BY-HOOK-PROBE") if isinstance(tr, dict) else "CONTAINED-BY-HOOK-PROBE"
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": new}}))
```

Negative control: replace the `new = ...` line with the bare string and keep the rest unchanged.

```python
new = "CONTAINED-BY-HOOK-PROBE"
```

Run with `--output-format stream-json --verbose` and read the `tool_result` block of each `user` event. With `new` as the bare string the tool_result was `REALOUTPUT-12345` (negative control). With the object form it was `CONTAINED-BY-HOOK-PROBE` and the original marker did not appear. The logged `tool_response` was `{"stdout": "REALOUTPUT-12345", "stderr": "", "interrupted": false, "isImage": false, "noOutputExpected": false}`.

Probe B, PreToolUse rewrite: the hook printed `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow", "updatedInput": {"command": "echo REWRITTEN-BY-PRE-HOOK"}}}`. The model-bound output was `REWRITTEN-BY-PRE-HOOK`, read from the model's reply in that run; the stream-json check was repeated only for Probe A.

Probe C, PostToolUseFailure: the same hook registered for both events, on `bash -c 'echo FAILOUT-777 >&2; echo STDOUT-888; exit 3'`. The failure event carried `error` = `Exit code 3\nFAILOUT-777\nSTDOUT-888` and no `tool_response`. The model's reply quoted the original text, so neither returned field applied. This row rests on the model's report, not the event log, and is weaker than Probe A.

## Reproduction

The Claude probes used `claude -p ... --settings <file> --allowedTools Bash --model haiku < /dev/null` with a PostToolUse hook that logged its stdin and printed the JSON above. Run the real binary from `~/.local/bin`, not the agent-shims copy, which hangs without a TTY.
