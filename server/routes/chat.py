"""POST /chat - full pipeline: router -> RAG/tool -> LLM -> formatted response."""

import logging

from flask import Blueprint, jsonify, request

from server.config import Config
from server.db import connection
from server.services import formatter, llm_chain, router

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)

MAX_MESSAGE_LENGTH = 2000


def _error(message, code, status, details=None):
    payload, http_status = formatter.build_error(message, code, status, details)
    return jsonify(payload), http_status


@chat_bp.post("/chat")
def chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("Request body must be a JSON object.", "bad_request", 400)

    question = payload.get("message") or payload.get("question")
    if not isinstance(question, str) or not question.strip():
        return _error(
            "Field 'message' is required and must be a non-empty string.",
            "bad_request", 400,
        )

    question = question.strip()
    if len(question) > MAX_MESSAGE_LENGTH:
        return _error(
            f"Message is too long (max {MAX_MESSAGE_LENGTH} characters).",
            "message_too_long", 400,
        )

    try:
        session_id = connection.ensure_session(payload.get("session_id"))
    except Exception as exc:
        logger.error("Could not open a session: %s", exc)
        return _error(
            "Database is unavailable, please try again later.",
            "database_unavailable", 503, str(exc),
        )

    try:
        history = connection.get_messages(session_id, limit=Config.MEMORY_MAX_MESSAGES)
    except Exception as exc:
        logger.warning("Could not load conversation memory: %s", exc)
        history = []

    try:
        connection.save_message(session_id, "user", question)
    except Exception as exc:
        logger.warning("Could not persist the user message: %s", exc)

    decision = router.classify(question, history)

    outcome = llm_chain.generate(
        question=question,
        decision=decision,
        session_id=session_id,
        history=history,
    )

    message_id = None
    try:
        message_id = connection.save_message(
            session_id,
            "assistant",
            outcome.get("answer", ""),
            route=outcome.get("route"),
            tool_name=outcome.get("tool_name"),
            router_reasoning=decision.get("reasoning"),
            sources=outcome.get("sources"),
        )
    except Exception as exc:
        logger.warning("Could not persist the assistant message: %s", exc)

    response = formatter.build_response(
        session_id=session_id,
        message_id=message_id,
        question=question,
        decision=decision,
        outcome=outcome,
    )
    return jsonify(response), 200
