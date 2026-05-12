This server is production-oriented:

- HTTP endpoints only (`/tools/call`).
- JWT RS256 auth required on tool endpoints.
- Tool request/response validation uses the contracts in `agentic-skills/contracts/tools/`.
- Stable error codes must match `agentic-skills/contracts/errors.yaml`.
- Never add refund/reversal execution endpoints here; keep money movement approval-only.

