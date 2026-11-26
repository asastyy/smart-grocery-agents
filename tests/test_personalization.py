from datetime import date, timedelta
from decimal import Decimal

from smart_grocery.schemas.foodcom import Recipe
from smart_grocery.schemas.integration import InventoryItem, UserProfile
from smart_grocery.tools.personalization import evaluate_recipe, personalize_recipes


TODAY = date(2026, 11, 26)


def profile(**updates):
    values = {
        "user_id": "test-user",
        "household_size": 2,
        "allergies": [],
        "dietary_pattern": [],
        "disliked_ingredients": [],
        "preferred_cuisines": [],
        "goals": [],
        "budget": 3000,
        "currency": "RUB",
        "max_cooking_time": 40,
    }
    values.update(updates)
    return UserProfile.model_validate(values)


def recipe(recipe_id, ingredients, **updates):
    values = {
        "recipe_id": recipe_id,
        "title": recipe_id,
        "servings": 2,
        "cook_minutes": 20,
        "tags": [],
        "ingredients": [
            {"ingredient_id": ingredient, "quantity": 100, "unit": "g"}
            for ingredient in ingredients
        ],
        "allergens_status": "confirmed",
        "allergens": [],
    }
    values.update(updates)
    return Recipe.model_validate(values)


def stock(ingredient_id, *, expiry_days=None):
    return InventoryItem(
        inventory_item_id=f"stock-{ingredient_id}", ingredient_id=ingredient_id,
        display_name=ingredient_id, quantity=200, unit="g", source="manual",
        confidence=1, expiry_date=TODAY + timedelta(days=expiry_days) if expiry_days is not None else None,
    )


def test_hard_constraints_are_applied_before_ranking():
    user = profile(
        allergies=["peanut"], dietary_pattern=["vegetarian"],
        disliked_ingredients=["cilantro"], max_cooking_time=25,
    )
    cases = [
        recipe("allergen", ["rice"], allergens=["peanut"], tags=["vegetarian"]),
        recipe("unknown", ["rice"], allergens_status="unknown", allergens=None, tags=["vegetarian"]),
        recipe("disliked", ["cilantro"], tags=["vegetarian"]),
        recipe("diet", ["rice"]),
        recipe("slow", ["rice"], tags=["vegetarian"], cook_minutes=30),
        recipe("safe", ["rice"], tags=["vegetarian"]),
    ]
    result = personalize_recipes(user, cases, as_of=TODAY)
    assert [item.recipe_id for item in result.ranked_recipes] == ["safe"]
    reasons = {item.recipe_id: item.hard_reasons for item in result.decisions}
    assert reasons["allergen"] == ["allergen_conflict"]
    assert reasons["unknown"] == ["allergen_data_unknown"]
    assert reasons["disliked"] == ["disliked_ingredient"]
    assert reasons["diet"] == ["dietary_pattern_mismatch"]
    assert reasons["slow"] == ["cooking_time_exceeded"]


def test_missing_soft_metadata_is_neutral_and_stable():
    result = personalize_recipes(profile(preferred_cuisines=["asian"]), [
        recipe("without-cuisine", ["rice"]),
        recipe("asian", ["rice"], cuisine="asian"),
    ], as_of=TODAY)
    assert [item.recipe_id for item in result.ranked_recipes] == ["asian", "without-cuisine"]
    assert evaluate_recipe(profile(), recipe("plain", ["rice"]), as_of=TODAY).eligible


def test_inventory_and_expiry_are_soft_ranking_signals():
    recipes = [recipe("rice", ["rice"]), recipe("beans", ["beans"])]
    result = personalize_recipes(
        profile(), recipes, [stock("rice", expiry_days=2), stock("beans", expiry_days=10)], as_of=TODAY
    )
    assert [item.recipe_id for item in result.ranked_recipes] == ["rice", "beans"]
    assert "uses_expiring_inventory" in result.decisions[0].soft_reasons


def test_five_profiles_produce_auditable_different_rankings():
    recipes = [
        recipe("asian-fast", ["rice"], cuisine="asian", tags=["high_protein"], cook_minutes=15),
        recipe("italian", ["tomato"], cuisine="italian", tags=["vegetarian"], cook_minutes=30),
        recipe("slow", ["beans"], cuisine="mexican", tags=["vegan"], cook_minutes=50),
    ]
    profiles = [
        profile(preferred_cuisines=["asian"]),
        profile(preferred_cuisines=["italian"]),
        profile(dietary_pattern=["vegan"], max_cooking_time=60),
        profile(max_cooking_time=20),
        profile(goals=["high_protein"]),
    ]
    rankings = [tuple(item.recipe_id for item in personalize_recipes(p, recipes, as_of=TODAY).ranked_recipes)
                for p in profiles]
    assert rankings[0][0] == "asian-fast"
    assert rankings[1][0] == "italian"
    assert rankings[2] == ("slow",)
    assert rankings[3] == ("asian-fast",)
    assert rankings[4][0] == "asian-fast"
    assert len(set(rankings)) >= 4
