FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY agentic-mcp/agentic_mcp_shared ./agentic_mcp_shared
COPY agentic-mcp/collections-mcp ./collections-mcp
COPY agentic-skills/contracts ./agentic-skills/contracts

RUN pip install --no-cache-dir -r collections-mcp/requirements.txt

RUN useradd -m -u 1000 mcpuser && chown -R mcpuser:mcpuser /app
USER mcpuser

EXPOSE 8100
CMD ["python", "collections-mcp/collections_mcp_server.py"]

