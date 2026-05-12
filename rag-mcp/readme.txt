# rag-mcp

Domain MCP server for RAG retrieval (ChromaDB).

## Storage
Mount the Chroma persist directory to `/data/chroma` (see `docker-compose.yml`).

## Env
- `RAG_CHROMA_PERSIST_DIR`
- `RAG_CHROMA_COLLECTION`
- `RAG_EMBEDDING_MODEL`
- `RAG_DEFAULT_VISIBILITY` (public|internal)

## Visibility enforcement
- Callers without scope `rag.internal` only get `visibility=public`.
- Callers with `rag.internal` may query internal content too.

