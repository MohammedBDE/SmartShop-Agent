"""LLM module: builds the final prompt with a LangChain LCEL chain, merges the
retrieved context and/or tool results, applies conversational memory, and calls
the Anthropic API with retry and fallback."""

import json
import logging

from server.config import Config
from server.services import rag, tools

logger = logging.getLogger(__name__)


ANSWER_SYSTEM_PROMPT = """You are the assistant of a small online clothing shop.
Answer the customer directly, briefly and politely. Always reply in English.

Ground rules:
- Use ONLY the context block below when it contains relevant information.
- Never invent stock levels, prices, discounts or policy details. If the context
  does not answer the question, say so and offer to contact the shop.
- When tool results are given, report their numbers exactly as they are.
- When an item, size or discount code was not found, say it plainly.
- Keep answers under about 120 words unless the customer asks for detail.
- Write plain text only. No markdown: no asterisks for bold, no hash headings and no
  backticks. Use short lines or simple dashes for lists.
"""

TOOL_SYSTEM_PROMPT = """You are the tool-calling step of a shop assistant.
Call the provided tool with arguments taken from the customer's message and the
recent conversation. Do not ask the customer for information that can be omitted;
optional arguments may be left out.
"""

FALLBACK_MESSAGE = (
    "The AI service is temporarily unavailable. Please try again in a moment, "
    "or contact the store directly."
)


def _build_model(**overrides):
    from langchain_anthropic import ChatAnthropic

    params = {
        "model": Config.ANTHROPIC_MODEL,
        "api_key": Config.ANTHROPIC_API_KEY,
        "max_tokens": Config.ANTHROPIC_MAX_TOKENS,
        "timeout": 45,
        "max_retries": Config.ANTHROPIC_MAX_RETRIES,
    }
    params.update(overrides)
    return ChatAnthropic(**params)


def _history_messages(history: list):
    from langchain_core.messages import AIMessage, HumanMessage

    messages = []
    for item in history or []:
        content = item.get("content") or ""
        if not content:
            continue
        if item.get("role") == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def _fallback_answer(_inputs) -> str:
    logger.error("LLM chain fell back: Anthropic call failed after retries")
    return FALLBACK_MESSAGE


def _answer_chain():
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.runnables import RunnableLambda

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", ANSWER_SYSTEM_PROMPT),
            MessagesPlaceholder("history"),
            ("human", "{question}\n\n--- CONTEXT ---\n{context_block}\n--- END CONTEXT ---"),
        ]
    )

    chain = prompt | _build_model() | StrOutputParser()

    return chain.with_retry(
        stop_after_attempt=Config.ANTHROPIC_MAX_RETRIES
    ).with_fallbacks([RunnableLambda(_fallback_answer)])


def _call_tool_model(question: str, history_messages: list, tool_name: str):
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    schemas = [s for s in tools.TOOL_SCHEMAS if s["name"] == tool_name] or tools.TOOL_SCHEMAS

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", TOOL_SYSTEM_PROMPT),
            MessagesPlaceholder("history"),
            ("human", "{question}"),
        ]
    )

    try:
        model = _build_model().bind_tools(schemas, tool_choice="any")
    except Exception:
        model = _build_model().bind_tools(schemas)

    chain = (prompt | model).with_retry(stop_after_attempt=Config.ANTHROPIC_MAX_RETRIES)
    return chain.invoke({"question": question, "history": history_messages})


def run_tool_route(question: str, tool_name: str, session_id: str,
                   history_messages: list, message_id=None) -> dict:
    """Ask the model for tool arguments, execute the tool, persist the call."""
    result = {"tool_name": tool_name, "tool_input": None, "tool_output": None, "error": None}

    if not Config.ANTHROPIC_API_KEY:
        result["error"] = "missing_api_key"
        return result

    try:
        ai_message = _call_tool_model(question, history_messages, tool_name)
    except Exception as exc:
        logger.error("Tool-argument call failed: %s", exc)
        result["error"] = f"tool_call_failed: {exc}"
        return result

    tool_calls = getattr(ai_message, "tool_calls", None) or []
    if not tool_calls:
        result["error"] = "model_returned_no_tool_call"
        return result

    call = tool_calls[0]
    called_name = call.get("name") or tool_name
    tool_input = call.get("args") or {}

    output = tools.execute_tool(
        called_name, tool_input, session_id=session_id, message_id=message_id
    )

    result["tool_name"] = called_name
    result["tool_input"] = tool_input
    result["tool_output"] = output
    return result


def _context_block(route: str, retrieval: dict = None, tool_result: dict = None) -> str:
    if route == "rag":
        if retrieval and retrieval.get("context"):
            return "Knowledge base excerpts:\n" + retrieval["context"]
        reason = (retrieval or {}).get("empty_reason") or (retrieval or {}).get("error")
        return f"Knowledge base returned nothing relevant (reason: {reason})."

    if route == "tool":
        if tool_result and tool_result.get("tool_output") is not None:
            return (
                f"Result of tool {tool_result['tool_name']} "
                f"called with {json.dumps(tool_result.get('tool_input'), ensure_ascii=False)}:\n"
                f"{json.dumps(tool_result['tool_output'], ensure_ascii=False, indent=2)}"
            )
        return f"The tool could not be executed (reason: {(tool_result or {}).get('error')})."

    return "No external context was needed for this question."


def _finalise(outcome: dict) -> dict:
    seen = set()
    outcome["notes"] = [n for n in outcome["notes"] if not (n in seen or seen.add(n))]
    return outcome


def generate(question: str, decision: dict, session_id: str,
             history: list = None, message_id=None) -> dict:
    """Run the path chosen by the router and produce the final answer."""
    route = decision.get("route", "direct")
    history_messages = _history_messages(history)

    outcome = {
        "answer": "",
        "route": route,
        "tool_name": decision.get("tool_name"),
        "tool_input": None,
        "tool_output": None,
        "sources": [],
        "retrieval": None,
        "degraded": False,
        "notes": [],
    }

    retrieval = None
    tool_result = None

    if route == "rag":
        retrieval = rag.retrieve(question)
        outcome["retrieval"] = retrieval
        outcome["sources"] = rag.sources_from_chunks(retrieval.get("chunks", []))
        if retrieval.get("error") or retrieval.get("empty_reason"):
            outcome["degraded"] = True
            outcome["notes"].append(
                retrieval.get("error") or retrieval.get("empty_reason")
            )

    elif route == "tool":
        tool_result = run_tool_route(
            question, decision.get("tool_name"), session_id, history_messages, message_id
        )
        outcome["tool_name"] = tool_result.get("tool_name")
        outcome["tool_input"] = tool_result.get("tool_input")
        outcome["tool_output"] = tool_result.get("tool_output")
        if tool_result.get("error"):
            outcome["degraded"] = True
            outcome["notes"].append(tool_result["error"])

    context_block = _context_block(route, retrieval, tool_result)

    if not Config.ANTHROPIC_API_KEY:
        outcome["answer"] = (
            "ANTHROPIC_API_KEY is not configured, so no answer can be generated. "
            "Add the key to the .env file and restart the server."
        )
        outcome["degraded"] = True
        outcome["notes"].append("missing_api_key")
        return _finalise(outcome)

    try:
        chain = _answer_chain()
        outcome["answer"] = chain.invoke(
            {
                "question": question,
                "context_block": context_block,
                "history": history_messages,
            }
        )
    except Exception as exc:
        logger.error("Answer generation failed: %s", exc)
        outcome["answer"] = FALLBACK_MESSAGE
        outcome["degraded"] = True
        outcome["notes"].append(f"llm_failed: {type(exc).__name__}")

    if outcome["answer"] == FALLBACK_MESSAGE:
        outcome["degraded"] = True

    return _finalise(outcome)
