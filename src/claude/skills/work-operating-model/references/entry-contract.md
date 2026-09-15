# Entry Contract: Output JSON Schema

The skill emits a single canonical JSON document. The optional markdown views (`USER.md`, `SOUL.md`, `HEARTBEAT.md`) are projections of this document; the JSON is the source of truth.

## Top-Level Shape

```json
{
  "schema_version": "1.0.0",
  "team": { ... },
  "rhythms": { ... },
  "decisions": { ... },
  "dependencies": { ... },
  "institutional_knowledge": { ... },
  "friction": { ... },
  "metadata": { ... }
}
```

All eight keys are required. A missing key is a schema failure.

## `schema_version`

A string. Currently `"1.0.0"`. Bump on breaking changes only.

## `team`

```json
{
  "name": "string (required)",
  "scope": "string (optional, what the team owns or produces)",
  "size": 0
}
```

`size` is an integer (head count) or `null` if the team prefers not to disclose. Negative values are rejected.

## `rhythms`

```json
{
  "cadences": [
    {
      "name": "string",
      "frequency": "string (e.g. 'weekly', 'daily', 'monthly')",
      "owner": "string",
      "purpose": "string",
      "source": "documented|tacit"
    }
  ],
  "milestones": [
    {
      "name": "string",
      "frequency": "string"
    }
  ]
}
```

Both arrays may be empty if the team has none of that kind.

## `decisions`

```json
{
  "decision_rights": [
    {
      "decision_type": "string (e.g. 'architecture', 'hiring', 'scope cut')",
      "decider": "string (role or person)",
      "informed": ["string"],
      "formality": "formal|informal",
      "source": "documented|tacit"
    }
  ],
  "review_triggers": ["string"]
}
```

`formality` is `formal` when the decision is recorded in a known artifact (ADR, ticket, doc) and `informal` when it lives in chat or memory. The contrast is the value; do not collapse the two.

## `dependencies`

```json
{
  "upstream": [
    {
      "name": "string",
      "role": "string (what this dependency provides)",
      "criticality": "low|medium|high",
      "source": "documented|tacit"
    }
  ],
  "downstream": [ ... same shape ... ]
}
```

`upstream` is what the team waits on. `downstream` is who waits on the team.

## `institutional_knowledge`

```json
{
  "tacit": [
    {
      "topic": "string",
      "owner": "string",
      "documentation_status": "none|partial|complete"
    }
  ]
}
```

Only items where `documentation_status` is `none` or `partial` should appear here. Fully documented knowledge belongs in the relevant doc, not in the operating model.

## `friction`

```json
{
  "blockers": [
    {
      "description": "string",
      "impact": "low|medium|high",
      "category": "tooling|process|communication|other"
    }
  ]
}
```

## `metadata`

```json
{
  "interview_date": "YYYY-MM-DD",
  "interview_status": "in_progress|complete",
  "completed_layers": ["rhythms", "decisions", "dependencies", "institutional_knowledge", "friction"],
  "skipped_layers": [{ "layer": "string", "reason": "string" }],
  "revisions": [{ "date": "YYYY-MM-DD", "section": "string", "note": "string" }]
}
```

`interview_date` MUST be `YYYY-MM-DD`. `interview_status` MUST be either `in_progress` or `complete`. `completed_layers` is a list of layer keys the interview captured (subset of the canonical five). `skipped_layers` and `revisions` may be empty arrays.

## Validation

The validator (`scripts/validate_operating_model.py`) enforces:

- All eight top-level keys present.
- `schema_version` is the literal string `"1.0.0"`.
- `team.name` is a non-empty string.
- `metadata.interview_date` matches `YYYY-MM-DD`.
- `metadata.interview_status` is one of the two allowed values.
- `metadata.completed_layers` is a list of strings drawn from the canonical layer set.
- Enum fields (`source`, `formality`, `criticality`, `documentation_status`, `impact`, `category`) hold allowed values when present.

The validator is intentionally permissive on optional fields. The output is meant to grow; new optional sections do not break old documents. Breaking changes bump `schema_version`.
