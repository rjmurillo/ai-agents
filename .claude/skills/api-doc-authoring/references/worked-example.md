# Worked Example: Place an Order

This page is the "after" form of an endpoint inventory. The skill's tests run
every `http` block below against a local fixture API, so the page is a live
example of the format and a regression fixture for `api_examples.py`.

The "before" form, an alphabetical endpoint list, is kept in the table below
only to show what changed. It is not an executable example.

| Before (inventory) | Why it fails a tired developer |
|--------------------|--------------------------------|
| `GET /orders/{id}` | No hint that you create an order first |
| `POST /orders` | Request fields listed alphabetically, no working call |
| `PUT /orders/{id}/status` | Status values appear nowhere near the goal |

## Place an order and check it

Goal: create an order for one SKU and read it back.

### Step 1: Create the order

Send the two required fields, `sku` and `qty`.

```http example=create-order expect=201
POST /orders
Content-Type: application/json

{"sku": "A-1", "qty": 2}
```

Expected response: the order starts as `pending`.

```json response=create-order
{"id": "<id>", "status": "pending"}
```

### Step 2: Read the order back

Use the `id` from step 1. The fixture assigns `ord_1` to the first order.

```http example=get-order expect=200
GET /orders/ord_1
```

```json response=get-order
{"id": "ord_1", "status": "pending", "qty": 2}
```

### If something goes wrong

| Status | Cause | Action |
|--------|-------|--------|
| 422 `invalid_quantity` | `qty` is zero or negative | Send a `qty` of 1 or more |
| 404 `order_not_found` | The `id` was never issued by this API | Create the order first, then reuse the returned `id` |
| 500 | Unknown | Unknown |

The 500 row says `Unknown` on purpose: the contract names no cause or fix, so
the page invents none.

```http example=reject-zero-quantity expect=422
POST /orders
Content-Type: application/json

{"sku": "A-1", "qty": 0}
```

```json response=reject-zero-quantity
{"error": "invalid_quantity"}
```

```http example=missing-order expect=404
GET /orders/ord_999
```

```json response=missing-order
{"error": "order_not_found"}
```

## Reference

Exhaustive field lists belong after the working path, not before it.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `sku` | string | yes | Catalog identifier |
| `qty` | integer | yes | 1 or more |
