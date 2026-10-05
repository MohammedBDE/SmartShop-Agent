"""Response formatter: single JSON shape returned by POST /chat."""

from datetime import datetime, timezone


def route_label(route: str, tool_name: str = None) -> str:
    if route == "rag":
        return "RAG"
    if route == "tool":
        return f"Tool: {tool_name}" if tool_name else "Tool"
    return "Direct LLM"


def build_response(session_id, message_id, question, decision, outcome) -> dict:
    route = outcome.get("route", decision.get("route", "direct"))
    tool_name = outcome.get("tool_name") or decision.get("tool_name")

    return {
        "ok": True,
        "session_id": session_id,
        "message_id": message_id,
        "question": question,
        "answer": outcome.get("answer", ""),
        "route": route,
        "route_label": route_label(route, tool_name),
        "router": {
            "route": decision.get("route"),
            "tool_name": decision.get("tool_name"),
            "reasoning": decision.get("reasoning"),
            "classifier": decision.get("classifier"),
        },
        "sources": outcome.get("sources", []),
        "tool": {
            "name": tool_name,
            "input": outcome.get("tool_input"),
            "output": outcome.get("tool_output"),
        } if route == "tool" else None,
        "degraded": bool(outcome.get("degraded")),
        "notes": outcome.get("notes", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def build_error(message, code="internal_error", status=500, details=None) -> tuple:
    payload = {
        "ok": False,
        "error": {"code": code, "message": message},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if details:
        payload["error"]["details"] = details
    return payload, status
