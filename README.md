# agentic-mcp (Tool Servers)

This repo contains **domain MCP tool servers**. Each server:

- Owns one domain (payments, ticketing, CRM, KYC, fraud, RAG, escalation, notifications)
- Exposes **HTTP** tool endpoints (production) and logs to stderr
- Validates tool inputs/outputs against `agentic-skills/contracts/tools/*.json`
- Authenticates runtime→MCP using **JWT (RS256)** (`customer_id`, `iss`, `aud`, `exp`, `scopes`)
- Calls backend services using **API keys** (`X-API-Key`) from `.env`
- Redacts/masks sensitive values before returning to the runtime

## Quick start (local)

1) Copy env template:

- `cp .env.example .env`

2) Start servers:

- `docker compose up --build`

3) Health checks:

- `curl -s http://localhost:8091/health | jq`
- `curl -s http://localhost:8097/health | jq`

## HTTP API (common across servers)

- `GET /health` → `{ "status": "ok" }`
- `GET /tools` (auth required) → `{ "tools": ["tool_a", "tool_b"] }`
- `POST /tools/call` (auth required) → `{ "ok": true, "result": {...} }` or `{ "ok": false, "error": { "code": "...", "message": "..." } }`

### Auth

Runtime calls MCP with:

- `Authorization: Bearer <jwt>`
- `X-Request-Id: <uuid>` (recommended)

JWT requirements:

- `customer_id` claim is required
- `iss` must match `MCP_JWT_ISS`
- `aud` must match `MCP_JWT_AUD`
- `exp` must be valid (short TTL recommended)
- `scopes` must include required scope for the tool (if configured)

## Where tool contracts live

Contracts are defined in the **skills repo**:

- `../agentic-skills/contracts/tools/*.json`
- `../agentic-skills/contracts/errors.yaml`

## Notes

- “Friendly” user messaging is done in **OpenClaw runtime + skills templates**, not inside MCP responses.
- For transaction screenshots: only **signed URLs** are accepted (see env in `.env.example`).

