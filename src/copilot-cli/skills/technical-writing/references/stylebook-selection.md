# Stylebook Selection

Pick one primary stylebook per page. Add a secondary only for one narrow
constraint, and name that constraint. The 16 stylebooks are in
[stylebooks/](stylebooks/). Each is an independent interpretation of a public
style system, not the owner's official guide (see [provenance](provenance.md)).

## Precedence

Apply the Unified Precedence list in the skill's `SKILL.md`. It ranks the
target repository, a site profile, the primary stylebook, the base rules, and
the secondary stylebook, in that order.

Never let a stylebook change a fact. Every stylebook starts by protecting the
source material; that rule outranks voice and tone.

## Defaults when the target has no style guide

| Target | Primary | Common secondary |
|---|---|---|
| Developer library or tool docs (.NET, Microsoft ecosystem) | `microsoft-writing-style` | `google-developer-docs` for global-reader precision |
| Developer library or tool docs (other ecosystems) | `google-developer-docs` | `github-docs` for task flow |
| Product workflow and troubleshooting guides | `github-docs` | `microsoft-writing-style` for error text |
| Operations and infrastructure tasks | `kubernetes-docs` | `red-hat-docs` for modular procedures |
| Modular enterprise docs (concept, procedure, reference split) | `red-hat-docs` | `gitlab-docs` for topic types |
| Web platform and standards explainers | `mdn-web-docs` | `w3c-technical-reports` for normative wording |
| Specifications and conformance requirements | `w3c-technical-reports` | none |
| Test reports and engineering analyses | `nasa-technical-writing` | none |
| UI labels, alerts, onboarding copy | `apple-interface-writing` | `microsoft-writing-style` |
| Public service, forms, eligibility | `govuk` or `18f-content` | the other, for inclusion |
| Health, safety, or risk communication | `cdc-clear-communication` or `nhs-health-content` | none; get expert review |
| Investor or regulatory disclosure | `sec-plain-english` | none; get counsel review |
| Customer education and brand copy | `mailchimp-content` | none |

## Editorial behavior

| Skill | Primary audience | Primary optimization | Distinctive behavior | Avoids |
| --- | --- | --- | --- | --- |
| `google-developer-docs` | Global technical practitioners | Successful implementation | Explicit actors, stable terms, prerequisite-first procedures | Idioms, assumed ease, vague pronouns |
| `govuk` | People using public services | Fast decisions and task completion | User need first; legal conditions and next actions exposed | Department-first framing, policy jargon, promotion |
| `gitlab-docs` | Product users and contributors | Searchability, precision, trust | One topic type; customer perspective; localization-ready prose | Marketing, self-reference, ambiguity |
| `github-docs` | Developers using a product | Verified workflow completion | Prerequisites, outcomes, approachable troubleshooting | Hidden context, blame, obviousness assumptions |
| `kubernetes-docs` | Cluster operators and developers | Version-aware operational accuracy | Explicit feature state, resource scope, verification, cleanup | Future promises, stale time words, ambiguous `we` |
| `mdn-web-docs` | Web developers at a stated level | Transferable web-platform understanding | Runnable examples; standards and browser behavior separated | Missing assumptions, decorative examples, blurred facts |
| `red-hat-docs` | Enterprise administrators and developers | Modular, supportable documentation | Concept/procedure/reference separation; visible system state | Mixed topic types, hidden privileges, ornamental prose |
| `18f-content` | People using US government services | Inclusive completion with less burden | Transaction design, alternative routes, recovery-focused content | Bureaucratese, agency-centric flow, shame or blame |
| `microsoft-writing-style` | Product and support users | Friendly, scannable action | Important point first; direct help; solution-oriented errors | Formal distance, unnecessary detail, user blame |
| `mailchimp-content` | Small-business and marketing customers | Clear, encouraging education | Situation-aware tone with removable personality | Hype, forced jokes, condescension, B2B fog |
| `apple-interface-writing` | People moving through an app | Clear choices in limited space | Verb-led labels and predictable consequences across a flow | Cute labels, vague errors, device mismatch |
| `cdc-clear-communication` | Defined public-health audiences | Comprehension and health action | One primary message; visible action; contextual numbers and risk | Competing messages, unsupported claims, false precision |
| `nhs-health-content` | Patients and health-service users | Clinically careful next steps | Explicit urgency, safety-netting, uncertainty, inclusive explanations | Implied diagnosis, hidden caveats, mixed urgency |
| `sec-plain-english` | Investors and shareholders | Understandable material disclosure | Fact inventory; cause-risk-consequence chains; qualification mapping | Boilerplate-first prose, lost risk language, false certainty |
| `w3c-technical-reports` | Implementers and specification reviewers | Precise interoperable requirements | Normative/informative split; testable actors, conditions, conformance | Invented requirements, vague references, casual `MUST` |
| `nasa-technical-writing` | Engineers, scientists, technical reviewers | Reproducibility and evidence traceability | Conditions and measurements preserved; results separated from interpretation | Promotional claims, hidden anomalies, unsupported extrapolation |

## Artifact and tone

| Skill | Typical artifacts | Formality | Personality tolerance | Compliance / precision importance |
| --- | --- | --- | --- | --- |
| `google-developer-docs` | Tutorials, API guides, concepts | Medium | Low | High technical precision |
| `govuk` | Eligibility, policy, service pages | Medium | Very low | High legal and policy fidelity |
| `gitlab-docs` | Product and engineering docs | Medium | Low | High product precision |
| `github-docs` | Workflows, help, troubleshooting | Medium | Low to medium | High product and security precision |
| `kubernetes-docs` | Tasks, concepts, resource reference | Medium-high | Very low | Very high version and operational precision |
| `mdn-web-docs` | Web reference, guides, learning | Medium | Low | High standards and behavior precision |
| `red-hat-docs` | Enterprise modules and procedures | High | Very low | Very high supportability and configuration precision |
| `18f-content` | Forms, transactions, notices | Medium | Low | High policy, rights, and accessibility fidelity |
| `microsoft-writing-style` | Product help, support, UX | Low-medium | Medium | Medium-high product precision |
| `mailchimp-content` | Customer education and brand copy | Low-medium | Medium-high when stakes permit | Medium; high where claims or compliance apply |
| `apple-interface-writing` | Labels, alerts, onboarding | Low-medium | Low | High interaction and consequence precision |
| `cdc-clear-communication` | Campaigns, warnings, health education | Medium | Very low | Very high health, risk, and evidence precision |
| `nhs-health-content` | Patient pages, appointments, treatments | Medium | Very low | Very high clinical and safety precision |
| `sec-plain-english` | Disclosures, risk factors, shareholder letters | High | Very low | Very high material and legal qualification fidelity |
| `w3c-technical-reports` | Specifications, protocols, standards | High | None in normative text | Very high conformance and interoperability precision |
| `nasa-technical-writing` | Test reports, memoranda, engineering analyses | High | Very low | Very high measurement and evidence precision |

## Upstream selection rule

Select by artifact and user need, not by which organization the subject mentions. A government
form about a software cluster may need `govuk`; a versioned cluster procedure may need
`kubernetes-docs`. If two systems fit, name the primary system and the narrow secondary constraint.
