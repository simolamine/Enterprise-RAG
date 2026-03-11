# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
Documentation Inquiry Chatbot — Document Registry Microservice

Provides a REST catalog of all ingested documents so the admin UI can:
  - List all documents  (GET  /v1/doc_registry)
  - Get one document    (GET  /v1/doc_registry/{doc_id})
  - Register a document (POST /v1/doc_registry/register)
  - Delete a document   (DELETE /v1/doc_registry/{doc_id})

Also exposes:
  - POST /v1/feedback   — for users to submit query feedback (👍/👎)
  - GET  /v1/health     — liveness probe
"""

import os
import time
import json

import redis as redis_client
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from comps.cores.mega.logger import change_opea_logger_level, get_opea_logger
from comps.doc_registry.utils.opea_doc_registry import OPEADocRegistry

# ── Bootstrap ─────────────────────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), "impl/microservice/.env"))

logger = get_opea_logger("doc_registry_microservice")
change_opea_logger_level(logger, log_level=os.getenv("OPEA_LOGGER_LEVEL", "INFO"))

REDIS_URL          = os.getenv("DOC_REGISTRY_REDIS_URL", "redis://localhost:6379")
REGISTRY_PREFIX    = os.getenv("DOC_REGISTRY_REDIS_HASH_PREFIX", "docbot:registry:")
FEEDBACK_STREAM    = os.getenv("FEEDBACK_STREAM", "docbot:feedback_log")
HOST               = os.getenv("DOC_REGISTRY_HOST", "0.0.0.0")
PORT               = int(os.getenv("DOC_REGISTRY_PORT", 6200))

registry = OPEADocRegistry(redis_url=REDIS_URL, hash_prefix=REGISTRY_PREFIX)
_redis   = redis_client.from_url(REDIS_URL, decode_responses=True)

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="DocBot — Document Registry",
    description="Catalog of ingested documents and user feedback store for the documentation chatbot.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / response models ─────────────────────────────────────────────────

class RegisterDocRequest(BaseModel):
    doc_id:      str
    filename:    str
    chunk_count: int = 0
    doc_hash:    Optional[str] = None
    doc_title:   Optional[str] = None
    category:    Optional[str] = None
    version:     Optional[str] = None
    department:  Optional[str] = None
    source_url:  Optional[str] = None
    status:      str = "ingested"


class FeedbackRequest(BaseModel):
    query_id:  str                      # any client-generated UUID for the query turn
    rating:    int                       # +1 (helpful) or -1 (not helpful)
    comment:   Optional[str] = None
    query:     Optional[str] = None     # original user query (for analytics)
    doc_ids:   Optional[List[str]] = None  # doc_ids of the sources shown


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/v1/health", tags=["health"])
def health():
    ok = registry.health()
    if not ok:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ok"}


# ── Document Catalog ──────────────────────────────────────────────────────────

@app.get("/v1/doc_registry", tags=["doc_registry"])
def list_documents():
    """Return all registered documents, newest first."""
    return {"documents": registry.list_documents()}


@app.get("/v1/doc_registry/{doc_id}", tags=["doc_registry"])
def get_document(doc_id: str = Path(..., description="Document identifier (SHA-256 first 16 chars of filename)")):
    """Return a single document entry."""
    doc = registry.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return doc


@app.post("/v1/doc_registry/register", status_code=201, tags=["doc_registry"])
def register_document(req: RegisterDocRequest):
    """Register or update a document entry.

    Called automatically by the ingestion microservice after successful embedding storage.
    Can also be called manually for administrative corrections.
    """
    if not req.doc_id:
        raise HTTPException(status_code=400, detail="doc_id is required")
    if not req.filename:
        raise HTTPException(status_code=400, detail="filename is required")

    entry = registry.register(
        doc_id=req.doc_id,
        filename=req.filename,
        chunk_count=req.chunk_count,
        doc_hash=req.doc_hash,
        doc_title=req.doc_title,
        category=req.category,
        version=req.version,
        department=req.department,
        source_url=req.source_url,
        status=req.status,
    )
    return entry


@app.delete("/v1/doc_registry/{doc_id}", tags=["doc_registry"])
def delete_document(doc_id: str = Path(..., description="Document identifier to remove")):
    """Remove a document from the catalog.

    Note: This removes the catalog entry only. To purge the embeddings from the
    vector store, use the vector store admin tooling with filter doc_id={doc_id}.
    """
    success = registry.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return {"deleted": doc_id}


# ── Feedback ──────────────────────────────────────────────────────────────────

@app.post("/v1/feedback", tags=["feedback"])
def submit_feedback(req: FeedbackRequest):
    """Store user feedback for a query response.

    Feedback is pushed to a Redis Stream for async analytics processing.
    rating: +1 = helpful, -1 = not helpful.
    """
    if req.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating must be +1 or -1")

    event = {
        "query_id":  req.query_id,
        "rating":    str(req.rating),
        "comment":   req.comment or "",
        "query":     req.query or "",
        "doc_ids":   json.dumps(req.doc_ids or []),
        "timestamp": str(time.time()),
    }
    try:
        _redis.xadd(FEEDBACK_STREAM, event)
    except Exception as e:
        logger.error(f"Failed to persist feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to store feedback")

    return {"status": "accepted", "query_id": req.query_id}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(f"Starting DocBot Document Registry on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
