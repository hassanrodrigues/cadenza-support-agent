import json

from cadenza.tools import catalog


def ids(result, key="products"):
    return [p["id"] for p in result[key]]


def test_search_lists_available_acoustic_guitars_up_to_1000_sorted_by_price():
    result = catalog.search_products(category="violões", max_price=1000)
    assert result["showing"] == "8 of 12"
    products = catalog.cached_store().products
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
    result = catalog.search_products(query="crafter", max_price=2000)
    assert ids(result) == [90]
    assert result["products"][0]["price"] == "R$ 1.967,18"


def test_search_matches_model_codes_without_punctuation():
    assert ids(catalog.search_products(query="GD-20")) == [95]


def test_search_can_include_items_not_for_sale():
    result = catalog.search_products(query="giannini gf3d", only_available=False)
    assert result["products"][0]["availability"] == "out_of_stock"


def test_search_in_empty_category_says_not_right_now():
    result = catalog.search_products(category="violino")
    assert result["showing"] == "0 of 0"
    assert "no momento não temos" in result["notice"]


def test_search_with_unknown_category_lists_known_ones():
    result = catalog.search_products(category="pandeiro")
    assert "error" in result
    assert "Violões" in result["known_categories"]


def test_details_show_price_pix_installments_and_ended_promotion():
    result = catalog.get_product_details("Takamine GD20")
    assert result["id"] == 95
    assert result["price"] == "R$ 2.199,00"
    assert result["pix_price"] == "R$ 2.089,05"
    assert result["installments"] == "até 12x de R$ 183,25 sem juros"
    assert result["ended_promotions"] == [
        "12% (Oferta Especial) - ended, no longer valid"
    ]
    assert "discount" not in result


def test_details_of_promo_product_show_original_price_and_no_pix():
    result = catalog.get_product_details("Taylor 110e")
    assert result["price"] == "R$ 5.519,08"
    assert result["original_price"] == "R$ 5.999,00"
    assert result["discount"].startswith("8% off")
    assert "pix_price" not in result


def test_ambiguous_name_returns_candidates():
    result = catalog.get_product_details("Martin D-28")
    assert result["ambiguous"] is True
    assert sorted(ids(result, "candidates")) == [93, 108]


def test_specific_model_code_resolves_the_ambiguity():
    assert catalog.get_product_details("Martin D28E")["id"] == 108


def test_out_of_stock_product_offers_three_available_alternatives_in_same_category():
    result = catalog.get_product_details("Giannini GF-3D")
    assert result["availability"] == "out_of_stock"
    alternatives = result["alternatives"]
    assert len(alternatives) == 3
    assert all(a["availability"] == "available" for a in alternatives)
    products = catalog.cached_store().products
    assert all(products.loc[a["id"], "category_id"] == 5 for a in alternatives)


def test_conflicting_description_is_never_exposed():
    assert "description" not in catalog.get_product_details("135")
    assert "StingRay" in catalog.get_product_details("138")["description"]


def test_unknown_product_returns_an_error():
    assert "error" in catalog.get_product_details("xyz banana")


def test_active_promotions_are_the_four_flagged_in_the_data():
    assert sorted(ids(catalog.list_active_promotions(), "promotions")) == [
        90,
        94,
        121,
        127,
    ]


def test_tool_results_are_plain_json():
    for result in (
        catalog.search_products(category="baixo", only_available=False),
        catalog.get_product_details("Giannini GF-3D"),
        catalog.list_active_promotions(),
    ):
        json.dumps(result)


def test_alternatives_prefer_the_same_string_type_before_price():
    # GF-3D is a steel-string guitar; the nylon Yamaha C70 is closer in price but a different instrument.
    alternatives = catalog.get_product_details("Giannini GF-3D")["alternatives"]
    assert ids({"a": alternatives}, "a") == [107, 86, 91]


def test_accessory_searches_are_answered_with_a_not_sold_notice():
    for query, category in (("palhetas", None), ("cabo p10", None), ("", "acessórios")):
        result = catalog.search_products(query=query, category=category)
        assert result["notice"] == catalog.ACCESSORY_NOTICE


def test_seven_string_guitars_are_not_mistaken_for_strings():
    assert catalog.search_products(query="violão 7 cordas")["products"]
