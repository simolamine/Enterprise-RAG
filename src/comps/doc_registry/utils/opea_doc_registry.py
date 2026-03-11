# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import json
import time
from typing import List, Optional

import redis

from comps.cores.mega.logger import get_opea_logger

logger = get_opea_logger("doc_registry_microservice")

REGISTRY_PREFIX = "docbot:registry:"
CHUNK_IDX_PREFIX = "docbot:chunks:"


class OPEADocRegistry:
    """
    Redis-backed catalog of ingested documents for the Documentation Chatbot.

    Each document is stored as a Redis Hash under the key:
        docbot:registry:<doc_id>

    Fields stored per document:
        doc_id, doc_hash, doc_title, filename, category, version,
        department, source_url, chunk_count, status, ingested_at, updated_at
    """

    def __init__(self, redis_url: str, hash_prefix: str = REGISTRY_PREFIX):
        self._prefix = hash_prefix
        self._client = redis.from_url(redis_url, decode_responses=True)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _key(self, doc_id: str) -> str:
        return f"{self._prefix}{doc_id}"

    def _all_keys(self) -> List[str]:
        return self._client.keys(f"{self._prefix}*")

    # ── Public API ────────────────────────────────────────────────────────────

    def register(
        self,
        doc_id: str,
        filename: str,
        chunk_count: int,
        doc_hash: Optional[str] = None,
        doc_title: Optional[str] = None,
        category: Optional[str] = None,
        version: Optional[str] = None,
        department: Optional[str] = None,
        source_url: Optional[str] = None,
        status: str = "ingested",
    ) -> dict:
        """Create or update a document entry in the registry.

        If a document with the same doc_id already exists (re-ingestion),
        the entry is updated rather than duplicated.
        """
        now = time.time()
        key = self._key(doc_id)

        existing = self._client.hgetall(key)
        ingested_at = existing.get("ingested_at", str(now))

        entry = {
            "doc_id":      doc_id,
            "doc_hash":    doc_hash or "",
            "doc_title":   doc_title or filename,
            "filename":    filename,
            "category":    category or "",
            "version":     version or "",
            "department":  department or "",
            "source_url":  source_url or "",
            "chunk_count": str(chunk_count),
            "status":      status,
            "ingested_at": ingested_at,
            "updated_at":  str(now),
        }
        self._client.hset(key, mapping=entry)
        logger.info(f"Registered document doc_id={doc_id} filename={filename} chunks={chunk_count}")
        return entry

    def list_documents(self) -> List[dict]:
        """Return all registered documents sorted by ingestion time (newest first)."""
        docs = []
        for key in self._all_keys():
            entry = self._client.hgetall(key)
            if entry:
                docs.append(self._deserialize(entry))
        docs.sort(key=lambda d: float(d.get("ingested_at", 0)), reverse=True)
        return docs

    def get_document(self, doc_id: str) -> Optional[dict]:
        """Return a single document entry or None if not found."""
        entry = self._client.hgetall(self._key(doc_id))
        return self._deserialize(entry) if entry else None

    def delete_document(self, doc_id: str) -> bool:
        """Remove a document from the catalog.

        Returns True when the entry was found and deleted, False when not found.
        Note: Callers are responsible for also removing the embeddings from
        the vector store using the doc_id metadata field.
        """
        key = self._key(doc_id)
        deleted = self._client.delete(key)
        if deleted:
            logger.info(f"Deleted document doc_id={doc_id} from registry")
            return True
        logger.warning(f"Delete requested for unknown doc_id={doc_id}")
        return False

    def health(self) -> bool:
        """Ping Redis to confirm connectivity."""
        try:
            return self._client.ping()
        except Exception:
            return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _deserialize(entry: dict) -> dict:
        """Convert Redis string values to appropriate Python types."""
        result = dict(entry)
        for field in ("chunk_count",):
            if field in result:
                try:
                    result[field] = int(result[field])
                except ValueError:
                    pass
        for field in ("ingested_at", "updated_at"):
            if field in result:
                try:
                    result[field] = float(result[field])
                except ValueError:
                    pass
        return result
