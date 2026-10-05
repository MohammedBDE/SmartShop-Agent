"""GET /history - conversation history of one session, ordered chronologically."""

import logging

from flask import Blueprint, jsonify, request

from server.db import connection
from server.services import formatter

logger = logging.getLogger(__name__)

history_bp = Blueprint("history", __name__)


@history_bp.get("/history")
def history():
    session_id = request.args.get("session_id", "").strip()
    if not session_id:
        payload, status = formatter.build_error(
            "Query parameter 'session_id' is required.", "bad_request", 400
        )
        return jsonify(payload), status

    try:
        messages = connection.get_messages(session_id)
        tool_calls = connection.get_tool_calls(session_id)
    except Exception as exc:
        logger.error("Could not read history: %s", exc)
        payload, status = formatter.build_error(
            "Could not read the conversation history.",
            "database_unavailable", 503, str(exc),
        )
        return jsonify(payload), status

    for message in messages:
        message["route_label"] = (
            formatter.route_label(message["route"], message.get("tool_name"))
            if message.get("route")
            else None
        )

    return jsonify(
        {
            "ok": True,
            "session_id": session_id,
            "count": len(messages),
            "messages": messages,
            "tool_calls": tool_calls,
        }
    ), 200
