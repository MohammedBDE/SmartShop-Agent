"""Tools module: two custom tools declared with the Anthropic tool-use schema,
their implementations, and automatic persistence of every call."""

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal

from server.db import connection

logger = logging.getLogger(__name__)


TOOL_SCHEMAS = [
    {
        "name": "check_product_availability",
        "description": (
            "Check whether a specific product is currently in stock in a given size. "
            "Use this whenever the customer asks if an item is available, whether a size "
            "is left, how many units remain, or what the price of a catalog item is. "
            "Returns the matched product, its price, the requested size and the exact "
            "quantity on hand. If the size is omitted, returns availability for every "
            "size of that product. Never guess stock levels without calling this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": (
                        "Product name or a distinctive part of it, as written by the "
                        "customer, e.g. 'cotton t-shirt' or 'denim jacket'."
                    ),
                },
                "size": {
                    "type": "string",
                    "description": (
                        "Requested size such as S, M, L, XL, 42, or 'one-size'. "
                        "Omit when the customer did not mention a size."
                    ),
                },
            },
            "required": ["product_name"],
        },
    },
    {
        "name": "calculate_order_total",
        "description": (
            "Calculate the exact total of an order: line subtotals, an optional discount "
            "code, shipping, and the final amount to pay. Use this whenever the customer "
            "asks how much an order costs, what a discount code gives them, or whether "
            "they qualify for free shipping. Discount codes are validated against the "
            "database: an unknown, expired or inactive code is reported as invalid and no "
            "discount is applied. Never compute totals or discounts without this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Order lines to be priced.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_name": {
                                "type": "string",
                                "description": "Product name as written by the customer.",
                            },
                            "quantity": {
                                "type": "integer",
                                "description": "Number of units, at least 1.",
                                "minimum": 1,
                            },
                            "size": {
                                "type": "string",
                                "description": "Optional size for this line.",
                            },
                        },
                        "required": ["product_name", "quantity"],
                    },
                },
                "discount_code": {
                    "type": "string",
                    "description": "Optional discount code exactly as the customer typed it.",
                },
            },
            "required": ["items"],
        },
    },
]

FREE_SHIPPING_THRESHOLD = Decimal("200")
SHIPPING_FEE = Decimal("25")


def _money(value) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def check_product_availability(product_name: str, size: str = None) -> dict:
    if not product_name or not product_name.strip():
        return {"status": "invalid_input", "message": "product_name is required."}

    pattern = f"%{product_name.strip().lower()}%"
    products = connection.query_all(
        """
        SELECT id, name, category, price, currency, description
        FROM products
        WHERE lower(name) LIKE %s OR lower(COALESCE(category, '')) LIKE %s
        ORDER BY length(name) ASC
        LIMIT 5;
        """,
        (pattern, pattern),
    )

    if not products:
        return {
            "status": "product_not_found",
            "query": product_name,
            "message": "No catalog product matches this name.",
        }

    product = products[0]

    if size:
        variant = connection.query_one(
            """
            SELECT size, stock_quantity, sku
            FROM product_variants
            WHERE product_id = %s AND lower(size) = lower(%s);
            """,
            (product["id"], size.strip()),
        )
        if variant is None:
            available_sizes = connection.query_all(
                "SELECT size FROM product_variants WHERE product_id = %s ORDER BY id;",
                (product["id"],),
            )
            return {
                "status": "size_not_carried",
                "product": product["name"],
                "requested_size": size,
                "available_sizes": [row["size"] for row in available_sizes],
            }

        return {
            "status": "in_stock" if variant["stock_quantity"] > 0 else "out_of_stock",
            "product": product["name"],
            "category": product["category"],
            "price": _money(product["price"]),
            "currency": product["currency"],
            "size": variant["size"],
            "stock_quantity": variant["stock_quantity"],
            "sku": variant["sku"],
            "other_matches": [row["name"] for row in products[1:]],
        }

    variants = connection.query_all(
        """
        SELECT size, stock_quantity
        FROM product_variants
        WHERE product_id = %s
        ORDER BY id;
        """,
        (product["id"],),
    )

    return {
        "status": "sizes_listed",
        "product": product["name"],
        "category": product["category"],
        "price": _money(product["price"]),
        "currency": product["currency"],
        "sizes": [
            {"size": row["size"], "stock_quantity": row["stock_quantity"]}
            for row in variants
        ],
        "other_matches": [row["name"] for row in products[1:]],
    }


def _lookup_discount(code: str) -> dict:
    row = connection.query_one(
        "SELECT * FROM discount_codes WHERE upper(code) = upper(%s);",
        (code.strip(),),
    )
    if row is None:
        return {"valid": False, "reason": "code_not_found"}
    if not row["active"]:
        return {"valid": False, "reason": "code_inactive"}
    if row["expires_at"] is not None and row["expires_at"] < datetime.now(timezone.utc):
        return {"valid": False, "reason": "code_expired"}
    return {"valid": True, "row": row}


def calculate_order_total(items: list, discount_code: str = None) -> dict:
    if not items:
        return {"status": "invalid_input", "message": "items must contain at least one line."}

    lines = []
    unknown = []
    subtotal = Decimal("0")

    for item in items:
        name = (item or {}).get("product_name", "")
        quantity = (item or {}).get("quantity", 1)

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            quantity = 1
        quantity = max(quantity, 1)

        product = connection.query_one(
            """
            SELECT id, name, price, currency
            FROM products
            WHERE lower(name) LIKE %s
            ORDER BY length(name) ASC
            LIMIT 1;
            """,
            (f"%{str(name).strip().lower()}%",),
        )

        if product is None:
            unknown.append(name)
            continue

        unit_price = Decimal(str(product["price"]))
        line_total = unit_price * quantity
        subtotal += line_total
        lines.append(
            {
                "product": product["name"],
                "size": (item or {}).get("size"),
                "quantity": quantity,
                "unit_price": _money(unit_price),
                "line_total": _money(line_total),
            }
        )

    if not lines:
        return {
            "status": "no_priceable_items",
            "unknown_items": unknown,
            "message": "None of the requested items exist in the catalog.",
        }

    discount_amount = Decimal("0")
    discount_info = {"applied": False, "code": discount_code}

    if discount_code:
        lookup = _lookup_discount(discount_code)
        if not lookup["valid"]:
            discount_info["reason"] = lookup["reason"]
        else:
            row = lookup["row"]
            minimum = Decimal(str(row["min_order_total"]))
            if subtotal < minimum:
                discount_info["reason"] = "min_order_total_not_met"
                discount_info["min_order_total"] = _money(minimum)
            else:
                if row["percent_off"] is not None:
                    percent = Decimal(str(row["percent_off"]))
                    discount_amount = subtotal * percent / Decimal("100")
                    discount_info["percent_off"] = float(percent)
                else:
                    discount_amount = min(Decimal(str(row["amount_off"])), subtotal)
                    discount_info["amount_off"] = _money(row["amount_off"])
                discount_info["applied"] = True

    after_discount = subtotal - discount_amount
    shipping = Decimal("0") if after_discount >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE
    total = after_discount + shipping

    return {
        "status": "calculated",
        "currency": "ILS",
        "lines": lines,
        "unknown_items": unknown,
        "subtotal": _money(subtotal),
        "discount": discount_info,
        "discount_amount": _money(discount_amount),
        "shipping": _money(shipping),
        "free_shipping_threshold": _money(FREE_SHIPPING_THRESHOLD),
        "total": _money(total),
    }


TOOL_REGISTRY = {
    "check_product_availability": check_product_availability,
    "calculate_order_total": calculate_order_total,
}


def execute_tool(tool_name: str, tool_input: dict, session_id=None, message_id=None) -> dict:
    """Run a tool, persist the call, and never raise to the caller."""
    started = time.perf_counter()
    tool_input = tool_input or {}

    if tool_name not in TOOL_REGISTRY:
        output = {"status": "unknown_tool", "message": f"No tool named {tool_name}."}
        connection.log_tool_call(
            session_id, message_id, tool_name, tool_input, output,
            "error", "unknown_tool", 0,
        )
        return output

    try:
        output = TOOL_REGISTRY[tool_name](**tool_input)
        latency_ms = int((time.perf_counter() - started) * 1000)
        connection.log_tool_call(
            session_id, message_id, tool_name, tool_input, output,
            "success", None, latency_ms,
        )
        return output

    except TypeError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        output = {"status": "invalid_arguments", "message": str(exc)}
        connection.log_tool_call(
            session_id, message_id, tool_name, tool_input, output,
            "error", str(exc), latency_ms,
        )
        return output

    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.error("Tool %s failed: %s", tool_name, exc)
        output = {"status": "tool_error", "message": str(exc)}
        connection.log_tool_call(
            session_id, message_id, tool_name, tool_input, output,
            "error", str(exc), latency_ms,
        )
        return output
