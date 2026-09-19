## Architecture

- One protocol-valid stdout document per group: context parts join on a blank line as plain text, except `PreToolUse`/`PostToolUse`, wrapped in one `hookSpecificOutput.additionalContext` object.
