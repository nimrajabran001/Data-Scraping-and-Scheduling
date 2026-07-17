import os
from dotenv import load_dotenv

load_dotenv()

# ----------------------------
# Weaviate
# ----------------------------
WEAVIATE_URL = os.getenv(
    "WEAVIATE_URL",
    "http://localhost:8080"
)

CLASS_NAME = "Judgment"

# ----------------------------
# Embedding
# ----------------------------
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2"
)

# ----------------------------
# Chunking
# ----------------------------
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

# ----------------------------
# Storage
# ----------------------------
PDF_FOLDER = "data/pdfs"
MARKDOWN_FOLDER = "data/markdown"

os.makedirs(PDF_FOLDER, exist_ok=True)
os.makedirs(MARKDOWN_FOLDER, exist_ok=True)

# ----------------------------
# Logging
# ----------------------------
LOG_LEVEL = "INFO"

OLLAMA_URL = "http://localhost:11434"

LLM_MODEL = "phi3:mini"

TOP_K = 5