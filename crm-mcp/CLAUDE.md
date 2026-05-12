CRM MCP server:
- Tool I/O must validate against contracts.
- Only sanitized fields returned; redact phone/email if accidentally included.
- customer_id comes from JWT claim `customer_id`.

