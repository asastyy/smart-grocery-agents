"""Food.com contract: deterministic quantities and costs; no LLM arithmetic."""
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class Ingredient(Model):
    ingredient_id: str = Field(min_length=1)
    quantity: Decimal = Field(ge=0)
    unit: Literal["g", "ml", "pcs"]


class Request(Model):
    pantry: list[Ingredient] = Field(default_factory=list)
    budget: Decimal = Field(ge=0)
    currency: str = "CU"
    days: int = Field(ge=1, le=7)
    people: int = Field(ge=1)
    diet: list[str] = Field(default_factory=list)
    max_cook_minutes: int = Field(default=30, ge=1)


class Recipe(Model):
    recipe_id: str
    title: str
    servings: Decimal = Field(gt=0)
    cook_minutes: int = Field(ge=0)
    tags: list[str]
    ingredients: list[Ingredient] = Field(min_length=1)


class Meal(Model):
    day: int = Field(ge=1)
    slot: str
    recipe_id: str
    servings: Decimal = Field(gt=0)


class Plan(Model):
    meals: list[Meal]


class Price(Model):
    unit: Literal["g", "ml", "pcs"]
    price_per_unit: Decimal = Field(ge=0)
    currency: str


def money(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def evaluate_plan(request, plan, catalog, *, slots=("lunch", "dinner")):
    """catalog = {recipes: candidate list, prices: ID -> price record}.

    Unknown quantities/prices never become zero-cost purchases: return null total,
    a priced subtotal, and explicit violations. Unit conversions are not guessed.
    """
    violations = []
    incomplete = False

    def fail(code, message, partial=False):
        nonlocal incomplete
        violations.append({"code": code, "message": message})
        incomplete |= partial

    try:
        req = Request.model_validate(request)
        parsed = Plan.model_validate(plan)
    except ValidationError:
        return {"valid": False, "total_cost": None, "priced_subtotal": 0.0,
                "shopping_list": [], "violations": [{"code": "invalid_input",
                "message": "Invalid request or plan: check quantities, days, people and units."}],
                "feedback": "Correct the request or plan before recalculating."}

    recipes = {}
    for raw in catalog.get("recipes", []):
        rid = raw.get("recipe_id")
        if rid in recipes:
            fail("duplicate_recipe", f"Duplicate recipe ID: {rid}", True)
        recipes[rid] = raw
    expected = {(day, slot) for day in range(1, req.days + 1) for slot in slots}
    actual = Counter((m.day, m.slot) for m in parsed.meals)
    if set(actual) != expected or any(n != 1 for n in actual.values()):
        fail("meal_slots", "Provide exactly one lunch and one dinner per day (or the explicitly requested slots).")

    needed = defaultdict(Decimal)
    units = defaultdict(set)
    for meal in parsed.meals:
        if meal.servings != req.people:
            fail("servings_mismatch", f"{meal.recipe_id}: servings must equal people ({req.people}).")
        if meal.recipe_id not in recipes:
            fail("unknown_recipe", f"Unknown candidate recipe: {meal.recipe_id}", True)
            continue
        try:
            recipe = Recipe.model_validate(recipes[meal.recipe_id])
        except ValidationError:
            fail("invalid_recipe", f"Invalid ingredient, unit or servings in {meal.recipe_id}", True)
            continue
        if not set(req.diet) <= set(recipe.tags):
            fail("diet_mismatch", f"Recipe {meal.recipe_id} does not meet diet tags.")
        if recipe.cook_minutes > req.max_cook_minutes:
            fail("cook_time", f"Recipe {meal.recipe_id} exceeds cooking time.")
        for ingredient in recipe.ingredients:
            needed[ingredient.ingredient_id, ingredient.unit] += (
                ingredient.quantity * meal.servings / recipe.servings)
            units[ingredient.ingredient_id].add(ingredient.unit)

    pantry = defaultdict(Decimal)
    for ingredient in req.pantry:
        pantry[ingredient.ingredient_id, ingredient.unit] += ingredient.quantity
        if ingredient.ingredient_id in units:
            units[ingredient.ingredient_id].add(ingredient.unit)
    mismatches = {iid for iid, values in units.items() if len(values) > 1}
    for iid in sorted(mismatches):
        fail("unit_mismatch", f"Incompatible recipe/pantry units for {iid}; no conversion assumed.", True)

    shopping = []
    subtotal = Decimal(0)
    for (iid, unit), qty in sorted(needed.items()):
        missing = max(Decimal(0), qty - pantry[iid, unit])
        if not missing:
            continue
        line = {"ingredient_id": iid, "quantity": float(missing), "unit": unit,
                "unit_price": None, "cost": None}
        shopping.append(line)
        if iid in mismatches:
            continue
        raw = catalog.get("prices", {}).get(iid)
        if raw is None:
            fail("missing_price", f"Unknown price for {iid}", True)
            continue
        try:
            price = Price.model_validate(raw)
        except ValidationError:
            fail("invalid_price", f"Invalid price for {iid}", True)
            continue
        if price.unit != unit or price.currency != req.currency:
            fail("price_mismatch", f"Price unit/currency mismatch for {iid}", True)
            continue
        cost = (missing * price.price_per_unit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal += cost
        line.update(unit_price=float(price.price_per_unit), cost=float(cost))
    if subtotal > req.budget:
        fail("over_budget", f"Known cost exceeds budget by {money(subtotal - req.budget)} {req.currency}.")
    if incomplete:
        fail("incomplete_cost", "Total cost is unknown; priced_subtotal excludes unpriced or invalid quantities.")
    return {"valid": not violations, "total_cost": None if incomplete else money(subtotal),
            "priced_subtotal": money(subtotal), "shopping_list": shopping,
            "violations": violations, "feedback": "\n".join(v["message"] for v in violations)}
