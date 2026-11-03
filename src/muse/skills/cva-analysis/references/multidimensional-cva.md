---
source: wiki/concepts/Design Principles/Commonality Variability Analysis.md
created: 2026-04-11
review-by: 2026-07-11
---

# Multidimensional CVA

When a problem has multiple independent axes of variability, a single CVA matrix
is insufficient. Each axis gets its own matrix or dimension.

## When to Use

- Two or more independent variation dimensions (e.g., geography AND product type)
- Rows from one matrix do not cleanly map to rows in another
- Combining all variations into one matrix produces sparse cells (many N/A entries)

## Process

1. Build a CVA matrix for the first axis (e.g., geography: US, Canada, Germany)
2. Build a separate matrix for the second axis (e.g., product: physical, digital, subscription)
3. Identify cross-cutting concerns that appear in both matrices
4. For each cross-cutting concern, determine if the variation is:
   - **Independent**: varies by axis 1 only, axis 2 only, or neither
   - **Correlated**: varies by both axes together (needs a composite strategy)

## Pattern Implications

| Matrix Relationship | Pattern |
|---|---|
| Independent axes | Two separate Strategy hierarchies |
| Correlated axes | Bridge pattern (one axis delegates to the other) |
| Sparse combinations | Abstract Factory constrains valid pairs |

## Example: Shipping Calculator

Axis 1 (geography): US, Canada, EU
Axis 2 (carrier): USPS, FedEx, DHL

```
Geography Matrix:
| Concept        | US          | Canada      | EU          |
|----------------|-------------|-------------|-------------|
| Tax rules      | State/local | GST+PST     | VAT         |
| Address format | US postal   | Canadian    | EU postal   |
| Currency       | USD         | CAD         | EUR         |

Carrier Matrix:
| Concept        | USPS        | FedEx       | DHL         |
|----------------|-------------|-------------|-------------|
| Rate API       | USPS REST   | FedEx SOAP  | DHL XML     |
| Tracking       | USPS track  | FedEx track | DHL track   |
| Weight limits  | 70 lbs      | 150 lbs     | 40 kg       |
```

Tax rules vary by geography only (independent). Rate API varies by carrier only
(independent). But shipping cost varies by BOTH geography and carrier (correlated),
requiring a Bridge: GeographyStrategy delegates to CarrierStrategy for rate
calculation, applying geography-specific tax rules to carrier-specific rates.

## Danger Signs

- Matrix has more than 30% empty cells: you may be forcing unrelated concerns
  into one dimension. Split into separate matrices.
- A row appears in both matrices with different meanings: the abstraction is
  not well-defined. Rename to clarify the distinction.
- All cells in a row are identical: that row is not a variability. Remove it
  from the matrix and make it a constant in the base class.
