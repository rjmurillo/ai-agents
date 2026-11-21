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
The section never feeds `scores.overall`. `render_report.py` exits 1 when any
finding has an empty `suggested_fix`.

```json
"adr_drift": {
  "skipped": "<reason, only when Step 1a did not run; omit repos then>",
  "repos": [
    {
      "repo": "<repo slug>",
      "head": "<commit SHA the scan read>",
      "examined": 300,
      "truncated": false,
      "findings": [
        {
          "id": "<id from the scan file>",
          "kind": "<finding kind>",
          "group": "Numbering | Links | History",
          "severity": "info | low | medium | high",
          "confidence": "deterministic | heuristic",
          "evidence": {"path": "", "line": 0, "sha": "", "subject": ""},
          "suggested_fix": "<non-empty text>"
        }
      ]
    }
  ]
}
```

Copy `findings` from the scan file. Kinds and fixes are in `adr-drift.md`.
