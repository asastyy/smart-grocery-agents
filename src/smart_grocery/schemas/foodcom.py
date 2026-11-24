"""Shared Food.com inputs consumed by the planner and Python validator."""
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


Unit = Literal["g", "ml", "pcs"]
CanonicalId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")]


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class AllergenMetadata(Model):
    allergens_status: Literal["unknown", "confirmed"] = "unknown"
    allergens: list[CanonicalId] | None = None

    @model_validator(mode="after")
    def require_confirmed_list(self):
        if self.allergens_status == "confirmed" and self.allergens is None:
            raise ValueError("confirmed allergens require an explicit list")
        return self


class Ingredient(Model):
    ingredient_id: str = Field(min_length=1)
    quantity: Decimal = Field(ge=0)
    unit: Unit


class Request(Model):
    pantry: list[Ingredient] = Field(default_factory=list)
    budget: Decimal = Field(ge=0)
    currency: str = "CU"
    days: int = Field(ge=1, le=7)
    people: int = Field(ge=1)
    diet: list[str] = Field(default_factory=list)
    max_cook_minutes: int = Field(default=30, ge=1)


class Recipe(AllergenMetadata):
    recipe_id: str
    title: str
    servings: Decimal = Field(gt=0)
    cook_minutes: int = Field(ge=0)
    tags: list[str]
    ingredients: list[Ingredient] = Field(min_length=1)
    instructions: list[str] | None = None
    cuisine: str | None = None
    meal_type: str | None = None
    nutrition: dict[str, Decimal] | None = None
    source: str | None = None


class Meal(Model):
    day: int = Field(ge=1)
    slot: str
    recipe_id: str
    servings: Decimal = Field(gt=0)


class Plan(Model):
    meals: list[Meal]


class Price(Model):
    unit: Unit
    price_per_unit: Decimal = Field(ge=0)
    currency: str


class IngredientBalance(Model):
    ingredient_id: str
    unit: Unit
    required_quantity: Decimal = Field(gt=0)
    inventory_quantity: Decimal = Field(ge=0)
    unit_compatible: bool = True

    @property
    def missing_quantity(self) -> Decimal:
        return max(Decimal(0), self.required_quantity - self.inventory_quantity)


class Violation(Model):
    code: str
    message: str
