FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY agentic-mcp/agentic_mcp_shared ./agentic_mcp_shared
COPY agentic-mcp/rag-mcp ./rag-mcp
COPY agentic-skills/contracts ./agentic-skills/contracts

RUN pip install --no-cache-dir -r rag-mcp/requirements.txt

RUN useradd -m -u 1000 mcpuser && chown -R mcpuser:mcpuser /app
USER mcpuser

EXPOSE 8098
CMD ["python", "rag-mcp/rag_mcp_server.py"]

