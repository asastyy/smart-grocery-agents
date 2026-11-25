"""Official VkusVill MCP adapter implementing the role 4 GroceryProvider."""
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from smart_grocery.retail.matching import SPECS, resolve_ingredient
from smart_grocery.retail.mcp import MCPClient
from smart_grocery.retail.models import NormalizationIssue, RetailOffer
from smart_grocery.retail.normalization import normalize_product
from smart_grocery.tools.grocery_provider import CartItem, GroceryProvider, NotSupported, ProviderUnavailable


class VkusVillProvider(GroceryProvider):
    def __init__(self, client: MCPClient | None = None, *, enable_cart_links: bool = False, clock=None):
        self.client = client or MCPClient()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.enable_cart_links = enable_cart_links
        self.issues: list[NormalizationIssue] = []
        self._offers: dict[str, RetailOffer] = {}
        self._queries: dict[str, list[RetailOffer]] = {}
        self._query_times: dict[str, datetime] = {}
        self._quarantined: set[str] = set()

    def _quarantine(self, product_id: str):
        self._quarantined.add(product_id)
        self._offers.pop(product_id, None)
        for key in self._queries:
            self._queries[key] = [offer for offer in self._queries[key] if offer.product_id != product_id]

    def close(self):
        self.client.close()

    def search_products(self, ingredient_id: str) -> list[RetailOffer]:
        try:
            canonical = resolve_ingredient(ingredient_id)
        except ValueError:
            return []
        if canonical in self._queries:
            cached = self._queries[canonical]
            if timedelta(0) <= self.clock() - self._query_times[canonical] <= timedelta(minutes=5):
                return list(cached)
        data = self.client.call_tool("vkusvill_products_search", {
            "q": SPECS[canonical].query, "limit": 3, "page": 1, "mode": "full",
        })
        items = data.get("items")
        if not isinstance(items, list):
            raise ProviderUnavailable("invalid_search_payload")
        timestamp = self.clock()
        offers = []
        for item in items:
            offer, issue = normalize_product(item, canonical, timestamp,
                                            personalized=data.get("meta", {}).get("personalized") is True)
            if issue:
                self.issues.append(issue)
            if offer:
                if offer.product_id in self._quarantined:
                    continue
                previous = self._offers.get(offer.product_id)
                if previous and (previous.package_unit, previous.package_quantity) != (offer.package_unit, offer.package_quantity):
                    self.issues.append(NormalizationIssue(product_id=offer.product_id, code="conflicting_package_size", message="Sources disagree on package size"))
                    self._quarantine(offer.product_id)
                    continue
                self._offers[offer.product_id] = offer
                offers.append(offer)
        self._queries[canonical] = offers
        self._query_times[canonical] = timestamp
        return list(offers)

    def get_product_details(self, product_id: str) -> RetailOffer | None:
        prior = self._offers.get(product_id)
        if prior is None:
            return None  # A SKU must first be bound to a reviewed ingredient.
        data = self.client.call_tool("vkusvill_product_details", {"id": int(product_id)})
        if str(data.get("id")) != product_id:
            raise ProviderUnavailable("product_id_mismatch")
        offer, issue = normalize_product(data, prior.ingredient_id, self.clock(),
                                        personalized=prior.availability_scope == "delivery_context")
        if issue:
            self.issues.append(issue)
            if issue.code == "conflicting_package_size":
                self._quarantine(product_id)
        if offer and (offer.package_quantity, offer.package_unit) != (prior.package_quantity, prior.package_unit):
            self.issues.append(NormalizationIssue(product_id=product_id, code="conflicting_package_size", message="Search and details disagree"))
            self._quarantine(product_id)
            return None
        if offer:
            self._offers[product_id] = offer
        return offer

    def check_availability(self, product_id: str):
        # Never promote catalogue presence to address-specific availability.
        offer = self.get_product_details(product_id)
        return offer.availability if offer else "unknown"

    def cart_link(self, items: Sequence[CartItem]) -> str | NotSupported:
        if not self.enable_cart_links:
            return NotSupported(operation="cart_link")
        if not items:
            raise ValueError("Cart cannot be empty")
        quantities = defaultdict(int)
        for item in items:
            if item.product_id not in self._offers or not item.product_id.isdecimal():
                raise ValueError("Only previously normalized fixed-package SKUs may be exported")
            quantities[item.product_id] += item.package_count
        if len(quantities) > 100 or any(count > 40 for count in quantities.values()):
            raise ValueError("Cart exceeds upstream limits")
        data = self.client.call_tool("vkusvill_cart_link_create", {"products": [
            {"id": int(key), "q": count} for key, count in sorted(quantities.items())
        ]})
        link = data.get("link", "")
        parsed = urlparse(link)
        if parsed.scheme != "https" or parsed.hostname not in {"vkusvill.ru", "www.vkusvill.ru"} or parsed.username or parsed.password:
            raise ProviderUnavailable("invalid_cart_link")
        return link
