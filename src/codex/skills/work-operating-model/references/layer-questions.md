# Layer Questions

The 5-layer interview surfaces how a team actually works. Each layer has a primary question, a small set of follow-ups, and a finishing prompt. Ask the primary question first. Use follow-ups only when the answer is thin. Always finish with the closing prompt before moving to the next layer.

The interview is conversational. Do not read this file aloud. Use the questions as a checklist behind the conversation.

## Layer 1: Rhythms

**Primary question.** When does work happen, and on what cadence?

**Follow-ups.**

- Walk me through a typical week. What recurring meetings, syncs, or reviews shape it?
- What planning cycle does the team run on (sprint, kanban pull, quarterly OKRs, ad hoc)?
- Which cadences are formal (calendar, scheduled, agenda) and which are informal (slack threads, drive-bys, "we just know")?
- What release or delivery cadence does the team commit to externally?

**Closing prompt.**

> Of the cadences you described, which ones serve the team and which ones are habits no one would defend if asked?

**Output section.** Populate `rhythms.cadences` and `rhythms.milestones`. Tag each cadence as `documented` (link to a doc, calendar invite, or playbook) or `tacit` (note who owns it).

## Layer 2: Decisions

**Primary question.** Who decides what, and how is the decision recorded?

**Follow-ups.**

- For decisions of size X (architectural, hiring, scope-cut), who has the call?
- Where do those decisions get written down (ADR, ticket, slack message, nowhere)?
- What kinds of decisions get re-litigated and why?
- Who do you check with informally before a formal decision is made?

**Closing prompt.**

> Name a recent decision you made. Walk me through how it was made and where it lives now.

**Output section.** Populate `decisions.decision_rights` and `decisions.review_triggers`. For every decision type, mark `formality` as `formal` (recorded in a known place) or `informal` (lives in a person's head or a chat thread).

## Layer 3: Dependencies

**Primary question.** Who do you wait on, and who waits on you?

**Follow-ups.**

- Which other teams or services block your work most often, and on what?
- Which other teams or services depend on yours, and what do they need?
- For each dependency, is there a contract (interface, SLA, doc) or is it implicit?
- What happens when a dependency is late or wrong?

**Closing prompt.**

> If you had to draw your team in the middle of a graph and label every arrow in and out, which arrow worries you most?

**Output section.** Populate `dependencies.upstream` and `dependencies.downstream`. Mark `criticality` as `low`, `medium`, or `high` based on what blocks if it fails.

## Layer 4: Institutional Knowledge

**Primary question.** What lives in someone's head and not in a doc?

**Follow-ups.**

- If person X were unreachable for two weeks, what would the team have to guess at?
- Which onboarding question gets asked over and over by new joiners?
- Which past decision do you find yourself explaining repeatedly because no one wrote it down?
- Where does the team go when the docs are wrong?

**Closing prompt.**

> Pick the one piece of tacit knowledge whose loss would hurt the team most. Why has it not been written down?

**Output section.** Populate `institutional_knowledge.tacit`. For each item, set `documentation_status` to `none`, `partial`, or `complete`. Note the `owner` (the person who currently holds the knowledge).

This layer is often the hardest. People are shy about admitting what is undocumented. Ask anyway. If the team genuinely cannot answer, record the question in `metadata.skipped_layers` with a note; do not skip silently.

## Layer 5: Friction

**Primary question.** What is broken or slow that the team has accepted?

**Follow-ups.**

- What part of the work do you dread because of how it has to be done?
- What process step exists only because something else broke once and no one removed the workaround?
- Where do you spend time you do not value?
- What would the team fix first if a quarter opened up?

**Closing prompt.**

> If you could remove one piece of friction tomorrow with no political cost, what would it be?

**Output section.** Populate `friction.blockers`. Tag `category` as `tooling`, `process`, `communication`, or `other`. Tag `impact` as `low`, `medium`, or `high`.

## After Layer 5

Summarize back to the team. Confirm the document. Then write the JSON. The validator (`scripts/validate_operating_model.py`) is the gate; do not declare the model complete until it exits 0.
