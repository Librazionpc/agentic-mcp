from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from agentic_mcp_shared.auth import CallerContext
from agentic_mcp_shared.errors import ToolError
from agentic_mcp_shared.server_base import ToolSpec, create_app, run_app


@dataclass(frozen=True)
class RagConfig:
    persist_dir: str
    collection: str
    embedding_model: str
    default_visibility: str
    chroma_host: str
    chroma_port: int
    chroma_ssl: bool


def _rag_config() -> RagConfig:
    persist_dir = os.environ.get("RAG_CHROMA_PERSIST_DIR", "/data/chroma").strip() or "/data/chroma"
    collection = os.environ.get("RAG_CHROMA_COLLECTION", "agentic_rag").strip() or "agentic_rag"
    embedding_model = os.environ.get("RAG_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2").strip()
    default_visibility = os.environ.get("RAG_DEFAULT_VISIBILITY", "public").strip() or "public"
    chroma_host = os.environ.get("RAG_CHROMA_HOST", "").strip()
    chroma_port = int(os.environ.get("RAG_CHROMA_PORT", "8000"))
    chroma_ssl = os.environ.get("RAG_CHROMA_SSL", "false").strip().lower() in {"1", "true", "yes"}
    return RagConfig(
        persist_dir=persist_dir,
        collection=collection,
        embedding_model=embedding_model,
        default_visibility=default_visibility,
        chroma_host=chroma_host,
        chroma_port=chroma_port,
        chroma_ssl=chroma_ssl,
    )


def _visibility_for_caller(caller: CallerContext) -> str:
    # Default: public. Internal is allowed for compliance/fraud roles (skills permissions).
    if {"compliance.read", "fraud.read"} & caller.scopes:
        return "internal_plus_public"
    return "public"


def _where_clause(visibility: str, sources: list[str] | None) -> dict[str, Any] | None:
    if visibility == "internal_plus_public":
        vis_clause: dict[str, Any] = {"visibility": {"$in": ["public", "internal"]}}
    else:
        vis_clause = {"visibility": visibility}

    clauses: list[dict[str, Any]] = [vis_clause]
    if sources:
        clauses.append({"source_id": {"$in": sources}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _collection(cfg: RagConfig):
    if cfg.chroma_host:
        client = chromadb.HttpClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    else:
        client = chromadb.PersistentClient(path=cfg.persist_dir)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=cfg.embedding_model)
    return client.get_or_create_collection(name=cfg.collection, embedding_function=ef)


def _format_results(res: dict, top_k: int) -> dict:
    ids = (res.get("ids") or [[]])[0] or []
    docs = (res.get("documents") or [[]])[0] or []
    metas = (res.get("metadatas") or [[]])[0] or []

    results: list[dict[str, Any]] = []
    for cid, doc, meta in list(zip(ids, docs, metas))[:top_k]:
        meta = meta or {}
        source_id = str(meta.get("source_id", "")).strip() or "unknown"
        path = str(meta.get("path", "")).strip() or "unknown"
        title = f"{source_id}:{path}"
        snippet = (doc or "").strip()
        if len(snippet) > 800:
            snippet = snippet[:800].rstrip() + "…"
        results.append({"id": str(cid), "title": title, "snippet": snippet, "source": source_id, "path": path})
    return {"results": results}


async def _rag_search(caller: CallerContext, args: dict, request_id: str) -> dict:
    # Support multiple contract shapes (rag_search, faq_lookup, policy_retrieval, etc.)
    query = str(args.get("query", "")).strip() or str(args.get("question", "")).strip()
    if not query:
        raise ToolError("INVALID_INPUT", "query is required.")
    top_k = int(args.get("top_k", 5))
    if top_k < 1 or top_k > 20:
        raise ToolError("INVALID_INPUT", "top_k must be between 1 and 20.")

    sources = args.get("sources")
    if sources is not None and not isinstance(sources, list):
        raise ToolError("INVALID_INPUT", "sources must be an array of strings.")
    sources_list = [str(s).strip() for s in (sources or []) if str(s).strip()] or None

    cfg = _rag_config()
    visibility = _visibility_for_caller(caller)
    where = _where_clause(visibility, sources_list)

    try:
        collection = _collection(cfg)
        res = collection.query(query_texts=[query], n_results=top_k, where=where)
    except Exception as e:
        raise ToolError("UPSTREAM_UNAVAILABLE", "RAG index unavailable or not initialized.") from e

    return _format_results(res, top_k)


async def _faq_lookup(caller: CallerContext, args: dict, request_id: str) -> dict:
    faq_id = str(args.get("id", "")).strip()
    if not faq_id:
        raise ToolError("INVALID_INPUT", "id is required.")
    res = await _rag_search(caller, {"query": faq_id, "top_k": 1}, request_id)
    results = res.get("results") or []
    if not results:
        raise ToolError("NOT_FOUND", "FAQ entry not found.")
    r0 = results[0]
    return {"id": faq_id, "title": r0.get("title", ""), "answer": r0.get("snippet", ""), "source": r0.get("source", "")}


async def _policy_retrieval(caller: CallerContext, args: dict, request_id: str) -> dict:
    policy_id = str(args.get("policy_id", "")).strip()
    if not policy_id:
        raise ToolError("INVALID_INPUT", "policy_id is required.")
    res = await _rag_search(caller, {"query": policy_id, "top_k": 1}, request_id)
    results = res.get("results") or []
    if not results:
        raise ToolError("NOT_FOUND", "Policy not found.")
    r0 = results[0]
    return {"policy_id": policy_id, "content": r0.get("snippet", ""), "source": r0.get("source", "")}


async def _knowledge_base_query(caller: CallerContext, args: dict, request_id: str) -> dict:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("INVALID_INPUT", "query is required.")
    top_k = int(args.get("top_k", 5))
    res = await _rag_search(caller, {"query": query, "top_k": top_k}, request_id)
    out = []
    for r in res.get("results") or []:
        out.append({"id": r.get("id", ""), "title": r.get("title", ""), "snippet": r.get("snippet", ""), "source": r.get("source", "")})
    return {"results": out}


def main() -> None:
    tools = [
        ToolSpec(name="rag_search", required_scopes={"kb.read"}, handler=_rag_search),
        ToolSpec(name="knowledge_search", required_scopes={"kb.read"}, handler=_rag_search),
        ToolSpec(name="knowledge_base_query", required_scopes={"kb.read"}, handler=_knowledge_base_query),
        ToolSpec(name="sop_search", required_scopes={"kb.read"}, handler=_rag_search),
        ToolSpec(name="faq_lookup", required_scopes={"kb.read"}, handler=_faq_lookup),
        ToolSpec(name="policy_retrieval", required_scopes={"kb.read"}, handler=_policy_retrieval),
    ]
    app = create_app("rag-mcp", tools)
    host = os.environ.get("RAG_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("RAG_MCP_PORT", "8098"))
    run_app(app, host, port)


if __name__ == "__main__":
    main()
