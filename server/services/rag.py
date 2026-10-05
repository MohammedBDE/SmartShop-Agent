"""RAG module: embeds the query, retrieves the nearest chunks from pgvector
and returns them together with their similarity scores."""

import logging

from server.config import Config
from server.db import connection

logger = logging.getLogger(__name__)

_model = None


def get_model():
    """Load the sentence-transformers model once, on first use."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", Config.EMBEDDING_MODEL)
        _model = SentenceTransformer(Config.EMBEDDING_MODEL)
    return _model


def embed(text: str) -> list:
    vector = get_model().encode(text, normalize_embeddings=True)
    return [float(value) for value in vector]


def to_pgvector(vector: list) -> str:
    """psycopg2 has no native vector adapter, so send the literal form."""
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def retrieve(question: str, top_k: int = None, min_score: float = None) -> dict:
    """Return the closest knowledge-base chunks with explicit similarity scores.

    Similarity is 1 - cosine_distance, so 1.0 is identical and 0.0 unrelated.
    """
    top_k = top_k or Config.RAG_TOP_K
    min_score = Config.RAG_MIN_SCORE if min_score is None else min_score

    result = {"chunks": [], "context": "", "error": None, "empty_reason": None}

    try:
        query_vector = to_pgvector(embed(question))
    except Exception as exc:
        logger.error("Embedding failed: %s", exc)
        result["error"] = f"embedding_failed: {exc}"
        return result

    try:
        rows = connection.query_all(
            """
            SELECT c.id,
                   c.content,
                   c.chunk_index,
                   d.title,
                   d.source_type,
                   1 - (c.embedding <=> %s::vector) AS similarity
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s;
            """,
            (query_vector, query_vector, top_k),
        )
    except Exception as exc:
        logger.error("Vector search failed: %s", exc)
        result["error"] = f"retrieval_failed: {exc}"
        return result

    if not rows:
        result["empty_reason"] = "knowledge_base_empty"
        return result

    kept = []
    for row in rows:
        similarity = round(float(row["similarity"]), 4)
        if similarity < min_score:
            continue
        kept.append(
            {
                "chunk_id": row["id"],
                "title": row["title"],
                "source_type": row["source_type"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "similarity": similarity,
            }
        )

    if not kept:
        result["empty_reason"] = "no_chunk_above_threshold"
        best = round(float(rows[0]["similarity"]), 4)
        result["best_similarity_seen"] = best
        return result

    result["chunks"] = kept
    result["context"] = "\n\n".join(
        f"[{item['title']}] (similarity={item['similarity']})\n{item['content']}"
        for item in kept
    )
    return result


def sources_from_chunks(chunks: list) -> list:
    """Compact source list for the JSON response returned to the client."""
    return [
        {
            "title": chunk["title"],
            "source_type": chunk["source_type"],
            "chunk_index": chunk["chunk_index"],
            "similarity": chunk["similarity"],
            "excerpt": chunk["content"][:180],
        }
        for chunk in chunks
    ]
