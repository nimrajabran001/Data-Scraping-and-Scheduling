from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from rag_api.pipeline import run_ingestion
from rag_api.weaviate_db import init_schema
from rag_api.chat import ask


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
    description="Incremental ingestion + grounded RAG chat",
    version="2.0.0",
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


# -------------------------------------------------
# Home
# -------------------------------------------------

@app.get("/")
async def home():

    return {
        "service": "PHC Judgment RAG API",
        "version": "2.0.0",
        "status": "running",
        "endpoints": [
            "/health",
            "/ingest",
            "/chat"
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
# Chat Endpoint
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