from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from rag_api.pipeline import run_ingestion
from rag_api.weaviate_db import init_schema
from rag_api.chat import ask

from rag_api.hybrid_search import hybrid_search, keyword_search
from rag_api.semantic_search import semantic_search
from rag_api.search_tool import search_judgments
from rag_api.query_classifier import classify_query
from rag_api.search_tool import _make_similarity_fn


# -------------------------------------------------
# Startup
# -------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize resources on startup.
    """

    try:
        init_schema()
        print("✓ Weaviate schema initialized")

    except Exception as e:
        print("Schema initialization failed:", e)

    yield


app = FastAPI(
    title="PHC Judgment RAG API",
    description="Incremental ingestion + grounded RAG chat + multi-strategy search (Stage 4)",
    version="4.0.0",
    lifespan=lifespan
)


# -------------------------------------------------
# Request Models
# -------------------------------------------------

class IngestRequest(BaseModel):
    json_path: str


class ChatRequest(BaseModel):
    question: str
    top_k: int = 5


class SearchRequest(BaseModel):
    query: str
    strategy: str = "hybrid"   # 'keyword' | 'semantic' | 'hybrid'
    top_k: int = 5
    court: Optional[str] = None
    year: Optional[int] = None
    judge: Optional[str] = None


class ClassifyRequest(BaseModel):
    query: str


# -------------------------------------------------
# Home
# -------------------------------------------------

@app.get("/")
async def home():

    return {
        "service": "PHC Judgment RAG API",
        "version": "4.0.0",
        "status": "running",
        "endpoints": [
            "/health",
            "/ingest",
            "/chat",
            "/search",
            "/keyword",
            "/semantic",
            "/hybrid",
            "/classify",
        ]
    }


# -------------------------------------------------
# Health
# -------------------------------------------------

@app.get("/health")
async def health():

    return {
        "status": "healthy"
    }


# -------------------------------------------------
# Ingestion Endpoint
# -------------------------------------------------

@app.post("/ingest")
async def ingest(request: IngestRequest):

    try:

        result = run_ingestion(request.json_path)

        return {
            "status": "success",
            "summary": result
        }

    except FileNotFoundError:

        raise HTTPException(
            status_code=404,
            detail="JSON file not found."
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# -------------------------------------------------
# Chat Endpoint (grounded RAG answer, no tool-calling)
# -------------------------------------------------

@app.post("/chat")
async def chat(request: ChatRequest):

    try:

        result = ask(
            question=request.question,
            top_k=request.top_k
        )

        return result

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# -------------------------------------------------
# Unified search tool endpoint (Section 5.1 contract)
#
# This is the same function the LLM tool-calling layer
# (rag_api/llm_tools.py) invokes. Exposed directly as an HTTP endpoint
# too, so the strategy comparison in Section 6/7 and any external caller
# can hit one contract without going through the chat LLM.
# -------------------------------------------------

@app.post("/search")
async def search(request: SearchRequest):

    try:

        result = search_judgments(
            query=request.query,
            strategy=request.strategy,
            top_k=request.top_k,
            court=request.court,
            year=request.year,
            judge=request.judge,
        )

        return result

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# -------------------------------------------------
# Individual strategy endpoints (Section 3 — each must be
# independently invokable for head-to-head comparison)
# -------------------------------------------------

@app.get("/keyword")
async def keyword(query: str, top_k: int = 5, court: str = None, year: int = None, judge: str = None):

    try:

        results = keyword_search(query, limit=top_k, court=court, year=year, judge=judge)

        return {"query": query, "strategy": "keyword", "results": results}

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/semantic")
async def semantic(query: str, top_k: int = 5, court: str = None, year: int = None, judge: str = None):

    try:

        results = semantic_search(query, limit=top_k, court=court, year=year, judge=judge)

        return {"query": query, "strategy": "semantic", "results": results}

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/hybrid")
async def hybrid(query: str, top_k: int = 5, court: str = None, year: int = None, judge: str = None):

    try:

        results = hybrid_search(query, limit=top_k, court=court, year=year, judge=judge)

        return {
            "query": query,
            "strategy": "hybrid",
            "results": results
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# -------------------------------------------------
# Classifier introspection endpoint (useful for debugging
# the Section 4/8 relevance classifier and its threshold tuning)
# -------------------------------------------------

@app.post("/classify")
async def classify(request: ClassifyRequest):

    try:

        result = classify_query(
            request.query,
            embedding_similarity_fn=_make_similarity_fn(),
        )

        return {"query": request.query, **result}

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )