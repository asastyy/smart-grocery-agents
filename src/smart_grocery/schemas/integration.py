"""Sprint boundaries built on the active Food.com quantities and meal slots."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, HttpUrl

from smart_grocery.schemas.foodcom import (
    AllergenMetadata, CanonicalId, Ingredient, Model, Plan, Unit, Violation,
)


Availability = Literal["in_stock", "out_of_stock", "unknown"]


class UserProfile(Model):
    user_id: str = Field(min_length=1)
    household_size: int = Field(ge=1)
    allergies: list[CanonicalId] = Field(default_factory=list)
    dietary_pattern: list[str] = Field(default_factory=list)
    disliked_ingredients: list[CanonicalId] = Field(default_factory=list)
    preferred_cuisines: list[str] = Field(default_factory=list)
    goals: list[str] = Field(default_factory=list)
    budget: Decimal = Field(ge=0)
    currency: str = Field(default="RUB", pattern=r"^[A-Z]{2,3}$")
    max_cooking_time: int = Field(ge=1)


class InventoryItem(Ingredient):
    inventory_item_id: str | None = None
    display_name: str = Field(min_length=1)
    expiry_date: date | None = None
    opened: bool | None = None
    status: Literal["available", "reserved", "depleted", "discarded"] = "available"
    source: str = Field(min_length=1)
    confidence: Decimal = Field(ge=0, le=1)


class MealPlan(Plan):
    days: int = Field(ge=1, le=7)
    planned_ingredients: list[Ingredient] = Field(default_factory=list)
    reasoning_summary: str = ""


class ProductOffer(AllergenMetadata):
    retailer: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    ingredient_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    brand: str | None = None
    package_quantity: Decimal = Field(gt=0)
    package_unit: Unit
    price: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(pattern=r"^[A-Z]{2,3}$")
    availability: Availability = "unknown"
    url: HttpUrl | None = None
    retrieved_at: AwareDatetime
    ingredients: str | None = None
    nutrition: dict[str, Decimal] | None = None


class ShoppingLine(Model):
    ingredient_id: str
    unit: Unit
    required_quantity: Decimal = Field(gt=0)
    inventory_quantity: Decimal = Field(ge=0)
    missing_quantity: Decimal = Field(gt=0)
    matched_offers: list[ProductOffer] = Field(default_factory=list)
    selected_offer: ProductOffer | None = None
    package_count: int | None = Field(default=None, ge=1)
    estimated_total: Decimal | None = Field(default=None, ge=0)


class ShoppingList(Model):
    currency: str
    lines: list[ShoppingLine] = Field(default_factory=list)
    priced_subtotal: Decimal = Field(ge=0)
    estimated_total: Decimal | None = Field(default=None, ge=0)


class IntegrationResult(Model):
    plan: MealPlan | None = None
    shopping_list: ShoppingList | None = None
    candidate_ids: list[str] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    attempts: int = Field(default=0, ge=0)
    valid: bool = False
