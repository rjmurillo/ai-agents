# Monetizing Innovation

Distilled from Madhavan Ramanujam and Georg Tacke, Monetizing Innovation. The central claim: most new products fail not because the product is bad but because pricing was an afterthought. The fix is to have the price conversation with customers before you commit engineering, then design the product, packaging, and business case around what people will actually pay.

## When to use

Use when you are deciding what to charge, how to package, or whether a feature set will sell at a viable price, ideally before the product is locked. Decision cue: if you cannot state a target price and the evidence behind it, you are not ready to build.

## Decision tree

- If you have not asked customers about willingness-to-pay (WTP) yet, then stop feature work and run WTP interviews first. Everything below depends on that data.
- If WTP is wildly different across customers, then segment by value and build tiered packages, not one product for everyone.
- If most customers want a feature but few will pay extra for it, then it is a base feature, not a premium differentiator. Do not gate it.
- If a small group will pay a large premium for one capability, then carve it into a separate tier or add-on (the "leader" feature).
- If you have a great product but no clear monetization model, then choose the pricing model (subscription, usage, tiered, freemium, outcome-based) before launch, not after.
- If sales keeps discounting to close, then the problem is value communication or segmentation, not the list price. Fix packaging first.
- If you only need to decide whether to build or buy a capability, then this is the wrong skill (use buy-vs-build-framework).

## Core framework

1. Have the WTP conversation early. Interview real target customers about value and price before the product is finished. Treat price as a design input, not a launch-day decision.
2. Segment by willingness-to-pay, not by demographics. Group customers by what they value and will pay for. Different segments justify different packages.
3. Design product configuration and bundling to match segments. Sort features into leaders (drive the purchase, worth a premium), fillers (nice to have, low pull), and killers (erode WTP when bundled in). Keep leaders, place fillers carefully, drop or isolate killers.
4. Choose the pricing model and price metric. Decide how you charge (per seat, per usage, flat subscription, freemium, outcome-based) so the metric scales with the value the customer receives.
5. Set the price level from the WTP evidence and build the business case around it. Pressure-test the price with customers, then back-cast required volume and cost. If the numbers do not work at a price customers accept, change the product, not just the spreadsheet.

## Scored checklist

Score each yes as the listed points. Total is 10. Pass at 7 or higher.

- (2) You interviewed at least a handful of target customers about price and value before finalizing the product.
- (2) You can name at least two WTP-based segments and the price each will bear.
- (2) Every feature is classified as leader, filler, or killer, and killers are removed or isolated.
- (1) Your price metric scales with the value the customer gets, not just your cost.
- (1) You have a defined pricing model (subscription, usage, tiered, freemium, outcome) chosen on purpose.
- (1) The business case closes at a price customers said they would pay, without assuming heroic discounts.
- (1) You have a plan to communicate value so the sales team does not default to discounting.

Below 7: go back to WTP interviews and segmentation before launch.

## Honest limitations

- Stated WTP is not revealed WTP. Interview answers overstate what people pay in reality. Treat them as directional and confirm with pilots, pre-orders, or live tests.
- The method assumes you can reach and interview target customers early. For deep-tech or category-creating products where customers cannot yet imagine the value, early WTP signal is noisy.
- It is strongest for B2B and considered purchases. For low-price, high-volume, impulse-driven consumer goods, behavioral and channel dynamics dominate over interview-based WTP.
- Teams misapply it as a one-time pricing study. Pricing is continuous. WTP shifts as competitors, substitutes, and the market move.
- It says little about price changes over time, dynamic pricing, or negotiation tactics at the deal level.

## Conflicts with other frameworks

- A lean or MVP-first framework pushes you to ship the smallest thing fast and learn from usage. This skill pushes a pricing conversation before build. Resolve by situation: keep the build small, but run the WTP interview in the same early loop. Do not let "ship first, price later" defer pricing past launch, which is the failure this book targets.
- A jobs-to-be-done or pure customer-discovery framework optimizes for the job and value, sometimes implying price follows naturally. This skill insists price is an explicit design input. Resolve by sequencing: use JTBD to find the valued outcome, then immediately attach the WTP question to that outcome rather than assuming value converts to revenue.

## Example

A two-founder team builds an analytics tool. They plan four tiers and assume $50 per seat per month. Before locking the roadmap, they interview 12 target buyers about value and price.

Findings: dashboards are a base expectation (filler, no premium). Automated anomaly alerts are the leader; ops teams will pay a clear premium for them. A heavy data-export module they were proud of is a killer; enterprise buyers see it as a security risk and it lowers their WTP when bundled in.

Action: they collapse to two tiers. Base at $40 per seat includes dashboards. Pro at $90 per seat adds anomaly alerts and is metered partly on monitored data volume, so price scales with value. Data export becomes an opt-in add-on, not a default. The business case now closes at prices buyers stated, the sales team leads with the alert value instead of discounting, and the team avoids shipping the export feature into the base package where it would have suppressed revenue.

Checklist score: WTP interviews done (2), two segments named (2), features classified and killer isolated (2), metric scales with value (1), model chosen (1), case closes at stated price (1), value-communication plan (1). Total 10, pass.
