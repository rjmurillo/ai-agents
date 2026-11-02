# API Reference

## Overview

[One paragraph describing what the API exposes, the protocol (REST, gRPC, GraphQL), and the base URL. Link to the OpenAPI or schema file if one exists.]

Base URL: `[https://api.example.com/v1]`

## Authentication

| Method | Header | Notes |
|--------|--------|-------|
| API key | `Authorization: Bearer [token]` | [How tokens are issued and rotated] |
| OAuth | `Authorization: Bearer [access_token]` | [Scopes and refresh] |

[Describe how a caller obtains and rotates credentials. Never include real keys in this document.]

## Conventions

- **Versioning**: Major version in the path (`/v1`). Breaking changes go to `/v2`. See [versioning policy].
- **Content type**: `application/json; charset=utf-8` for both request and response unless noted.
- **Status codes**: Standard HTTP semantics. `2xx` success, `4xx` client error, `5xx` server error.
- **Time**: ISO 8601 in UTC. Example: `2026-04-27T12:00:00Z`.
- **Pagination**: Cursor-based via `next_cursor` in the response and `cursor` query parameter on the next call.

## Endpoints

### `[GET /resources]`

[Short description of what this endpoint returns and when to use it.]

- **Auth**: Required. [Scope or role.]
- **Rate limit**: [Tier and per-window limit.]

#### Query parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `cursor` | string | No | Pagination cursor from a previous response |
| `limit` | integer | No | Max items per page (1-100, default 20) |

#### Response 200

```json
{
  "items": [
    {
      "id": "[id]",
      "name": "[name]",
      "created_at": "2026-04-27T12:00:00Z"
    }
  ],
  "next_cursor": "[opaque-cursor]"
}
```

#### Error responses

| Status | Code | Meaning |
|--------|------|---------|
| 401 | `unauthorized` | Missing or invalid credentials |
| 429 | `rate_limited` | Caller exceeded rate limit; retry after the `Retry-After` header |

---

### `[POST /resources]`

[Short description.]

- **Auth**: Required.
- **Idempotency**: Send `Idempotency-Key` header to make retries safe.

#### Request body

```json
{
  "name": "[name]",
  "tags": ["[tag-one]", "[tag-two]"]
}
```

#### Response 201

```json
{
  "id": "[id]",
  "name": "[name]",
  "tags": ["[tag-one]", "[tag-two]"],
  "created_at": "2026-04-27T12:00:00Z"
}
```

#### Error codes

| Status | Code | Meaning |
|--------|------|---------|
| 400 | `validation_error` | Body failed validation; see `errors` array |
| 409 | `conflict` | Resource with the same identity exists |

## Error Format

All error responses share this shape:

```json
{
  "error": {
    "code": "[machine-readable-code]",
    "message": "[human-readable summary]",
    "request_id": "[opaque-id-for-support]"
  }
}
```

## Rate Limits

| Tier | Requests per minute | Burst |
|------|---------------------|-------|
| Free | 60 | 100 |
| Pro | 600 | 1000 |

Clients should respect the `X-RateLimit-Remaining` and `Retry-After` headers.

## Examples

### curl

```bash
curl -sS https://api.example.com/v1/resources \
  -H "Authorization: Bearer $API_TOKEN"
```

### Python (httpx)

```python
import httpx

api_token = "[token]"

response = httpx.get(
    "https://api.example.com/v1/resources",
    headers={"Authorization": f"Bearer {api_token}"},
    timeout=10.0,
)
response.raise_for_status()
print(response.json())
```

## Changelog

| Date | Version | Change |
|------|---------|--------|
| `[YYYY-MM-DD]` | `v1.0.0` | Initial release |
