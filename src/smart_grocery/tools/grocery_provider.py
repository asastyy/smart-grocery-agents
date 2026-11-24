"""Provider boundary and a fixture-backed implementation for offline work."""
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter

from smart_grocery.schemas.foodcom import Model
from smart_grocery.schemas.integration import Availability, ProductOffer


class NotSupported(Model):
    status: Literal["not_supported"] = "not_supported"
    operation: str


class CartItem(Model):
    product_id: str = Field(min_length=1)
    package_count: int = Field(ge=1)


class ProviderUnavailable(Exception):
    """A provider could not supply offers for this request."""


class GroceryProvider(ABC):
    @abstractmethod
    def search_products(self, ingredient_id: str) -> list[ProductOffer]:
        """Return offers matched to the requested canonical ingredient."""

    @abstractmethod
    def get_product_details(self, product_id: str) -> ProductOffer | None:
        """Return a SKU by ID, or None when there is no matching product."""

    @abstractmethod
    def check_availability(self, product_id: str) -> Availability:
        """Return stock status for the provider's configured context."""

    def create_cart(self, items: Sequence[CartItem]) -> str | NotSupported:
        return NotSupported(operation="create_cart")

    def cart_link(self, items: Sequence[CartItem]) -> str | NotSupported:
        return NotSupported(operation="cart_link")


class MockGroceryProvider(GroceryProvider):
    def __init__(self, offers: Iterable[ProductOffer]):
        self._offers: dict[str, ProductOffer] = {}
        for offer in offers:
            if offer.product_id in self._offers:
                raise ValueError(f"Duplicate mock product ID: {offer.product_id}")
            self._offers[offer.product_id] = offer

    @classmethod
    def from_file(cls, path: Path):
        return cls(TypeAdapter(list[ProductOffer]).validate_json(path.read_bytes()))

    def search_products(self, ingredient_id: str) -> list[ProductOffer]:
        return [offer for offer in self._offers.values() if offer.ingredient_id == ingredient_id]

    def get_product_details(self, product_id: str) -> ProductOffer | None:
        return self._offers.get(product_id)

    def check_availability(self, product_id: str) -> Availability:
        offer = self.get_product_details(product_id)
        return offer.availability if offer is not None else "unknown"
