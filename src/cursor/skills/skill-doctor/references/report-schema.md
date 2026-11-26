# report.json shape

Read this from Step 5 of `SKILL.md`. Write the file in this shape, without
numbers, then run `assemble_report.py` to fill them. The raw rubric means never
go in `scores`.

```json
{
  "title": "Agent Skill Report",
  "generated_at": "<ISO timestamp>",
  "harness": "<harness from inventory.json>",
  "handle": "<repo_name from inventory.json>",
  "stats": {
    "sessions_analyzed": 0, "sessions_scanned": 0,
    "skills_found": 0, "skills_used": 0, "window_days": 45
  },
  "sampling": {
    "harness_coverage_complete": true,
    "notice": null,
    "per_harness": {
      "<harness>": {"scoreable": 0, "skill_candidates": 0, "sampled": 0}
    }
  },
  "scores": {
    "efficiency": 0.0,
    "code_quality": 0.0,
    "procedure_compliance": 0.0,
    "verbosity": 0.0,
    "skill_coverage": 0.0,
    "overall": 0.0
  },
  "top_findings": ["", "", ""],
  "suggestions": [
    {
      "skill": "",
      "status": "unevaluated",
      "owner": "skill | new-skill | tooling",
      "owner_target": "<tooling owner, only when owner is tooling>",
      "target": "<exact skill path, or empty when variants are unresolved>",
      "variants": [{"path": "", "sha256": ""}],
      "change": "<one-sentence summary of the edit>",
      "evidence": "<observed fact: which session(s), scorer, and what happened>",
      "mechanism": "<hypothesis: the behavioral change and why it may help>",
      "expected_improvement": "<unmeasured expected behavior change>",
      "reproduction": "<smallest useful reproduction>",
      "acceptance_checks": ["<check skillopt can score>"],
      "risks": ["<known risk or counterexample>"],
      "missing_evidence": ["<what the transcripts do not show>"],
      "proposed_path": "<path under proposed/, if an edit was drafted>",
      "diff": "<unified diff, or full content for a new skill>"
    }
  ],
  "evaluation": {"diagnosis": "static", "optimization": "not_run"}
}
```

## Optional `adr_drift` section

Add this object only when Step 1a ran. Reports without it render unchanged.
The section never feeds `scores.overall`. The report reads findings from the
scan files by path, so do not copy findings into `report.json`.

```json
"adr_drift": {
  "skipped": "<reason, only when Step 1a did not run; omit repos then>",
  "repos": [
    {
      "repo": "<repo slug>",
      "scan": "adr_drift/<repo-slug>.json",
      "decisions": "adr_drift/<repo-slug>-decisions.json"
    }
  ]
}
```

- `scan` is the file `adr_drift.py scan` wrote. Required for each repo.
- `decisions` is optional: the file skill-bootstrap's `bootstrap_adr.py scan`
  wrote, rendered as a candidate table without grading it.

Paths are relative to the folder that holds `report.json` and must resolve
inside it. A path outside it, a missing or unreadable file, invalid JSON, or an
unexpected shape makes `render_report.py` exit 2.

From the scan file the renderer reads `findings` (a list, required), `head`,
`examined`, `truncated`, `read_errors`, and `locate.rejected`. A truncated scan,
any unreadable paths, and any refused paths are shown in the report. Each
finding needs a non-empty `suggested_fix`, or `render_report.py` exits 1.

The `decisions` file is an object with a `candidates` list. The renderer reads
these fields from each candidate and ignores the rest: `id`, `title`, `reason`,
and from `source`, `sha`, `file`, and `pr_url` (or `url`). The Source column
shows the commit, or the decision-log `file` when a candidate has no commit. A
file with no `candidates` list makes `render_report.py` exit 2.

### ADR-only report

An ADR-only report has no scorecard. It needs `"mode": "adr_only"` and an
`adr_drift` object. Without the marker, a report with no `scores.overall` exits
with code 1. `title` and `generated_at` are optional. The smallest valid file:

```json
{
  "mode": "adr_only",
  "adr_drift": {
    "repos": [{"repo": "my-repo", "scan": "adr_drift/my-repo.json"}]
  }
}
```

Kinds and fixes are in `adr-drift.md`.
