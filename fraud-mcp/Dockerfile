FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY agentic-mcp/agentic_mcp_shared ./agentic_mcp_shared
COPY agentic-mcp/fraud-mcp ./fraud-mcp
COPY agentic-skills/contracts ./agentic-skills/contracts

RUN pip install --no-cache-dir -r fraud-mcp/requirements.txt

RUN useradd -m -u 1000 mcpuser && chown -R mcpuser:mcpuser /app
USER mcpuser

EXPOSE 8095
CMD ["python", "fraud-mcp/fraud_mcp_server.py"]

