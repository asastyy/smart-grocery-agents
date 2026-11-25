from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import httpx
import pytest

from smart_grocery.retail.matching import match_product, resolve_ingredient
from smart_grocery.retail.mcp import MCPClient, decode_rpc
from smart_grocery.retail.normalization import normalize_product
from smart_grocery.retail.purchasing import eligibility_reasons, quote_packages
from smart_grocery.retail.report import build_retail_report
from smart_grocery.retail.snapshot import DEFAULT_CAPTURE, snapshot_provider
from smart_grocery.retail.vkusvill import VkusVillProvider
from smart_grocery.tools.grocery_provider import CartItem, NotSupported, ProviderUnavailable


NOW = datetime(2026, 11, 26, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def rice_raw():
    capture = json.loads(DEFAULT_CAPTURE.read_text())
    record = next(record for record in capture["records"] if record.get("ingredient_id") == "rice")
    return json.loads(record["response"]["content"][0]["text"])["data"]["items"][0]


def normalized(raw, ingredient="rice", **kwargs):
    offer, issue = normalize_product(raw, ingredient, NOW, **kwargs)
    assert issue is None
    return offer


@pytest.mark.parametrize("ingredient,title,status", [
    ("rice", "Рис Жасмин, 500 г", "accepted"),
    ("rice", "Рисовая мука, 500 г", "rejected"),
    ("rice", "Каша рисовая готовая", "rejected"),
    ("rice", "Rice", "accepted"),
    ("rice", "ric", "review"),
    ("milk", "Молоко 3,2%, 1 л", "accepted"),
    ("milk", "Молоко кокосовое, 400 мл", "rejected"),
    ("milk", "Молоко сгущенное", "rejected"),
    ("milk", "Напиток овсяный", "rejected"),
    ("egg", "Яйцо куриное С1", "accepted"),
    ("egg", "Яйцо перепелиное, 20 шт", "rejected"),
    ("egg", "Яйцо куриное вареное", "rejected"),
    ("chicken_breast", "Филе грудки цыпленка-бройлера", "accepted"),
    ("chicken_breast", "Грудка цыплят-бройлеров на кости", "rejected"),
    ("chicken_breast", "Филе бедра цыпленка", "rejected"),
    ("chicken_breast", "Котлеты из куриной грудки", "rejected"),
    ("tomato", "Томаты сливка, 450 г", "accepted"),
    ("tomato", "Соус томатный", "rejected"),
    ("tomato", "Томаты маринованные", "rejected"),
    ("olive_oil", "Масло оливковое Extra Virgin", "accepted"),
    ("olive_oil", "Масло оливковое, спрей", "rejected"),
    ("olive_oil", "Смесь оливкового и подсолнечного масла", "rejected"),
])
def test_reviewed_name_matching(ingredient, title, status):
    assert match_product(ingredient, title).status == status


def test_ingredient_aliases_do_not_create_unreviewed_ids():
    assert resolve_ingredient("помидоры") == "tomato"
    assert resolve_ingredient("eggs") == "egg"
    with pytest.raises(ValueError):
        resolve_ingredient("unknown_food")


def test_real_capture_normalizes_eleven_and_preserves_unknowns():
    provider = snapshot_provider()
    offers = [offer for key in ("rice", "egg", "chicken_breast", "milk", "tomato", "olive_oil")
              for offer in provider.search_products(key)]
    assert len(offers) == 11
    assert all(offer.availability == "unknown" and offer.allergens_status == "unknown" and offer.allergens is None for offer in offers)
    assert all(offer.retrieved_at.year == 2026 for offer in offers)
    assert {issue.code for issue in provider.issues} >= {"variable_weight_price_not_package", "match_rejected", "package_quantity_unverified"}


def test_price_for_card_discount_is_not_assumed(rice_raw):
    offer = normalized(rice_raw)
    assert offer.price == 146  # source current=130 requires the loyalty card
    assert offer.price_source.startswith("price.old")
    assert "discount_requires_confirmation" in offer.warnings
    rice_raw["price"]["old"] = None
    assert normalized(rice_raw).price is None


def test_whole_packages_not_proportional_ingredient_price(rice_raw):
    rice_raw.update(name="Рис, 400 г", weight={"value": 0.4, "unit": "кг"})
    rice_raw["price"] = {"current": 120, "currency": "RUB"}
    offer = normalized(rice_raw)
    quote = quote_packages(offer, 600)
    assert (quote.package_count, quote.purchased_quantity, quote.surplus_quantity, quote.total) == (2, 800, 200, 240)
    assert quote_packages(offer, 800).package_count == 2


def test_volume_is_not_inferred_from_mass_and_egg_count_is_explicit():
    provider = snapshot_provider()
    assert provider.search_products("olive_oil") == []
    milk = provider.search_products("milk")[0]
    assert milk.package_unit == "ml" and milk.package_quantity == 900 and milk.package_source == "title"
    egg = provider.search_products("egg")[0]
    assert egg.package_unit == "pcs" and egg.package_quantity == 10
    assert egg.package_source == "description:explicit_package_count"


@pytest.mark.parametrize("change,code", [
    ({"unit": "кг"}, "variable_weight_price_not_package"),
    ({"weight": {"value": 0.5, "unit": "кг"}}, "conflicting_package_size"),
    ({"price": {"current": -1, "currency": "RUB"}}, "invalid_number"),
    ({"id": "bad"}, "invalid_product_id"),
    ({"name": "Рис, 2 х 400 г"}, "multipack_requires_review"),
])
def test_ambiguous_data_is_quarantined(rice_raw, change, code):
    rice_raw.update(change)
    offer, issue = normalize_product(rice_raw, "rice", NOW)
    assert offer is None and issue.code == code


def test_only_personalized_quantity_can_confirm_stock(rice_raw):
    rice_raw["available_quantity"] = 5
    assert normalized(rice_raw).availability == "unknown"
    assert normalized(rice_raw, personalized=True).availability == "in_stock"
    rice_raw["available_quantity"] = 0
    assert normalized(rice_raw, personalized=True).availability == "out_of_stock"


def test_unknown_allergens_stock_and_stale_prices_block_selection(rice_raw):
    offer = normalized(rice_raw)
    assert set(eligibility_reasons(offer, unit="g", currency="RUB", allergies=("peanut",), now=NOW)) == {"availability_unknown", "allergens_unknown"}
    assert "stale_or_future_offer" in eligibility_reasons(offer, unit="g", currency="RUB", now=NOW + timedelta(days=2))
    offer = offer.model_copy(update={"availability": "in_stock", "allergens_status": "confirmed", "allergens": ["peanut"]})
    assert "allergen_conflict" in eligibility_reasons(offer, unit="g", currency="RUB", allergies=("peanut",), now=NOW)


def test_unknown_price_and_invalid_demand_cannot_be_quoted(rice_raw):
    offer = normalized(rice_raw)
    for missing in (0, -1, "NaN", "Infinity"):
        with pytest.raises(ValueError):
            quote_packages(offer, missing)
    with pytest.raises(ValueError):
        quote_packages(offer.model_copy(update={"price": None}), 600)


def test_real_snapshot_golden_case_does_not_become_safe_basket():
    report = build_retail_report(snapshot_provider())
    assert report["normalized_offer_count"] == 11
    result = report["golden_case_strict"]
    assert len(result["plan"]["meals"]) == 10
    assert not result["valid"] and result["shopping_list"]["estimated_total"] is None
    assert result["shopping_list"]["priced_subtotal"] == "0.00"
    assert all(line["selected_offer"] is None for line in result["shopping_list"]["lines"])


def rpc_transport(handler):
    def respond(request):
        body = json.loads(request.content)
        if body["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"protocolVersion": "2025-03-26"}}, headers={"Mcp-Session-Id": "private-test-session"})
        if body["method"] == "notifications/initialized":
            assert "id" not in body
            return httpx.Response(202)
        assert request.headers["Mcp-Session-Id"] == "private-test-session"
        return handler(request, body)
    return httpx.MockTransport(respond)


def test_mcp_handshake_sse_and_no_order_tools():
    seen = []
    def handler(request, body):
        seen.append(body)
        payload = {"jsonrpc": "2.0", "id": body["id"], "result": {"content": [{"type": "text", "text": '{"ok":true,"data":{"items":[]}}'}]}}
        return httpx.Response(200, text="event: message\ndata: " + json.dumps(payload) + "\n\n", headers={"content-type": "text/event-stream"})
    client = MCPClient(transport=rpc_transport(handler))
    assert client.call_tool("vkusvill_products_search", {"q": "рис"}) == {"items": []}
    for prohibited in ("confirm_order", "checkout_preview", "vkusvill_orders_history"):
        with pytest.raises(ValueError):
            client.call_tool(prohibited, {})
    assert len(seen) == 1
    assert "private-test-session" not in json.dumps(client.responses)
    client.close()


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_mcp_errors_are_sanitized_and_not_retried(status):
    count = 0
    def handler(request, body):
        nonlocal count
        count += 1
        return httpx.Response(status, text="private credentials and server details")
    client = MCPClient(transport=rpc_transport(handler))
    with pytest.raises(ProviderUnavailable) as error:
        client.call_tool("vkusvill_products_search", {"q": "рис"})
    assert "private" not in str(error.value) and count == 1
    client.close()


@pytest.mark.parametrize("text", ["not json", "[]", 'data: {"progress":1}\n\n'])
def test_invalid_mcp_payloads_are_rejected(text):
    with pytest.raises(ProviderUnavailable):
        decode_rpc(text)


def test_sse_multiline_and_rpc_id_check():
    assert decode_rpc('data: {"id":1,\ndata: "result":{}}\n\n')["result"] == {}
    client = MCPClient(transport=rpc_transport(lambda request, body: httpx.Response(200, json={"id": 999, "result": {}})))
    with pytest.raises(ProviderUnavailable):
        client.call_tool("vkusvill_products_search", {})
    client.close()


class FakeClient:
    def __init__(self, rice_raw):
        self.raw = deepcopy(rice_raw)
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "vkusvill_products_search":
            return {"meta": {"personalized": False}, "items": [deepcopy(self.raw)]}
        if name == "vkusvill_product_details":
            return deepcopy(self.raw)
        return {"link": "https://vkusvill.ru/mobile?basket&share=123"}

    def close(self):
        pass


def test_adapter_cache_expiry_unknown_ids_and_cart_limits(rice_raw):
    clock = [NOW]
    fake = FakeClient(rice_raw)
    provider = VkusVillProvider(fake, clock=lambda: clock[0])
    assert provider.search_products("rice") == provider.search_products("рис")
    assert len(fake.calls) == 1
    assert provider.search_products("not_in_dictionary") == []
    assert provider.get_product_details("unknown") is None
    assert isinstance(provider.create_cart([]), NotSupported)
    assert isinstance(provider.cart_link([]), NotSupported)
    clock[0] += timedelta(minutes=6)
    provider.search_products("rice")
    assert len(fake.calls) == 2
    provider.enable_cart_links = True
    product_id = str(rice_raw["id"])
    assert provider.cart_link([CartItem(product_id=product_id, package_count=2)]).startswith("https://vkusvill.ru/")
    assert fake.calls[-1][1] == {"products": [{"id": int(product_id), "q": 2}]}
    for items in ([], [CartItem(product_id=product_id, package_count=41)], [CartItem(product_id="999", package_count=1)]):
        with pytest.raises(ValueError):
            provider.cart_link(items)


def test_conflicting_details_quarantine_cached_sku(rice_raw):
    fake = FakeClient(rice_raw)
    provider = VkusVillProvider(fake, clock=lambda: NOW)
    provider.search_products("rice")
    fake.raw["weight"] = {"value": 0.5, "unit": "кг"}
    assert provider.get_product_details(str(rice_raw["id"])) is None
    assert provider.search_products("rice") == []
    provider.enable_cart_links = True
    with pytest.raises(ValueError):
        provider.cart_link([CartItem(product_id=str(rice_raw["id"]), package_count=1)])
