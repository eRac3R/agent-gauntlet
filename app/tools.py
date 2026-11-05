"""Mock backends the agent can call. Deterministic so evals are reproducible."""
from __future__ import annotations

from typing import Any, Callable

CUSTOMERS: dict[str, dict[str, str]] = {
    "C-1001": {"id": "C-1001", "name": "Alice Nguyen", "email": "alice@example.com", "plan": "pro"},
    "C-1002": {"id": "C-1002", "name": "Ben Ortiz", "email": "ben@example.com", "plan": "free"},
    "C-1003": {"id": "C-1003", "name": "Chloe Park", "email": "chloe@example.com", "plan": "enterprise"},
    "C-1004": {"id": "C-1004", "name": "Dev Patel", "email": "dev@example.com", "plan": "pro"},
    "C-1005": {"id": "C-1005", "name": "Emma Rossi", "email": "emma@example.com", "plan": "free"},
}

ORDERS: dict[str, dict[str, str]] = {
    "O-5001": {"id": "O-5001", "customer_id": "C-1001", "status": "shipped"},
    "O-5002": {"id": "O-5002", "customer_id": "C-1002", "status": "processing"},
    "O-5003": {"id": "O-5003", "customer_id": "C-1004", "status": "delivered"},
    "O-5004": {"id": "O-5004", "customer_id": "C-1003", "status": "cancelled"},
    "O-5005": {"id": "O-5005", "customer_id": "C-1003", "status": "shipped"},
}

BASE_LATENCY_MS = {"lookup_customer": 40, "get_order": 55, "web_search": 420}


class ToolError(Exception):
    """Raised when a backend is unavailable."""


class ToolTimeout(ToolError):
    """Raised when a backend does not answer in time."""


def lookup_customer(customer_id: str) -> dict | None:
    return CUSTOMERS.get(customer_id)


def get_order(order_id: str) -> dict | None:
    return ORDERS.get(order_id)


def web_search(query: str) -> list[str]:
    q = query.lower()
    if "refund" in q:
        return ["Refunds are accepted within 30 days of delivery."]
    if "shipping" in q or "ship" in q or "order" in q:
        return ["Orders typically ship within 2 business days; track them in the support portal."]
    if "customer" in q or "plan" in q:
        return ["Plan details are listed on the pricing page."]
    return ["No authoritative results found."]


TOOLS: dict[str, Callable[..., Any]] = {
    "lookup_customer": lookup_customer,
    "get_order": get_order,
    "web_search": web_search,
}

TOOL_SCHEMAS = [
    {
        "name": "lookup_customer",
        "description": "Look up a customer record (name, email, plan) by customer id like C-1001.",
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_order",
        "description": "Get an order's status by order id like O-5001.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for general policy or help-center information.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]
