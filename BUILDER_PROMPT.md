# Production MCP Server Builder Prompt (RedTech / OpenClaw)

Use this prompt to generate **production-ready domain MCP servers** for OpenClaw.

## Non-negotiables (production architecture)

1) **Transport**
- Production servers expose **HTTP** endpoints (container-to-container in Docker Compose/K8s).
- Stdio mode may exist for local dev, but production uses HTTP.

2) **Tool I/O**
- Tools must return **JSON** that validates against:
  - `agentic-skills/contracts/tools/<tool>.json` (`response_schema`)
- Inputs must validate against the same contract (`request_schema`).
- Errors must be stable codes from `agentic-skills/contracts/errors.yaml`.

3) **Auth: runtime → MCP**
- Require `Authorization: Bearer <jwt>` on all tool endpoints.
- JWT is **RS256**.
- Required claims:
  - `customer_id` (string)
  - `iss` (must match env)
  - `aud` (must match env)
  - `exp` (must be valid)
  - `scopes` (list of strings), used to enforce tool permissions (defense-in-depth)

4) **Auth: MCP → backend**
- Backend calls use **API key** from env.
- Send backend key as: `X-API-Key: <key>`.
- Keep backend URLs and timeouts in env (`<DOMAIN>_BASE_URL`, `<DOMAIN>_TIMEOUT_SECONDS`).

5) **Audit + redaction**
- Log to stderr: tool name, request_id, customer_id, outcome, latency.
- Never log raw PII.
- Redact/mask sensitive values in responses (PAN/account numbers/internal refs).

6) **Attachments (transaction screenshots)**
- Only accept **signed URLs** (no base64).
- Enforce strict allowlist + size limit + content-type allowlist + timeouts.
- If OCR/txid extraction is not confident, **stop** and return an error (anti prompt-injection).

7) **Security testing / pentest**
- Do not include any “web pentest” capabilities in core fintech MCP servers.
- If you create a separate `security-mcp`, it must:
  - require explicit target allowlist
  - rate limit and timeout every operation
  - include proof-of-ownership banner in README
  - never support internet-wide scanning

## Output structure (exactly)

### SECTION 1: FILES TO CREATE
Create these files exactly once each:

1) `Dockerfile`
2) `requirements.txt`
3) `<server_name>_server.py`
4) `readme.txt`
5) `CLAUDE.md`

### SECTION 2: INSTALLATION INSTRUCTIONS
Provide a single numbered list of commands for:
- building the Docker image
- running it (Docker Compose preferred)
- verifying health and calling a tool endpoint

## Server HTTP API contract (required)

- `GET /health`
- `GET /tools` (auth required)
- `POST /tools/call` (auth required)

`POST /tools/call` request JSON:
```json
{
  "name": "tool_name",
  "arguments": { "any": "json" }
}
```

Response JSON:
```json
{ "ok": true, "result": { } }
```
or
```json
{ "ok": false, "error": { "code": "INVALID_INPUT", "message": "..." } }
```

## Implementation checklist (must satisfy)

- Validate request against tool JSON schema.
- Enforce JWT signature + `iss`/`aud` + `exp`.
- Enforce scopes for the tool (configurable).
- Call backend (HTTP) or local domain engine.
- Mask sensitive values before returning.
- Validate output against tool JSON schema.
- Return only allowed error codes.

