"""Tools exposed to the LLM. Each tool's docstring is part of the prompt."""

from cadenza.tools.catalog import (
    get_product_details,
    list_active_promotions,
    search_products,
)
from cadenza.tools.support import get_store_policy, lookup_orders, open_support_ticket

TOOLS = [
    search_products,
    get_product_details,
    list_active_promotions,
    lookup_orders,
    get_store_policy,
    open_support_ticket,
]
