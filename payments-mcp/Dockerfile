FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Copy shared code + contracts + this server
COPY agentic-mcp/agentic_mcp_shared ./agentic_mcp_shared
COPY agentic-mcp/payments-mcp ./payments-mcp
COPY agentic-skills/contracts ./agentic-skills/contracts

RUN pip install --no-cache-dir -r payments-mcp/requirements.txt

RUN useradd -m -u 1000 mcpuser && chown -R mcpuser:mcpuser /app
USER mcpuser

EXPOSE 8091
CMD ["python", "payments-mcp/payments_mcp_server.py"]
