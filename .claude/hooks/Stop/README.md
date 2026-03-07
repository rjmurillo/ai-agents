# Stop Hook: invoke_skill_learning.py

Automatically extracts skill learnings from session conversations.

## Requirements

**Python 3.12+** with `anthropic` package installed.

## Setup

### Option 1: pyenv (Recommended)

Ensure pyenv is initialized in your shell (`~/.bashrc` or `~/.zshrc`):

```bash
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
```

Then install anthropic:

```bash
python -m pip install anthropic
```

The `.python-version` file at the repository root ensures Python 3.12.8 is used.

### Option 2: System Python

Install Python 3.12+ and the anthropic package:

```bash
# Ubuntu/Debian
sudo apt install python3.12 python3.12-venv
python3.12 -m pip install --user anthropic

# macOS
brew install python@3.12
python3.12 -m pip install anthropic
```

## Configuration

### API Key (Required for LLM Fallback)

The hook uses Claude Haiku 4.5 for LLM fallback classification when pattern-based detection confidence is below threshold (default: 0.7).

Set your Anthropic API key in `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

Or export it in your shell:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

**Cost**: ~$0.0001 per session with learnings (Haiku pricing)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (required) | Anthropic API key for LLM fallback |
| `SKILL_LEARNING_USE_LLM` | `true` | Enable LLM fallback (`true`/`false`) |
| `SKILL_LEARNING_CONFIDENCE_THRESHOLD` | `0.7` | Confidence threshold for LLM fallback (0.0-1.0) |

**Disable LLM fallback** to save API costs (relies only on pattern-based detection):

```bash
export SKILL_LEARNING_USE_LLM=false
```

## Behavior

- **Model**: Uses Claude Haiku 4.5 for LLM fallback classification (cost-efficient)
- **Non-blocking**: Hook failures don't prevent session completion
- **Silent**: Only outputs learning notifications on success
- **Graceful degradation**: Falls back to pattern-based detection if API key missing

## Troubleshooting

### Hook not running

Check Claude Code logs for hook errors:

```bash
ls ~/.claude/debug/  # Recent debug logs
```

### Python version issues

Verify Python version:

```bash
python3 --version  # Should be 3.12+
```

### Missing anthropic package

```bash
python3 -m pip install anthropic
```

## Related

- Hook source: `.claude/hooks/Stop/invoke_skill_learning.py`
- Skill observations: `.serena/memories/*-observations.md`
- Configuration: `LLM_MODEL` in hook source (line 175)
