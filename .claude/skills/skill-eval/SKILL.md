---
name: skill-eval
version: 1.0.0
description: Execution-based skill evaluation and self-healing training loop. Runs skills in real environments (browser, shell, API), captures structured error bundles, and feeds them to Claude Code for iterative fixes. Complements SkillForge by adding runtime validation. Use for browser automation training, complex skill debugging, or cost-efficient skill development using Claude Code's flat subscription.
license: MIT
model: claude-sonnet-4-5
metadata:
  domains:
    - meta-skill
    - evaluation
    - training
    - automation
    - self-healing
  type: orchestrator
  inputs:
    - skill-path
    - test-scenario
    - execution-target
  outputs:
    - eval-report
    - error-bundles
    - fixed-skill
---

# Skill Eval - Self-Healing Skill Training Loop

Run skills in real environments, capture failures, and automatically fix them via Claude Code.

```
┌─────────────────┐     skill/fix      ┌─────────────────┐
│   Claude Code   │ ─────────────────► │    OpenClaw     │
│  (reasoning)    │                    │   (execution)   │
│  • writes skill │ ◄───────────────── │   • runs skill  │
│  • troubleshoots│    error bundle    │   • captures err│
└─────────────────┘                    └─────────────────┘
```

---

## Triggers

| Trigger | Action |
|---------|--------|
| `skill-eval {skill-path}` | Run eval loop on existing skill |
| `train skill {skill-path}` | Alias for skill-eval |
| `test skill {name} with {scenario}` | Run specific test scenario |
| `heal skill {name}` | Run eval loop until passing |
| `eval --browser {skill}` | Force browser execution target |

---

## Quick Start

```bash
# Eval an existing skill
skill-eval ~/.claude/skills/browser-login/

# Train with specific scenario
skill-eval ~/.claude/skills/form-filler/ --scenario "Fill checkout form on amazon.com"

# Browser automation with headed mode (watch it work)
skill-eval ~/.claude/skills/scraper/ --target browser --headed

# Max 5 iterations, then report
skill-eval ~/.claude/skills/api-client/ --max-iterations 5
```

---

## Process

```
┌────────────────────────────────────────────────────────────────────┐
│  Phase 1: SETUP                                                    │
│  • Load skill from path                                            │
│  • Parse test scenarios (from SKILL.md or --scenario)              │
│  • Detect execution target (browser/shell/api)                     │
│  • Initialize error bundle store                                   │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Phase 2: EXECUTE                                                  │
│  • Run skill via OpenClaw in target environment                    │
│  • Capture stdout, stderr, exit code                               │
│  • For browser: capture screenshots, DOM state, console logs       │
│  • For API: capture request/response, status codes                 │
│  • Timeout handling with partial state capture                     │
└────────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                SUCCESS              FAILURE
                    │                   │
                    ▼                   ▼
┌──────────────────────┐  ┌──────────────────────────────────────────┐
│  Phase 3a: PASS      │  │  Phase 3b: ERROR BUNDLE                  │
│  • Record success    │  │  • Structure error with context          │
│  • Update eval report│  │  • Include: stack trace, screenshots,    │
│  • Exit loop         │  │    DOM state, recent actions, env info   │
└──────────────────────┘  │  • Save to .skill-eval/bundles/          │
                          └──────────────────────────────────────────┘
                                        │
                                        ▼
┌────────────────────────────────────────────────────────────────────┐
│  Phase 4: CLAUDE CODE FIX                                          │
│  • Send error bundle to Claude Code via --permission-mode          │
│  • Claude Code analyzes, proposes fix                              │
│  • Fix applied to skill files                                      │
│  • Increment iteration counter                                     │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Phase 5: LOOP CHECK                                               │
│  • iterations < max_iterations?                                    │
│  • If YES → return to Phase 2                                      │
│  • If NO → generate failure report, exit                           │
└────────────────────────────────────────────────────────────────────┘
```

---

## Error Bundle Format

Structured JSON for maximum Claude Code understanding:

```json
{
  "bundle_id": "eval-2026-02-19-001",
  "skill": {
    "name": "browser-login",
    "path": "/home/user/.claude/skills/browser-login/",
    "version": "1.0.0"
  },
  "execution": {
    "target": "browser",
    "scenario": "Login to github.com",
    "started_at": "2026-02-19T15:04:00Z",
    "duration_ms": 12500,
    "iteration": 3
  },
  "error": {
    "type": "ElementNotFound",
    "message": "Selector '#login-button' not found after 10s timeout",
    "stack": "...",
    "exit_code": 1
  },
  "context": {
    "last_actions": [
      "navigate to https://github.com/login",
      "fill #login_field with 'user@example.com'",
      "fill #password with '***'",
      "click #login-button (FAILED)"
    ],
    "dom_snapshot": "<html>...</html>",
    "console_logs": ["[warn] Cookie consent not dismissed"],
    "screenshots": [
      ".skill-eval/screenshots/eval-001-before.png",
      ".skill-eval/screenshots/eval-001-error.png"
    ],
    "environment": {
      "browser": "chromium",
      "viewport": "1280x720",
      "user_agent": "..."
    }
  },
  "previous_attempts": [
    {
      "iteration": 1,
      "error": "Timeout navigating to page",
      "fix_applied": "Added waitUntil: 'networkidle'"
    },
    {
      "iteration": 2,
      "error": "Cookie consent modal blocking",
      "fix_applied": "Added cookie consent dismissal step"
    }
  ]
}
```

---

## Execution Targets

| Target | Use Case | Capture |
|--------|----------|---------|
| `browser` | Web automation, scraping | Screenshots, DOM, console, network |
| `browser-headed` | Debug mode, watch execution | Same + visible browser window |
| `shell` | CLI tools, scripts | stdout, stderr, exit code |
| `api` | HTTP requests | Request/response, headers, timing |
| `hybrid` | Multi-step workflows | Combined capture |

### Browser Target

```bash
# Headless (default)
skill-eval ~/.claude/skills/scraper/ --target browser

# Headed (watch it work)
skill-eval ~/.claude/skills/scraper/ --target browser --headed

# With specific viewport
skill-eval ~/.claude/skills/scraper/ --target browser --viewport 1920x1080
```

### Shell Target

```bash
# Run shell-based skill
skill-eval ~/.claude/skills/git-helper/ --target shell

# With specific working directory
skill-eval ~/.claude/skills/git-helper/ --target shell --cwd ~/projects/myrepo
```

---

## Claude Code Integration

The fix phase uses Claude Code with appropriate permissions:

```bash
# Internal command (executed by skill-eval)
claude --permission-mode acceptEdits -p "
Fix this skill error. Error bundle:

$(cat .skill-eval/bundles/latest.json)

The skill is at: ${SKILL_PATH}

Analyze the error, understand what went wrong, and fix the skill.
Focus on:
1. The specific error message and stack trace
2. The DOM state / console logs (for browser issues)
3. Previous fix attempts that didn't fully work

Make minimal, targeted changes. Commit when done.
"
```

### Session Continuity

Claude Code maintains context across iterations via:

1. **Error bundle history** — `previous_attempts` array in bundle
2. **Git history** — each fix is committed, Claude can see diff
3. **Conversation resume** — `claude --continue` for same session

---

## Configuration

Create `.skill-eval/config.yaml` in skill directory (optional):

```yaml
# .skill-eval/config.yaml
execution:
  target: browser
  headed: false
  timeout_ms: 30000
  viewport: 1280x720

scenarios:
  - name: "Happy path login"
    steps:
      - navigate: "https://example.com/login"
      - fill: { selector: "#email", value: "test@example.com" }
      - fill: { selector: "#password", value: "password123" }
      - click: "#submit"
      - assert: { selector: ".dashboard", visible: true }

  - name: "Invalid credentials"
    steps:
      - navigate: "https://example.com/login"
      - fill: { selector: "#email", value: "bad@example.com" }
      - fill: { selector: "#password", value: "wrong" }
      - click: "#submit"
      - assert: { selector: ".error-message", contains: "Invalid" }

limits:
  max_iterations: 10
  max_time_minutes: 30

success_criteria:
  - all_scenarios_pass: true
  - no_console_errors: true
```

---

## Integration with SkillForge

Chain SkillForge creation with skill-eval validation:

```bash
# SkillForge creates, skill-eval validates
SkillForge: create a browser automation skill for logging into GitHub

# Then automatically:
skill-eval ~/.claude/skills/github-login/ --scenario "Login with valid credentials"
```

### SkillForge Hook (Optional)

Add to SkillForge Phase 4 synthesis:

```yaml
# In SkillForge config
post_creation:
  - skill-eval: 
      enabled: true
      max_iterations: 5
      require_pass: false  # warn but don't block
```

---

## Commands

| Command | Description |
|---------|-------------|
| `skill-eval {path}` | Run full eval loop |
| `skill-eval --dry-run {path}` | Show what would execute |
| `skill-eval --report {path}` | Generate report without fixing |
| `skill-eval --max-iterations N` | Limit fix attempts |
| `skill-eval --scenario "..."` | Override test scenario |
| `skill-eval --target {browser\|shell\|api}` | Force execution target |
| `skill-eval --headed` | Browser in visible mode |
| `skill-eval --continue` | Resume previous eval session |

---

## Output

### Eval Report

Generated at `.skill-eval/reports/eval-{timestamp}.md`:

```markdown
# Skill Eval Report: browser-login

**Status**: ✅ PASS (after 3 iterations)
**Duration**: 4m 32s
**Skill Path**: ~/.claude/skills/browser-login/

## Iterations

| # | Result | Error | Fix Applied |
|---|--------|-------|-------------|
| 1 | ❌ | Timeout navigating | Added networkidle wait |
| 2 | ❌ | Cookie modal blocking | Added consent dismissal |
| 3 | ✅ | - | - |

## Changes Made

```diff
- await page.goto(url);
+ await page.goto(url, { waitUntil: 'networkidle' });

+ // Dismiss cookie consent if present
+ const consentBtn = await page.$('.cookie-accept');
+ if (consentBtn) await consentBtn.click();
```

## Lessons Learned

- Always wait for network idle on navigation
- Check for cookie consent modals before form interaction
- GitHub login button selector changed from #login-button to [type="submit"]

## Recommendations

- [ ] Add to skill's edge cases documentation
- [ ] Consider adding to SkillForge patterns
```

---

## Cost Analysis

The key benefit — cost reduction:

| Actor | Cost Model | Role |
|-------|------------|------|
| Claude Code | $200/month flat | Reasoning, debugging, fixing |
| OpenClaw | Per-token API | Execution only (minimal tokens) |

**Typical savings**: 90-95% token cost reduction for skill development, since the expensive reasoning happens in Claude Code's flat subscription.

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| No max iterations | Infinite loop risk | Set reasonable limit (5-10) |
| Overly broad scenarios | Hard to debug | Specific, atomic test cases |
| Skipping headed mode | Can't see what's wrong | Use `--headed` for browser debug |
| Ignoring previous attempts | Repeats same fixes | Include history in bundle |
| Manual skill edits during eval | Breaks continuity | Let Claude Code make all edits |

---

## Scripts

### `scripts/run-eval.py`

Main orchestrator for the eval loop:

```python
#!/usr/bin/env python3
"""Skill eval orchestrator."""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict

@dataclass
class EvalResult:
    success: bool
    iterations: int
    duration_ms: int
    final_error: str | None
    changes_made: list[str]

def run_skill(skill_path: Path, target: str, scenario: str) -> tuple[bool, dict]:
    """Execute skill and capture results."""
    # Implementation depends on target type
    pass

def create_error_bundle(skill_path: Path, error: dict, context: dict, iteration: int) -> dict:
    """Create structured error bundle for Claude Code."""
    return {
        "bundle_id": f"eval-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}",
        "skill": {
            "name": skill_path.name,
            "path": str(skill_path),
        },
        "execution": {
            "iteration": iteration,
        },
        "error": error,
        "context": context,
    }

def invoke_claude_code(bundle: dict, skill_path: Path) -> bool:
    """Send error bundle to Claude Code for fixing."""
    bundle_json = json.dumps(bundle, indent=2)
    
    result = subprocess.run([
        "claude", "--permission-mode", "acceptEdits", "-p",
        f"Fix this skill error:\n\n{bundle_json}\n\nSkill path: {skill_path}"
    ], capture_output=True, text=True)
    
    return result.returncode == 0

def main():
    # Parse args, run loop, generate report
    pass

if __name__ == "__main__":
    main()
```

### `scripts/capture-browser.py`

Browser execution and capture:

```python
#!/usr/bin/env python3
"""Browser execution target with full capture."""

# Uses playwright or similar for:
# - Screenshot capture
# - DOM snapshot
# - Console log capture
# - Network request logging
```

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `SkillForge` | Creates skills; skill-eval validates them |
| `reflect` | Captures learnings; skill-eval generates them |
| `chaos-experiment` | Theory; skill-eval is practical execution |
| `coding-agent` | Alternative; skill-eval uses Claude Code specifically |

---

## Future Extensions

1. **Parallel eval** — Run multiple scenarios concurrently
2. **Regression suite** — Save passing scenarios as regression tests
3. **CI integration** — Run skill-eval in GitHub Actions
4. **Cost tracking** — Log token usage for OpenClaw portion
5. **Learning export** — Auto-update skill observations from fixes
