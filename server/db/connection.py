"""Database access layer: connection pooling, queries and persistence helpers."""

import json
import logging
import uuid
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from server.config import Config

logger = logging.getLogger(__name__)

_pool = None

EXPECTED_TABLES = [
    "products",
    "product_variants",
    "sessions",
    "messages",
    "tool_calls",
    "kb_documents",
    "kb_chunks",
    "discount_codes",
]


def get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=Config.database_url())
        logger.info("Database connection pool created")
    return _pool


@contextmanager
def get_connection():
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def get_cursor():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur


def query_all(sql: str, params: tuple = ()) -> list:
    with get_cursor() as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def query_one(sql: str, params: tuple = ()):
    with get_cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(sql: str, params: tuple = ()):
    with get_cursor() as cur:
        cur.execute(sql, params)
        if cur.description is not None:
            row = cur.fetchone()
            return dict(row) if row else None
        return None


def check_health() -> dict:
    """Verify the database really answers, pgvector is installed and tables exist."""
    result = {
        "database": "down",
        "pgvector": False,
        "tables_present": [],
        "tables_missing": [],
        "error": None,
    }

    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1 AS ok;")
            cur.fetchone()
            result["database"] = "up"

            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
            result["pgvector"] = cur.fetchone() is not None

            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"
            )
            present = {row["table_name"] for row in cur.fetchall()}
            result["tables_present"] = sorted(present & set(EXPECTED_TABLES))
            result["tables_missing"] = sorted(set(EXPECTED_TABLES) - present)

    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        result["error"] = str(exc)

    return result


def ensure_session(session_id=None) -> str:
    if session_id:
        try:
            uuid.UUID(str(session_id))
        except (ValueError, AttributeError, TypeError):
            session_id = None

    if session_id:
        existing = query_one(
            "SELECT session_id FROM sessions WHERE session_id = %s::uuid;",
            (str(session_id),),
        )
        if existing:
            return str(existing["session_id"])

    row = execute(
        "INSERT INTO sessions (session_id) "
        "VALUES (COALESCE(%s::uuid, gen_random_uuid())) RETURNING session_id;",
        (str(session_id) if session_id else None,),
    )
    return str(row["session_id"])


def save_message(session_id: str, role: str, content: str,
                 route=None, tool_name=None, router_reasoning=None, sources=None) -> int:
    row = execute(
        """
        INSERT INTO messages (session_id, role, content, route, tool_name, router_reasoning, sources)
        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """,
        (
            session_id,
            role,
            content,
            route,
            tool_name,
            router_reasoning,
            json.dumps(sources, ensure_ascii=False) if sources is not None else None,
        ),
    )
    return row["id"]


def get_messages(session_id: str, limit=None) -> list:
    if limit:
        rows = query_all(
            """
            SELECT * FROM (
                SELECT id, role, content, route, tool_name, router_reasoning, sources, created_at
                FROM messages
                WHERE session_id = %s::uuid
                ORDER BY created_at DESC, id DESC
                LIMIT %s
            ) AS recent
            ORDER BY created_at ASC, id ASC;
            """,
            (session_id, limit),
        )
    else:
        rows = query_all(
            """
            SELECT id, role, content, route, tool_name, router_reasoning, sources, created_at
            FROM messages
            WHERE session_id = %s::uuid
            ORDER BY created_at ASC, id ASC;
            """,
            (session_id,),
        )

    for row in rows:
        if row.get("created_at") is not None:
            row["created_at"] = row["created_at"].isoformat()
    return rows


def log_tool_call(session_id, message_id, tool_name, tool_input,
                  tool_output, status, error_message=None, latency_ms=None):
    try:
        execute(
            """
            INSERT INTO tool_calls
                (session_id, message_id, tool_name, tool_input, tool_output,
                 status, error_message, latency_ms)
            VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                session_id,
                message_id,
                tool_name,
                json.dumps(tool_input, ensure_ascii=False),
                json.dumps(tool_output, ensure_ascii=False) if tool_output is not None else None,
                status,
                error_message,
                latency_ms,
            ),
        )
    except Exception as exc:
        logger.error("Could not log tool call %s: %s", tool_name, exc)


def get_tool_calls(session_id: str) -> list:
    rows = query_all(
        """
        SELECT id, tool_name, tool_input, tool_output, status, error_message,
               latency_ms, created_at
        FROM tool_calls
        WHERE session_id = %s::uuid
        ORDER BY created_at ASC, id ASC;
        """,
        (session_id,),
    )
    for row in rows:
        if row.get("created_at") is not None:
            row["created_at"] = row["created_at"].isoformat()
    return rows
