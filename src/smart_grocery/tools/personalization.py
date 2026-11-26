"""Role 2: hard filtering and explainable soft ranking without an LLM."""
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from smart_grocery.schemas.foodcom import Recipe
from smart_grocery.schemas.integration import InventoryItem, UserProfile
from smart_grocery.schemas.personalization import PersonalizationResult, RecipeDecision
from smart_grocery.tools.inventory import available_inventory


def _normalise(values: Sequence[str]) -> set[str]:
    return {value.casefold().strip() for value in values if value.strip()}


def evaluate_recipe(
    profile: UserProfile,
    recipe: Recipe,
    inventory: Sequence[InventoryItem] = (),
    *,
    as_of: date | None = None,
) -> RecipeDecision:
    """Apply safety constraints first, then score preferences and usable stock."""
    ingredient_ids = {item.ingredient_id for item in recipe.ingredients}
    hard_reasons: list[str] = []
    allergies = set(profile.allergies)

    if allergies:
        if allergies.intersection(ingredient_ids):
            hard_reasons.append("allergen_ingredient_conflict")
        elif recipe.allergens_status != "confirmed" or recipe.allergens is None:
            hard_reasons.append("allergen_data_unknown")
        elif allergies.intersection(recipe.allergens):
            hard_reasons.append("allergen_conflict")
    if set(profile.disliked_ingredients).intersection(ingredient_ids):
        hard_reasons.append("disliked_ingredient")
    required_diets = _normalise(profile.dietary_pattern)
    if required_diets and not required_diets.issubset(_normalise(recipe.tags)):
        hard_reasons.append("dietary_pattern_mismatch")
    if recipe.cook_minutes > profile.max_cooking_time:
        hard_reasons.append("cooking_time_exceeded")
    if hard_reasons:
        return RecipeDecision(recipe_id=recipe.recipe_id, eligible=False, hard_reasons=hard_reasons)

    score = Decimal("0")
    soft_reasons: list[str] = []
    preferred_cuisines = _normalise(profile.preferred_cuisines)
    if recipe.cuisine and recipe.cuisine.casefold() in preferred_cuisines:
        score += Decimal("3")
        soft_reasons.append("preferred_cuisine")
    matched_goals = _normalise(profile.goals).intersection(_normalise(recipe.tags))
    if matched_goals:
        score += Decimal(2 * len(matched_goals))
        soft_reasons.append("goal_match")

    today = as_of or date.today()
    usable = available_inventory(inventory, as_of=today)
    recipe_keys = {(item.ingredient_id, item.unit) for item in recipe.ingredients}
    stocked_keys = {(item.ingredient_id, item.unit) for item in usable}
    covered = recipe_keys.intersection(stocked_keys)
    if covered:
        score += Decimal(len(covered))
        soft_reasons.append("uses_inventory")
    expiring_keys = {
        (item.ingredient_id, item.unit) for item in usable
        if item.expiry_date is not None and 0 <= (item.expiry_date - today).days <= 3
    }
    expiring = recipe_keys.intersection(expiring_keys)
    if expiring:
        score += Decimal(2 * len(expiring))
        soft_reasons.append("uses_expiring_inventory")
    opened_keys = {(item.ingredient_id, item.unit) for item in usable if item.opened is True}
    if recipe_keys.intersection(opened_keys):
        score += Decimal("0.5")
        soft_reasons.append("uses_opened_inventory")
    score -= Decimal(len(recipe_keys - stocked_keys)) / Decimal("10")
    return RecipeDecision(
        recipe_id=recipe.recipe_id,
        eligible=True,
        score=score,
        soft_reasons=soft_reasons,
    )


def personalize_recipes(
    profile: UserProfile,
    recipes: Sequence[Recipe],
    inventory: Sequence[InventoryItem] = (),
    *,
    as_of: date | None = None,
    limit: int | None = None,
) -> PersonalizationResult:
    """Return an auditable result; an LLM may only arrange the returned recipes."""
    pairs = [(recipe, evaluate_recipe(profile, recipe, inventory, as_of=as_of)) for recipe in recipes]
    remaining = [(recipe, decision) for recipe, decision in pairs if decision.eligible]
    ranked: list[Recipe] = []
    cuisine_counts: dict[str, int] = {}
    meal_type_counts: dict[str, int] = {}
    while remaining:
        def rank_key(pair):
            recipe, decision = pair
            cuisine = (recipe.cuisine or "").casefold()
            meal_type = (recipe.meal_type or "").casefold()
            diversity_penalty = Decimal("0.5") * cuisine_counts.get(cuisine, 0) if cuisine else Decimal(0)
            diversity_penalty += Decimal("0.25") * meal_type_counts.get(meal_type, 0) if meal_type else Decimal(0)
            return (-(decision.score - diversity_penalty), recipe.cook_minutes, recipe.recipe_id)

        chosen = min(remaining, key=rank_key)
        remaining.remove(chosen)
        recipe, _ = chosen
        ranked.append(recipe)
        if recipe.cuisine:
            key = recipe.cuisine.casefold()
            cuisine_counts[key] = cuisine_counts.get(key, 0) + 1
        if recipe.meal_type:
            key = recipe.meal_type.casefold()
            meal_type_counts[key] = meal_type_counts.get(key, 0) + 1
    if limit is not None:
        ranked = ranked[:limit]
    decisions_by_id = {decision.recipe_id: decision for _, decision in pairs}
    ordered_decisions = [decisions_by_id[recipe.recipe_id] for recipe in ranked]
    ordered_ids = {decision.recipe_id for decision in ordered_decisions}
    ordered_decisions.extend(
        decision for _, decision in pairs if decision.recipe_id not in ordered_ids
    )
    return PersonalizationResult(ranked_recipes=ranked, decisions=ordered_decisions)
