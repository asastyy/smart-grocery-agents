"""Contracts for deterministic personalization and confirmed inventory updates."""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from smart_grocery.schemas.foodcom import CanonicalId, Model, Recipe, Unit
from smart_grocery.schemas.integration import InventoryItem


class RecipeDecision(Model):
    recipe_id: str
    eligible: bool
    hard_reasons: list[str] = Field(default_factory=list)
    score: Decimal = Decimal("0")
    soft_reasons: list[str] = Field(default_factory=list)


class PersonalizationResult(Model):
    ranked_recipes: list[Recipe] = Field(default_factory=list)
    decisions: list[RecipeDecision] = Field(default_factory=list)


class InventorySuggestion(Model):
    suggestion_id: str
    ingredient_id: CanonicalId
    display_name: str = Field(min_length=1)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: Unit | None = None
    source: Literal["purchase_history", "receipt", "barcode", "photo"]
    confidence: Decimal = Field(ge=0, lt=1)
    purchased_at: datetime | None = None
    expiry_date: date | None = None


class InventoryAllocation(Model):
    inventory_item_id: str
    ingredient_id: CanonicalId
    quantity: Decimal = Field(gt=0)
    unit: Unit


class InventoryShortage(Model):
    ingredient_id: CanonicalId
    quantity: Decimal = Field(gt=0)
    unit: Unit


class ConsumptionPlan(Model):
    allocations: list[InventoryAllocation] = Field(default_factory=list)
    shortages: list[InventoryShortage] = Field(default_factory=list)


class InventoryEvent(Model):
    inventory_item_id: str
    ingredient_id: CanonicalId
    action: Literal["consume", "deplete"]
    quantity: Decimal = Field(gt=0)
    unit: Unit


class InventoryUpdate(Model):
    inventory: list[InventoryItem]
    events: list[InventoryEvent] = Field(default_factory=list)
