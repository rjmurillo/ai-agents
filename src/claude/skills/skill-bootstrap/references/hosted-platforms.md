# Hosted and Mixed-Platform Workflows

Load this reference when a selected outcome touches source hosting, a tracker,
a PR, a pipeline, an artifact, or a release. Discovery here is read-only.
Describe a legitimate correction; never exercise an override or change a
policy during bootstrap.

## Contents

- [Resolve each hosting role](#resolve-each-hosting-role)
- [Identifiers](#identifiers)
- [Tracker semantics](#tracker-semantics)
- [GitHub merge requirements](#github-merge-requirements)
- [Azure DevOps policies](#azure-devops-policies)
- [Build and release](#build-and-release)

## Resolve each hosting role

Resolve each role on its own. One project can keep source on GitHub, run
pipelines in Azure DevOps, and track work in Azure Boards.

| Role | Question to answer |
| --- | --- |
| Source | Which host owns the canonical branch? |
| Tickets or work items | Which tracker owns accepted work? |
| PRs | Which host evaluates and merges changes? |
| Pipelines | Which system runs required checks? |
| Artifacts and releases | Which system publishes the candidate? |

For each selected action, name the authoritative system and the integration
that connects it to the next system. Prefer an installed host skill (for
example `github`, or an Azure DevOps feature) over raw CLI calls.

## Identifiers

Put a known ID or slug directly in the workflow when it removes repeated
discovery. Keep the scope and value type explicit beside it. Bind a value only
after you read it back from the host.

| Host | Do not confuse |
| --- | --- |
| GitHub | REST database `id`, GraphQL `node_id`, issue or PR `number` |
| Azure DevOps | Project name and project GUID; repository GUID; team identity |
| Azure Boards | Classification-node integer IDs, node GUIDs, and area or iteration path strings. Each field accepts a different one. |
| Pipelines | Build definition ID, release definition ID, run ID |

Durable skill text may hold stable values: organization, project, repository,
definition IDs, area paths. Current work items, active iterations, PR
evaluations, and run IDs stay in task context. Refresh a stored mapping only
when scope changes, failure evidence implicates it, or the workflow requires
freshness.

## Tracker semantics

Find how the project actually uses its tracker: item types, templates,
required fields, ownership, states, naming, and closure conventions.

For each relationship the workflow uses (related, parent and child,
duplicate, predecessor and successor, blocked-by, blocking), record:

1. The direction.
2. The API representation.
3. The read-back check that proves the link exists.

Separate four things that look alike:

| Form | Effect |
| --- | --- |
| Text mention | Displays a reference. Creates no stored link. |
| Hyperlink | Navigates. Creates no stored link. |
| Stored relationship | A queryable link. Read it back. |
| Automatic transition | A state change that a keyword or merge triggers. |

The same text can produce a different form on a different surface. Verify
reference syntax for the actual field, endpoint, and platform version. Field
formats differ: plain text, HTML, and Markdown. Examples:

- Azure DevOps `#12345`: a mention in a work item discussion, but a stored
  Development link in a PR description, or in a commit message when the
  repository's commit mention linking setting is on. Imported repositories
  can have it off; read the setting.
- Azure DevOps `!455667`: a PR mention where the surface supports it.
- `AB#123` in a GitHub commit message, PR description, or issue
  description, with the Azure Boards app connected: a stored link on the
  work item. A PR title or comment creates no link.
- GitHub `owner/repo#123`: a cross-reference. Closing keywords add an
  automatic transition on merge to the default branch.

Use a full URL when shorthand is ambiguous, then confirm the destination
relationship exists. Tracker mutations need the task's authorization.

## GitHub merge requirements

1. Read rulesets, inherited organization rules, and legacy branch protection
   as separate sources.
2. Match each required check context and integration to the evaluated
   revision and the triggering event.
3. Separate PR head, test-merge, and merge-group evaluation.
4. Read reviews, unresolved threads, allowed merge methods, and any
   deployment or security requirement.
5. Report an unreadable setting as `UNKNOWN`.

## Azure DevOps policies

1. List enabled and blocking policies, including those set at broader scopes.
2. Join each policy configuration to the actual PR's policy evaluations. Do
   not infer a blocker from a policy name.
3. Keep evaluation states distinct: queued, running, rejected, broken,
   approved, and not applicable.
4. Read resource approvals and checks that live outside pipeline YAML.
5. Use a supported API version. Report an unreadable setting as `UNKNOWN`.

## Build and release

1. Route to the repository-owned release guide and the executable definition.
   Do not copy the procedure into a skill.
2. Identify the version source, branch convention, tag format, release
   trigger, and candidate revision.
3. Separate five stages: build, promote, publish, deploy, and consumer
   adoption.
4. Keep version numbers and release status out of durable skill text. They
   change on every release.
