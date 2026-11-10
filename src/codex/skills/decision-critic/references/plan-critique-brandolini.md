# Brandolini's Law: Review Burden Allocation

Loaded by the `critic` agent when a plan or diff rests on many unsupported assertions. The decision-oriented version of this model is the sibling reference below.

The energy needed to refute a claim is an order of magnitude larger than the energy needed to produce it (Alberto Brandolini, the bullshit asymmetry principle). A confident, unsupported assertion is cheap for the author to write and expensive for you to disprove. The asymmetry favors the producer, so unverified claims accumulate faster than a reviewer can clear them.

Allocate your scrutiny accordingly. For each claim the plan or diff rests on, estimate whether refuting it costs more than the author would have spent supplying evidence:

- When refutation effort exceeds authorship effort, do not chase the claim by hand. Push the burden back: make "author supplies evidence first" a finding (`file:line`, the claim, "evidence not supplied; burden of proof sits with the author").
- Flag any PR whose total refutation effort exceeds its authorship effort. A wall of plausible, citation-free assertions is a red flag, not a passing grade. Refuting it line by line is how a weak plan passes by attrition.
- Spend reviewer energy where the consequence of a wrong claim is highest, not uniformly across every assertion.

"Prove me wrong" and "it is obvious that..." weaponize the asymmetry; treat them as findings, not as arguments. Full model and verification checklist: [critical-thinking-brandolinis-law.md](critical-thinking-brandolinis-law.md).
