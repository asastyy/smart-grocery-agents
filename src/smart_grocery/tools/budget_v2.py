"""Food.com contract: deterministic quantities and costs; no LLM arithmetic."""
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP

from pydantic import ValidationError

from smart_grocery.schemas.foodcom import IngredientBalance, Plan, Price, Recipe, Request, Violation
# Preserve imports from the original Food.com module for existing callers.
from smart_grocery.schemas.foodcom import Ingredient as Ingredient, Meal as Meal, Model as Model


def money(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def measure_plan(req: Request, parsed: Plan, raw_recipes, *, slots=("lunch", "dinner")):
    """Validate meal slots and measure ingredient needs before applying prices."""
    violations: list[Violation] = []
    incomplete = False

    def fail(code, message, partial=False):
        nonlocal incomplete
        violations.append(Violation(code=code, message=message))
        incomplete |= partial

    recipes = {}
    for raw in raw_recipes:
        rid = raw.recipe_id if isinstance(raw, Recipe) else raw.get("recipe_id")
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

    balances = [
        IngredientBalance(ingredient_id=iid, unit=unit, required_quantity=qty,
                          inventory_quantity=pantry[iid, unit], unit_compatible=iid not in mismatches)
        for (iid, unit), qty in sorted(needed.items()) if qty
    ]
    return balances, violations, incomplete


def evaluate_plan(request, plan, catalog, *, slots=("lunch", "dinner")):
    """Estimate a Food.com plan using per-unit prices in the request currency."""
    try:
        req = Request.model_validate(request)
        parsed = Plan.model_validate(plan)
    except ValidationError:
        return {"valid": False, "total_cost": None, "priced_subtotal": 0.0,
                "shopping_list": [], "violations": [{"code": "invalid_input",
                "message": "Invalid request or plan: check quantities, days, people and units."}],
                "feedback": "Correct the request or plan before recalculating."}

    balances, issues, incomplete = measure_plan(req, parsed, catalog.get("recipes", []), slots=slots)
    violations = [issue.model_dump() for issue in issues]

    def fail(code, message, partial=False):
        nonlocal incomplete
        violations.append({"code": code, "message": message})
        incomplete |= partial

    shopping = []
    subtotal = Decimal(0)
    for balance in balances:
        iid, unit, missing = balance.ingredient_id, balance.unit, balance.missing_quantity
        if not missing:
            continue
        line = {"ingredient_id": iid, "quantity": float(missing), "unit": unit,
                "unit_price": None, "cost": None}
        shopping.append(line)
        if not balance.unit_compatible:
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
