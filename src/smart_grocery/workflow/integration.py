"""Join the shared profile, catalogue, planning and store boundaries."""
from collections.abc import Sequence
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from functools import partial

from smart_grocery.agents.planner import MAX_CANDIDATES, plan_meals
from smart_grocery.schemas.foodcom import AllergenMetadata, Ingredient, IngredientBalance, Plan, Recipe, Request, Violation
from smart_grocery.schemas.integration import IntegrationResult, InventoryItem, MealPlan, ShoppingLine, ShoppingList, UserProfile
from smart_grocery.tools.budget_v2 import measure_plan
from smart_grocery.tools.grocery_provider import GroceryProvider, ProviderUnavailable
from smart_grocery.tools.inventory import available_inventory
from smart_grocery.tools.personalization import personalize_recipes
from smart_grocery.workflow.foodcom import run_candidate_loop


def _meets_allergy_constraint(item: AllergenMetadata, allergies: set[str]) -> bool:
    return not allergies or (
        item.allergens_status == "confirmed"
        and item.allergens is not None
        and allergies.isdisjoint(item.allergens)
    )


def _shop_for_ingredients(
    profile: UserProfile,
    balances: list[IngredientBalance],
    provider: GroceryProvider,
    violations: list[Violation],
    incomplete: bool,
) -> ShoppingList:
    lines = []
    subtotal = Decimal("0.00")
    allergies = set(profile.allergies)
    for balance in balances:
        missing = balance.missing_quantity
        if not missing:
            continue
        line = ShoppingLine(
            ingredient_id=balance.ingredient_id, unit=balance.unit,
            required_quantity=balance.required_quantity, inventory_quantity=balance.inventory_quantity,
            missing_quantity=missing,
        )
        lines.append(line)
        if not balance.unit_compatible:
            continue
        try:
            line.matched_offers = [
                offer for offer in provider.search_products(line.ingredient_id)
                if offer.ingredient_id == line.ingredient_id
            ]
        except ProviderUnavailable:
            violations.append(Violation(
                code="provider_unavailable", message=f"Product search unavailable for {line.ingredient_id}."
            ))
            incomplete = True
            continue
        choices = []
        for offer in line.matched_offers:
            if (offer.package_unit != line.unit or offer.currency != profile.currency
                    or offer.availability != "in_stock" or offer.price is None
                    or not _meets_allergy_constraint(offer, allergies)):
                continue
            count = int((missing / offer.package_quantity).to_integral_value(rounding=ROUND_CEILING))
            cost = (count * offer.price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            choices.append((cost, count * offer.package_quantity - missing, offer.retailer, offer.product_id, count, offer))
        if not choices:
            violations.append(Violation(
                code="no_compatible_offer", message=f"No eligible priced offer for {line.ingredient_id}."
            ))
            incomplete = True
            continue
        cost, _, _, _, count, offer = min(choices, key=lambda choice: choice[:4])
        line.selected_offer, line.package_count, line.estimated_total = offer, count, cost
        subtotal += cost

    if subtotal > profile.budget:
        violations.append(Violation(
            code="over_budget", message=f"Known cost exceeds budget by {subtotal - profile.budget:g} {profile.currency}."
        ))
    return ShoppingList(currency=profile.currency, lines=lines, priced_subtotal=subtotal,
                        estimated_total=None if incomplete else subtotal)


def run_integration_workflow(
    profile: UserProfile,
    inventory: Sequence[InventoryItem],
    recipes: Sequence[Recipe],
    provider: GroceryProvider,
    *,
    days: int,
    as_of: date | None = None,
    mock_planner: bool = False,
) -> IntegrationResult:
    today = as_of if as_of is not None else date.today()
    request = Request(
        days=days, people=profile.household_size, budget=profile.budget, currency=profile.currency,
        diet=profile.dietary_pattern, max_cook_minutes=profile.max_cooking_time,
        pantry=[Ingredient.model_validate(item, from_attributes=True)
                for item in available_inventory(inventory, as_of=today)],
    )
    request_data = request.model_dump(mode="json")
    request_data.update({
        "preferred_cuisines": profile.preferred_cuisines,
        "goals": profile.goals,
        "candidate_order": "descending_personalization_score_with_diversity",
    })
    personalization = personalize_recipes(
        profile, recipes, inventory, as_of=today, limit=MAX_CANDIDATES
    )
    candidates = personalization.ranked_recipes
    if not candidates:
        return IntegrationResult(violations=[
            Violation(code="no_candidates", message="No recipes match the profile and confirmed ingredient data.")
        ])

    def assess(raw_plan: dict) -> dict:
        parsed = Plan.model_validate(raw_plan)
        balances, violations, incomplete = measure_plan(request, parsed, candidates)
        shopping_list = _shop_for_ingredients(profile, balances, provider, violations, incomplete)
        return {
            "valid": not violations,
            "violations": violations,
            "feedback": "\n".join(issue.message for issue in violations),
            "shopping_list": shopping_list,
            "planned_ingredients": [
                Ingredient(ingredient_id=item.ingredient_id, quantity=item.required_quantity, unit=item.unit)
                for item in balances
            ],
        }

    planner = partial(plan_meals, mock=True) if mock_planner else None
    run = run_candidate_loop(request_data, candidates, assess, planner=planner)
    final = run["assessment"]
    return IntegrationResult(
        plan=MealPlan.model_validate({**run["plan"], "days": days, "planned_ingredients": final["planned_ingredients"]}),
        shopping_list=final["shopping_list"],
        candidate_ids=[recipe.recipe_id for recipe in candidates],
        violations=final["violations"],
        attempts=len(run["agent_trace"]),
        valid=final["valid"],
    )
