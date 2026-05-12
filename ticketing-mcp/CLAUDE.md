Ticketing MCP server rules:
- Validate against `agentic-skills/contracts/tools/*.json`.
- Require JWT RS256 with `customer_id`.
- Use `X-API-Key` to call backend.
- Never echo internal IDs back to the customer; MCP returns masked/sanitized fields only.

