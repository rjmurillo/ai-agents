
```yaml
SKILLCREATOR_CONFIG:
  mode: autonomous
  depth: maximum  # always
  core_lens: evolution_timelessness

  analysis:
    min_lens_depth: 5
    max_questioning_rounds: 7
    termination_empty_rounds: 3

  synthesis:
    panel_size: 3
    require_unanimous: true
    max_iterations: 5
    escalate_to_human: true

  evolution:
    min_timelessness_score: 7
    min_extension_points: 2
    require_temporal_projection: true

  model:
    primary: claude-opus-4-5-20251101
    subagents: claude-opus-4-5-20251101
```
