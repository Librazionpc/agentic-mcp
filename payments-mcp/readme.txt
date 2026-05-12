# payments-mcp

Production tool server for the **payments/transactions** domain.

## What it does
- Validates tool calls against `agentic-skills/contracts/tools/*.json`
- Authenticates runtime→MCP using RS256 JWT (customer_id, iss, aud, exp, scopes)
- Proxies read-only requests to your payments backend (API key auth)
- Redacts sensitive values in responses

## Tools
See `tool_routes.yaml` for the list of tools exposed by this server.

## Backend wiring
Set these env vars:
- `PAYMENTS_BASE_URL`
- `PAYMENTS_API_KEY`
- `PAYMENTS_TIMEOUT_SECONDS`

Backend auth header used:
- `X-API-Key: <PAYMENTS_API_KEY>`

## Security
- No direct money movement tools live here (refund/reversal execution is NOT exposed).
- Any approval requests must remain approval-only (HITL enforced in runtime).

