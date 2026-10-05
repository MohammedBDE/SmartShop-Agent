"""Agent Router: classifies every incoming request and decides the path
(RAG / tool / direct answer) before any answer is generated."""

import json
import logging
import re

from server.config import Config
from server.services.tools import TOOL_SCHEMAS

logger = logging.getLogger(__name__)

VALID_ROUTES = {"rag", "tool", "direct"}
TOOL_NAMES = [schema["name"] for schema in TOOL_SCHEMAS]

CLASSIFIER_SYSTEM_PROMPT = """You are the routing component of a shop assistant.
Classify the customer's latest message into exactly one route. Answer nothing else.

Routes:
- "rag": the answer lives in the shop's written knowledge base: return policy,
  exchange policy, delivery and shipping terms, warranty, opening hours, payment
  methods, size-guide advice, general FAQ.
- "tool": the answer requires live data or arithmetic that only a tool can provide.
  Available tools:
    * check_product_availability - stock or price of a specific catalog product,
      possibly in a specific size.
    * calculate_order_total - the total of an order, with an optional discount code.
- "direct": small talk, greetings, thanks, or general knowledge that needs neither
  the knowledge base nor a tool.

Rules:
- A question about a *specific* product's stock or price is "tool", not "rag".
- A question about the rules of returning, shipping or exchanging is "rag", even if
  it mentions a product.
- If a message needs both, choose the route that answers the customer's main intent.
- When the message is ambiguous, prefer "rag" over "direct".

Reply with a single JSON object and nothing else:
{{"route": "rag" | "tool" | "direct", "tool_name": "<tool name or null>", "reasoning": "<one short sentence>"}}
"""

RULE_PATTERNS = {
    "check_product_availability": [
        r"\bin stock\b", r"\bstock\b", r"\bavailab", r"\bdo you have\b", r"\bgot any\b",
        r"\bsize\b", r"\bsizes\b", r"\bhow many\b", r"\bleft\b",
        r"\bprice\b", r"\bhow much is\b", r"\bhow much are\b", r"\bcost of\b",
    ],
    "calculate_order_total": [
        r"\btotal\b", r"\bsubtotal\b", r"\bcalculate\b", r"\bwork out\b",
        r"\bdiscount code\b", r"\bpromo\b", r"\bcoupon\b", r"\bvoucher\b",
        r"\bmy (cart|basket|order) come to\b", r"\bhow much would\b",
    ],
}

RAG_PATTERNS = [
    r"\bpolic", r"\breturn\b", r"\breturns\b", r"\brefund", r"\bexchang",
    r"\bdeliver", r"\bshipping\b", r"\bship\b", r"\bwarrant", r"\bguarantee\b",
    r"\bopening hours\b", r"\bworking hours\b", r"\bpayment\b", r"\bpay\b",
    r"\bcancel\b", r"\bprivacy\b", r"\bgift wrap", r"\bsize (guide|chart)\b",
    r"\bhow do i (return|exchange|track|cancel)\b", r"\bcare instructions\b",
]


def _rule_based_classify(question: str) -> dict:
    text = (question or "").lower()

    for pattern in RAG_PATTERNS:
        if re.search(pattern, text):
            return {
                "route": "rag",
                "tool_name": None,
                "reasoning": f"Rule match on knowledge-base keyword: /{pattern}/",
                "classifier": "rules",
            }

    for tool_name, patterns in RULE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                return {
                    "route": "tool",
                    "tool_name": tool_name,
                    "reasoning": f"Rule match on tool keyword: /{pattern}/",
                    "classifier": "rules",
                }

    return {
        "route": "direct",
        "tool_name": None,
        "reasoning": "No knowledge-base or tool keyword matched.",
        "classifier": "rules",
    }


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise ValueError("classifier returned no JSON object")
    return json.loads(match.group(0))


def _normalise(decision: dict, classifier: str) -> dict:
    route = str(decision.get("route", "")).strip().lower()
    if route not in VALID_ROUTES:
        raise ValueError(f"invalid route: {route!r}")

    tool_name = decision.get("tool_name")
    if isinstance(tool_name, str):
        tool_name = tool_name.strip() or None

    if route == "tool":
        if tool_name not in TOOL_NAMES:
            raise ValueError(f"invalid tool_name: {tool_name!r}")
    else:
        tool_name = None

    return {
        "route": route,
        "tool_name": tool_name,
        "reasoning": str(decision.get("reasoning", "")).strip()[:400],
        "classifier": classifier,
    }


def _llm_classify(question: str, history: list = None) -> dict:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    model = ChatAnthropic(
        model=Config.ANTHROPIC_ROUTER_MODEL,
        api_key=Config.ANTHROPIC_API_KEY,
        max_tokens=300,
        temperature=0,
        timeout=20,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CLASSIFIER_SYSTEM_PROMPT),
            ("human", "Recent conversation:\n{history}\n\nLatest message:\n{question}"),
        ]
    )

    chain = prompt | model | StrOutputParser()

    history_text = "(none)"
    if history:
        history_text = "\n".join(
            f"{item['role']}: {item['content']}" for item in history[-4:]
        )

    raw = chain.invoke({"question": question, "history": history_text})
    return _normalise(_extract_json(raw), "llm")


def classify(question: str, history: list = None) -> dict:
    """Return {route, tool_name, reasoning, classifier}.

    An LLM classifier decides the route; if it is unavailable or answers with
    something invalid, a deterministic rule-based classifier takes over so the
    router step is never skipped.
    """
    if not question or not question.strip():
        return {
            "route": "direct",
            "tool_name": None,
            "reasoning": "Empty message.",
            "classifier": "rules",
        }

    if not Config.ANTHROPIC_API_KEY:
        decision = _rule_based_classify(question)
        decision["reasoning"] += " (no API key, rule-based fallback)"
        return decision

    try:
        return _llm_classify(question, history)
    except Exception as exc:
        logger.warning("LLM classifier failed (%s); falling back to rules", exc)
        decision = _rule_based_classify(question)
        decision["reasoning"] += f" (LLM classifier unavailable: {type(exc).__name__})"
        return decision
