# ADR-063 Kill Gate Eval

Issue: #2926
Date: 2026-07-08
Model: claude-sonnet-4-6
Harness: scripts/eval/eval-knowledge-integration.py
Prompts: tests/evals/skills/triage-prompts.json

## Commands

```bash
export ANTHROPIC_API_KEY=$(grep -E '^ANTHROPIC_API_KEY=' .env | cut -d= -f2-)
python3 scripts/eval/eval-knowledge-integration.py --prompts-file tests/evals/skills/triage-prompts.json --skill memory-search --dry-run
python3 scripts/eval/eval-knowledge-integration.py --prompts-file tests/evals/skills/triage-prompts.json --skill memory-reflexion --dry-run
python3 scripts/eval/eval-knowledge-integration.py --prompts-file tests/evals/skills/triage-prompts.json --skill memory-search --output evals/reports/adr-063-kill-gate-20260708/memory-search.json
python3 scripts/eval/eval-knowledge-integration.py --prompts-file tests/evals/skills/triage-prompts.json --skill memory-reflexion --output evals/reports/adr-063-kill-gate-20260708/memory-reflexion.json
```

## Results

| Skill | Verdict | Baseline avg | Enhanced avg | Delta | Context chars |
|-------|---------|--------------|--------------|-------|---------------|
| memory-search | PROCEED | 1.78 | 4.61 | 2.83 | 6210 |
| memory-reflexion | PROCEED | 2.06 | 4.94 | 2.89 | 33367 |

## Kill Criteria

Both sibling skills pass the eval-knowledge-integration kill gate. No regression was reported. The ADR-063 behavior-change kill criterion did not fire.

The hot path context target applies to router plus hot-path sub-skill. This run measured memory-search at 6210 chars. The combined router path was not remeasured in this fixture-only issue.
