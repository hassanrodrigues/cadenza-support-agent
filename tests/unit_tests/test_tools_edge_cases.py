from types import SimpleNamespace

import pytest

from cadenza import tools
from cadenza.context import Context, parse_now


def runtime_at(iso):
    return SimpleNamespace(context=Context(now=parse_now(iso)))


def ids(result, key="products"):
    return [p["id"] for p in result[key]]


def test_price_bounds_are_inclusive_on_the_exact_promotional_price():
    assert ids(tools.search_products(query="crafter", max_price=1967.18)) == [90]
    assert ids(
        tools.search_products(query="taylor", min_price=5519.08, max_price=5519.08)
    ) == [94]


def test_float_prices_from_the_model_compare_without_rounding_noise():
    assert 81 in ids(tools.search_products(category="violão", max_price=599.9))


def test_search_ignores_portuguese_stopwords():
    result = tools.search_products(query="violão de nylon", only_available=False)
    products = tools._store().products
    assert result["products"]
    assert all(products.loc[i, "specs"]["strings"] == "nylon" for i in ids(result))


def test_cheap_item_gets_only_the_installments_its_tier_allows():
    assert (
        tools.get_product_details("119")["installments"]
        == "até 3x de R$ 53,30 sem juros"
    )


@pytest.mark.parametrize(
    ("name_or_id", "availability"), [("136", "discontinued"), ("130", "coming_soon")]
)
def test_items_not_for_sale_come_with_alternatives_regardless_of_stock(
    name_or_id, availability
):
    result = tools.get_product_details(name_or_id)
    assert result["availability"] == availability
    assert result["alternatives"]
    assert all(a["availability"] == "available" for a in result["alternatives"])


def test_unknown_product_id_returns_an_error():
    assert "error" in tools.get_product_details("999")


def test_future_order_is_hidden_even_from_its_owner():
    result = tools.lookup_orders(
        "camila.duarte@inlook.com", order_id=16, runtime=runtime_at("2026-03-01T10:00")
    )
    assert result == {"error": tools.ORDER_NOT_FOUND}


def test_cancelled_order_shows_status_but_no_return_rules():
    result = tools.lookup_orders(
        "(67) 98321-6543", order_id=20, runtime=runtime_at("2026-03-25T10:00")
    )
    order = result["orders"][0]
    assert order["status"] == "cancelado"
    assert "returns" not in order
    assert "tracking_code" not in order


def test_regret_window_closes_the_day_after_the_deadline():
    contact = "leticia.rocha@jmail.com"
    last_day = tools.lookup_orders(contact, runtime=runtime_at("2026-02-24T23:59"))
    day_after = tools.lookup_orders(contact, runtime=runtime_at("2026-02-25T00:00"))
    assert last_day["orders"][0]["returns"]["regret_return"]["eligible"] is True
    assert day_after["orders"][0]["returns"]["regret_return"]["eligible"] is False


def test_reference_time_is_read_in_store_timezone():
    # 03:30 UTC on Feb 25 is still Feb 24 in Campo Grande (UTC-4).
    result = tools.lookup_orders(
        "leticia.rocha@jmail.com", runtime=runtime_at("2026-02-25T03:30+00:00")
    )
    assert result["orders"][0]["returns"]["regret_return"]["eligible"] is True
