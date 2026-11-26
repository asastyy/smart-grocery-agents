"""Retail metadata extends, rather than duplicates, the sprint contracts."""
from decimal import Decimal
from typing import Literal

from pydantic import Field

from smart_grocery.schemas.foodcom import Model
from smart_grocery.schemas.integration import ProductOffer


class RetailOffer(ProductOffer):
    package_source: str
    price_source: str
    availability_scope: Literal["unknown", "delivery_context"] = "unknown"
    warnings: list[str] = Field(default_factory=list)


class MatchDecision(Model):
    status: Literal["accepted", "review", "rejected"]
    method: Literal["exact", "alias", "fuzzy", "rule"]
    reason: str


class NormalizationIssue(Model):
    product_id: str
    code: str
    message: str


class PackageQuote(Model):
    product_id: str
    required_quantity: Decimal
    package_count: int
    purchased_quantity: Decimal
    surplus_quantity: Decimal
    total: Decimal
    currency: str
