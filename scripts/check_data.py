"""Валидация data/*.csv|jsonl перед сдачей. Запуск: python scripts/check_data.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smart_grocery.tools.recipes import load_ingredients, load_prices, load_recipes


def main() -> int:
    errors: list[str] = []
    ingredients = load_ingredients()
    prices = load_prices()
    recipes = load_recipes()

    if not 30 <= len(recipes) <= 200:
        errors.append(f"recipes: {len(recipes)}, ожидается 30-200")
    if not 30 <= len(prices) <= 2000:
        errors.append(f"prices: {len(prices)}, ожидается 30-2000")

    ids = [r["recipe_id"] for r in recipes]
    if len(ids) != len(set(ids)):
        errors.append("дубли recipe_id")

    for r in recipes:
        if not 10 <= r["cook_minutes"] <= 30:
            errors.append(f"{r['recipe_id']}: cook_minutes={r['cook_minutes']}")
        if len(r["ingredients"]) < 3:
            errors.append(f"{r['recipe_id']}: <3 ингредиентов")
        for i in r["ingredients"]:
            if i["ingredient_id"] not in ingredients:
                errors.append(f"{r['recipe_id']}: unknown ingredient {i['ingredient_id']}")
            if i["unit"] not in {"g", "ml", "pcs"}:
                errors.append(f"{r['recipe_id']}: bad unit {i['unit']}")
            if i["quantity"] <= 0:
                errors.append(f"{r['recipe_id']}: quantity<=0")

    for iid, p in prices.items():
        if iid not in ingredients:
            errors.append(f"price for unknown ingredient {iid}")
        elif p["unit"] != ingredients[iid]["base_unit"]:
            errors.append(f"{iid}: price unit {p['unit']} != base {ingredients[iid]['base_unit']}")
        if p["price_per_unit"] <= 0:
            errors.append(f"{iid}: price<=0")

    if errors:
        print("FAIL")
        for e in errors:
            print(" -", e)
        return 1

    print(f"OK: {len(recipes)} recipes, {len(ingredients)} ingredients, {len(prices)} prices")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
