import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smart_grocery.tools.recipes import (  # noqa: E402
    load_ingredients,
    load_prices,
    load_recipes,
    search_recipes,
)

DATA = ROOT / "data"

REQUEST_BASIC = {
    "pantry": [
        {"ingredient_id": "rice", "quantity": 500, "unit": "g"},
        {"ingredient_id": "egg", "quantity": 4, "unit": "pcs"},
    ],
    "budget": 25.0,
    "currency": "CU",
    "days": 3,
    "people": 2,
    "diet": ["vegetarian"],
    "max_cook_minutes": 30,
}


def test_base_request_returns_at_least_five_candidates():
    candidates = search_recipes(REQUEST_BASIC)["candidates"]
    assert len(candidates) >= 5
    assert all("vegetarian" in c["tags"] for c in candidates)
    assert all(c["cook_minutes"] <= 30 for c in candidates)


def test_sorting_prefers_more_pantry_overlap():
    """Первым идёт рецепт с максимальным покрытием pantry (без привязки к id)."""
    candidates = search_recipes(REQUEST_BASIC)["candidates"]
    assert len(candidates) >= 5

    pantry_ids = {p["ingredient_id"] for p in REQUEST_BASIC["pantry"]}
    overlaps = []
    for c in candidates:
        ing = {i["ingredient_id"] for i in c["ingredients"]}
        overlaps.append(len(ing & pantry_ids))

    assert max(overlaps) > 0, "ни один кандидат не содержит ингредиент из pantry"
    assert overlaps[0] == max(overlaps), \
        f"сортировка сломана: первый {overlaps[0]}, максимум {max(overlaps)}"


def test_impossible_max_cook_returns_empty():
    request = {**REQUEST_BASIC, "max_cook_minutes": 1}
    assert search_recipes(request) == {"candidates": []}


def test_diet_filter_works():
    request = {**REQUEST_BASIC, "diet": ["vegan"]}
    assert search_recipes(request) == {"candidates": []}


def test_all_units_and_ingredients_are_canonical():
    ingredients = load_ingredients(DATA / "ingredients.csv")
    for recipe in load_recipes(DATA / "recipes.jsonl"):
        assert recipe["recipe_id"].startswith("r")
        for ing in recipe["ingredients"]:
            assert ing["unit"] in {"g", "ml", "pcs"}, (recipe["recipe_id"], ing)
            assert ing["ingredient_id"] in ingredients, (recipe["recipe_id"], ing)


def test_recipes_and_prices_are_consistent():
    ingredients = load_ingredients(DATA / "ingredients.csv")
    prices = load_prices(DATA / "prices.csv")
    assert len(prices) >= 30
    for iid, price in prices.items():
        assert iid in ingredients, iid
        assert price["unit"] == ingredients[iid]["base_unit"], iid
        assert price["price_per_unit"] > 0, iid


def test_recipe_ids_are_unique():
    recipes = load_recipes(DATA / "recipes.jsonl")
    ids = [r["recipe_id"] for r in recipes]
    assert len(ids) == len(set(ids))
    assert len(recipes) >= 30


def test_empty_pantry_does_not_crash():
    request = {**REQUEST_BASIC, "pantry": []}
    candidates = search_recipes(request)["candidates"]
    assert len(candidates) >= 5


def test_empty_diet_returns_all_within_time():
    request = {**REQUEST_BASIC, "diet": []}
    candidates = search_recipes(request)["candidates"]
    assert len(candidates) == len(load_recipes(DATA / "recipes.jsonl"))
