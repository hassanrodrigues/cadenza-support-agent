import json
from types import SimpleNamespace

from cadenza import tools
from cadenza.context import Context, parse_now


def ids(result, key="products"):
    return [p["id"] for p in result[key]]


def test_search_lists_available_acoustic_guitars_up_to_1000_sorted_by_price():
    result = tools.search_products(category="violões", max_price=1000)
    assert result["showing"] == "8 of 12"
    products = tools._store().products
    prices = [products.loc[i, "effective_price"] for i in ids(result)]
    assert prices == sorted(prices)
    assert result["products"][0] == {
        "id": 83,
        "name": "Tagima Memphis AC-39 Nylon Natural",
        "availability": "available",
        "price": "R$ 429,90",
        "pix_price": "R$ 408,41",
    }
    assert 96 not in ids(result)


def test_search_price_filter_uses_the_promotional_price():
    result = tools.search_products(query="crafter", max_price=2000)
    assert ids(result) == [90]
    assert result["products"][0]["price"] == "R$ 1.967,18"


def test_search_matches_model_codes_without_punctuation():
    assert ids(tools.search_products(query="GD-20")) == [95]


def test_search_can_include_items_not_for_sale():
    result = tools.search_products(query="giannini gf3d", only_available=False)
    assert result["products"][0]["availability"] == "out_of_stock"


def test_search_in_empty_category_says_not_right_now():
    result = tools.search_products(category="violino")
    assert result["showing"] == "0 of 0"
    assert "no momento não temos" in result["notice"]


def test_search_with_unknown_category_lists_known_ones():
    result = tools.search_products(category="pandeiro")
    assert "error" in result
    assert "Violões" in result["known_categories"]


def test_details_show_price_pix_installments_and_ended_promotion():
    result = tools.get_product_details("Takamine GD20")
    assert result["id"] == 95
    assert result["price"] == "R$ 2.199,00"
    assert result["pix_price"] == "R$ 2.089,05"
    assert result["installments"] == "até 12x de R$ 183,25 sem juros"
    assert result["ended_promotions"] == [
        "12% (Oferta Especial) - ended, no longer valid"
    ]
    assert "discount" not in result


def test_details_of_promo_product_show_original_price_and_no_pix():
    result = tools.get_product_details("Taylor 110e")
    assert result["price"] == "R$ 5.519,08"
    assert result["original_price"] == "R$ 5.999,00"
    assert result["discount"].startswith("8% off")
    assert "pix_price" not in result


def test_ambiguous_name_returns_candidates():
    result = tools.get_product_details("Martin D-28")
    assert result["ambiguous"] is True
    assert sorted(ids(result, "candidates")) == [93, 108]


def test_specific_model_code_resolves_the_ambiguity():
    assert tools.get_product_details("Martin D28E")["id"] == 108


def test_out_of_stock_product_offers_three_available_alternatives_in_same_category():
    result = tools.get_product_details("Giannini GF-3D")
    assert result["availability"] == "out_of_stock"
    alternatives = result["alternatives"]
    assert len(alternatives) == 3
    assert all(a["availability"] == "available" for a in alternatives)
    products = tools._store().products
    assert all(products.loc[a["id"], "category_id"] == 5 for a in alternatives)


def test_conflicting_description_is_never_exposed():
    assert "description" not in tools.get_product_details("135")
    assert "StingRay" in tools.get_product_details("138")["description"]


def test_unknown_product_returns_an_error():
    assert "error" in tools.get_product_details("xyz banana")


def test_active_promotions_are_the_four_flagged_in_the_data():
    assert sorted(ids(tools.list_active_promotions(), "promotions")) == [
        90,
        94,
        121,
        127,
    ]


def test_tool_results_are_plain_json():
    for result in (
        tools.search_products(category="baixo", only_available=False),
        tools.get_product_details("Giannini GF-3D"),
        tools.list_active_promotions(),
    ):
        json.dumps(result)


def runtime_at(iso):
    return SimpleNamespace(context=Context(now=parse_now(iso)))


def test_orders_are_found_by_phone_in_any_format():
    for phone in ("(67) 99812-3456", "67998123456", "+55 67 99812-3456"):
        result = tools.lookup_orders(phone, runtime=runtime_at("2026-03-25T10:00"))
        assert [o["order_id"] for o in result["orders"]] == [4]


def test_partial_phone_is_refused():
    result = tools.lookup_orders("99812-3456", runtime=runtime_at("2026-03-25T10:00"))
    assert "DDD" in result["error"]


def test_unknown_contact_and_someone_elses_order_get_the_same_answer():
    now = runtime_at("2026-03-25T10:00")
    unknown = tools.lookup_orders("nobody@jmail.com", runtime=now)
    not_theirs = tools.lookup_orders("lucas.mendes@jmail.com", order_id=7, runtime=now)
    assert unknown == not_theirs == {"error": tools.ORDER_NOT_FOUND}


def test_shared_email_asks_for_more_unless_order_number_is_given():
    now = runtime_at("2026-03-25T10:00")
    assert (
        "more than one"
        in tools.lookup_orders("bruno.martins@jmail.com", runtime=now)["error"]
    )
    result = tools.lookup_orders("bruno.martins@jmail.com", order_id=10, runtime=now)
    assert result["orders"][0]["total"] == "R$ 8.732,00"


def test_delivered_order_comes_with_return_eligibility_computed():
    result = tools.lookup_orders(
        "leticia.rocha@jmail.com", runtime=runtime_at("2026-02-20T10:00")
    )
    order = result["orders"][0]
    assert order["order_id"] == 7
    assert order["status"] == "entregue"
    assert order["payment"] == "cartão de crédito em 3x"
    assert order["days_since_delivery"] == 3
    assert order["returns"]["regret_return"] == {
        "eligible": True,
        "deadline": "24/02/2026",
    }
    later = tools.lookup_orders(
        "leticia.rocha@jmail.com", runtime=runtime_at("2026-03-01T10:00")
    )
    assert later["orders"][0]["returns"]["regret_return"]["eligible"] is False


def test_shipped_order_past_its_estimate_is_flagged_overdue():
    result = tools.lookup_orders(
        "(67) 99654-7821", runtime=runtime_at("2026-03-10T10:00")
    )
    order = result["orders"][0]
    assert order["status"] == "enviado"
    assert order["tracking_code"] == "BRJL5544332BR"
    assert order["delivery_overdue"] is True
    assert "returns" not in order


def test_orders_after_the_reference_time_are_ignored():
    result = tools.lookup_orders(
        "camila.duarte@inlook.com", runtime=runtime_at("2026-03-01T10:00")
    )
    assert result == {"error": tools.ORDER_NOT_FOUND}


def test_order_lookup_result_is_plain_json():
    json.dumps(
        tools.lookup_orders(
            "leticia.rocha@jmail.com", runtime=runtime_at("2026-02-20T10:00")
        )
    )


def test_tool_schemas_hide_the_injected_runtime():
    from langgraph.prebuilt import ToolNode

    node = ToolNode(tools.TOOLS, handle_tool_errors=True)
    schema = node.tools_by_name["lookup_orders"].tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"contact", "order_id"}
