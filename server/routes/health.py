"""GET /health - real check of the server and of the database behind it."""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify

from server.config import Config
from server.db import connection

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    db_status = connection.check_health()

    counts = {}
    if db_status["database"] == "up" and not db_status["tables_missing"]:
        try:
            row = connection.query_one(
                """
                SELECT
                    (SELECT count(*) FROM products)      AS products,
                    (SELECT count(*) FROM kb_documents)  AS kb_documents,
                    (SELECT count(*) FROM kb_chunks)     AS kb_chunks,
                    (SELECT count(*) FROM kb_chunks WHERE embedding IS NOT NULL) AS kb_embedded,
                    (SELECT count(*) FROM sessions)      AS sessions,
                    (SELECT count(*) FROM messages)      AS messages,
                    (SELECT count(*) FROM tool_calls)    AS tool_calls;
                """
            )
            counts = {key: int(value) for key, value in (row or {}).items()}
        except Exception as exc:
            logger.warning("Could not read table counts: %s", exc)

    missing_secrets = Config.missing_secrets()

    healthy = (
        db_status["database"] == "up"
        and db_status["pgvector"]
        and not db_status["tables_missing"]
        and not missing_secrets
    )

    payload = {
        "ok": healthy,
        "status": "healthy" if healthy else "degraded",
        "server": "up",
        "database": db_status,
        "counts": counts,
        "missing_secrets": missing_secrets,
        "models": {
            "answer_model": Config.ANTHROPIC_MODEL,
            "router_model": Config.ANTHROPIC_ROUTER_MODEL,
            "embedding_model": Config.EMBEDDING_MODEL,
            "embedding_dim": Config.EMBEDDING_DIM,
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    return jsonify(payload), (200 if healthy else 503)
