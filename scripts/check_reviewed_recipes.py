"""Verify pinned sources, overlays, scaling and fail-closed allergy handling offline."""
import argparse
import json
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from smart_grocery.catalog.reviewed import load_reviewed_records, reviewed_planning_recipes, scale_recipe
from smart_grocery.schemas.foodcom import Meal, Plan, Request
from smart_grocery.tools.budget_v2 import measure_plan
from smart_grocery.tools.personalization import personalize_recipes
from smart_grocery.workflow.golden import load_golden_case


def check():
    rows, recipes = load_reviewed_records(), reviewed_planning_recipes()
    if len(recipes) != 50:
        raise ValueError('The reviewed release must contain exactly 50 recipes')
    examples = []
    for recipe in recipes:
        for people in (1, 2, 4, 7):
            expected = scale_recipe(recipe, people)
            request = Request(pantry=[], budget=0, days=1, people=people, max_cook_minutes=2000)
            slot = recipe.meal_slots[0]
            plan = Plan(meals=[Meal(day=1, slot=slot, recipe_id=recipe.recipe_id, servings=people)])
            balances, violations, incomplete = measure_plan(request, plan, [recipe], slots=(slot,))
            if incomplete or violations or any(b.required_quantity != item.quantity or b.missing_quantity != item.quantity
                                              for b, item in zip(balances, expected)):
                raise ValueError(f'Scaling/deficit failure: {recipe.recipe_id} / {people}')
        examples.append({'recipe_id': recipe.recipe_id, 'source_servings': str(recipe.servings),
                         'ingredients': len(recipe.ingredients), 'meal_slots': recipe.meal_slots})
    case, _ = load_golden_case()
    case.profile.max_cooking_time = 2000
    for allergy in ('peanut', 'milk', 'egg', 'wheat', 'soy', 'unknown_allergen'):
        profile = case.profile.model_copy(update={'allergies': [allergy]})
        if personalize_recipes(profile, recipes).ranked_recipes:
            raise ValueError('Unknown allergen metadata bypassed the strict filter')
    return {'checked_on': str(date.today()), 'recipes': len(recipes),
            'source_audited_not_cooking_tested': True, 'human_cooking_validation': 'not_performed',
            'allergen_confirmed': 0, 'allergy_profiles_blocked': 6,
            'dish_types': dict(Counter(row['dish_type'] for row in rows)),
            'scaling_and_missing_cases': 4 * len(recipes),
            'portion_sizes_checked': [1, 2, 4, 7], 'sources_unchanged': True,
            'prices': 'not_verified_and_not_fabricated', 'details': examples}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-report', action='store_true')
    args = parser.parse_args()
    report = check()
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.write_report:
        (ROOT / 'data/reviewed/medlineplus/validation.json').write_text(text, encoding='utf-8')
    print(text)
