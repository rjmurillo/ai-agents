---
name: business-strategy
version: 0.1.0
description: "Route a founder problem to the right business framework, then load that framework on demand. Distills 14 business books (customer discovery, positioning, pricing, sales, growth, persuasion) into scored, decision-tree skills. Use when you say diagnose my business problem, what framework applies, how do I validate demand, price this, position this, generate leads, or close deals. Do NOT use for software design (use the engineering rules) or for a single named decision (use decision-critic)."
license: MIT
user-invocable: true
metadata:
  pack: business-strategy
  jtbd_stages: [Discovery, Validation, Positioning, GoToMarket, Persuasion]
  source_pattern: getagentseal/founder-playbook (MIT)
---

# Business Strategy

The front door to a 14-book business-strategy pack. A founder arrives with a felt
problem ("sales are flat", "nobody replies", "I do not know what to build") and no
idea which framework applies. This skill names the real problem, routes to the one
reference that addresses it, and refuses to guess when the symptom is ambiguous.

Each reference is an original distillation (decision tree, scored checklist, honest
limitations, cross-book conflicts, worked example) of one book. They are loaded on
demand: read only the one this router points you to.

## When to use

Start here whenever the problem is a symptom ("growth stalled") rather than a named
method ("run SPIN Selling"). If you already know the framework, skip the router and
read its reference directly.

## Triggers

| Trigger phrase | Action |
|----------------|--------|
| `diagnose my business problem` | Walk the decision tree below |
| `what framework applies` | Walk the decision tree below |
| `validate demand or find customers` | Start with mom-test; use four-steps only after interview evidence names a repeatable buyer |
| `price or position this` | Route to monetizing-innovation for price pain, or obviously-awesome for category confusion |
| `get leads or close deals` | Route to 100m-leads for lead volume, or spin-selling for qualified pipeline stalls |

## Decision tree: symptom to reference

Route on the dominant symptom. If two apply, take the earliest funnel stage: an
upstream positioning problem usually causes the downstream messaging or pricing
problem. Read the named reference, then act.

- You do not know what to build, or whether anyone wants it -> `references/mom-test.md` (interview for evidence, not flattery). Follow with `references/four-steps.md` only after interviews identify a repeatable buyer but you still lack first-customer motion.
- You can build it but have not proven demand -> `references/lean-startup.md` (Build-Measure-Learn, smallest MVP that tests the riskiest assumption).
- You cannot describe who the product is for, or prospects say "interesting" but do not act -> `references/obviously-awesome.md` (positioning and category choice).
- You are entering a crowded market and need a wedge -> `references/crossing-the-chasm.md` (beachhead). Follow with `references/blue-ocean-strategy.md` only when no beachhead can produce a defensible category position.
- People want it but balk at the price, or you are guessing the number -> `references/monetizing-innovation.md` (price before you build, willingness-to-pay).
- The offer itself feels weak -> `references/100m-offers.md` (stack value so the price feels trivial).
- Traffic is fine but no leads -> `references/100m-leads.md` (lead generation), and re-check messaging.
- The words on the page fall flat -> `references/storybrand.md` (make the customer the hero). Follow with `references/made-to-stick.md` only when the message is clear but not remembered or repeated.
- Leads stall in the pipeline, or you lose at the close -> `references/spin-selling.md` (situation, problem, implication, need-payoff). Follow with `references/influence.md` only when discovery is sound but decision dynamics still block action.
- You picked product-market fit but have no growth channel -> `references/traction.md` (test 19 channels, find the one that works).

## Process (progressive disclosure)

1. Name the symptom in one concrete sentence with a number ("20 trials, 1 paid").
   A vague symptom cannot be routed.
2. Walk the decision tree to the earliest broken stage. Weak close is often weak
   positioning; low conversion is often the wrong audience. Stop at the root, not
   the symptom.
3. Read ONLY the primary reference the tree points to first. Each one is
   self-contained.
4. Apply that reference's scored checklist. If the checklist passes and the route
   names a conditional follow-up, load that follow-up next. If no follow-up is
   named or the follow-up also passes, re-diagnose: the funnel breaks in more
   than one place at once.

## Self-assessment: is the router the right entry point?

Score each yes (2 pts for the first two, 1 pt each for the rest):

- [ ] I can state my symptom in one concrete sentence with a number. (2)
- [ ] I have NOT already named the framework I need. (2)
- [ ] My problem touches more than one funnel stage, or I am unsure which. (1)
- [ ] I have customer or revenue data to walk upstream against. (1)
- [ ] I am at discovery, not mid-execution on a chosen plan. (1)
- [ ] I am willing to be routed away from the fix I assumed I needed. (1)

Total 8. Pass threshold 4. Below 4, you likely already know your stage: skip the
router and read the named reference. At or above 4, walk the decision tree.

## Honest limitations

- Garbage in, garbage out. A symptom stated as "we need to grow" routes nowhere
  useful; the method needs a concrete, numeric symptom.
- Single-bottleneck bias. The funnel model assumes one dominant broken stage; real
  businesses often break in two places at once. Re-diagnose after each fix.
- Founder-context bias. The source books target early-stage software founders. A
  regulated, hardware, or enterprise business will find some routes mis-weighted.
- This router points; it does not execute. Each reference carries its own caveats.

## Verification

You used this skill correctly when:

- The symptom was stated in one concrete sentence with a number before routing.
- Exactly one reference was read first (the earliest broken funnel stage), not all 14.
- That reference's scored checklist was applied and produced a pass/fail with a number.
- A falsifiable success metric was set, so the founder knows when to stop or re-diagnose.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Reading all 14 references up front | Defeats progressive disclosure; burns context | Route to one, read it, act |
| Routing a vague symptom ("we need to grow") | The method needs a concrete numeric symptom | Force a one-sentence symptom with a number first |
| Fixing the symptom stage, not the root | Weak close is often weak positioning | Walk upstream to the earliest broken stage |
| Treating a framework as truth | Each book has honest limitations and conflicts | Read the reference's limitations and conflicts sections |

## References

Fourteen books, one file each, all under `references/`:

- `references/mom-test.md` - The Mom Test (Fitzpatrick): customer interviews.
- `references/four-steps.md` - The Four Steps to the Epiphany (Blank): first customers.
- `references/lean-startup.md` - The Lean Startup (Ries): Build-Measure-Learn, MVPs.
- `references/obviously-awesome.md` - Obviously Awesome (Dunford): positioning.
- `references/crossing-the-chasm.md` - Crossing the Chasm (Moore): tech adoption.
- `references/blue-ocean-strategy.md` - Blue Ocean Strategy (Kim/Mauborgne): category creation.
- `references/monetizing-innovation.md` - Monetizing Innovation (Ramanujam/Tacke): pricing.
- `references/100m-offers.md` - $100M Offers (Hormozi): offer design.
- `references/100m-leads.md` - $100M Leads (Hormozi): lead generation.
- `references/spin-selling.md` - SPIN Selling (Rackham): B2B sales.
- `references/influence.md` - Influence (Cialdini): persuasion principles.
- `references/traction.md` - Traction (Weinberg/Mares): growth channels.
- `references/storybrand.md` - Building a StoryBrand (Miller): brand messaging.
- `references/made-to-stick.md` - Made to Stick (Heath/Heath): message memorability.

Pattern credit: the books-to-skills structure (decision trees, scored checklists,
honest limitations, cross-book conflict resolution) follows the MIT-licensed
[Founder Playbook](https://github.com/getagentseal/founder-playbook). The
distillations here are original. The `npx ai-agents init --pack business` installer
flag is tracked separately (CLI milestone, not in this skill).
