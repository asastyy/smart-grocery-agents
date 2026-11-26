"""Compare five profiles on the same reviewed recipe pool without external calls."""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from smart_grocery.schemas.integration import UserProfile
from smart_grocery.tools.inventory import available_inventory
from smart_grocery.tools.personalization import personalize_recipes
from smart_grocery.workflow.golden import load_golden_case


if __name__ == "__main__":
    case, _ = load_golden_case()
    profiles = [
        UserProfile.model_validate(item)
        for item in json.loads((ROOT / "fixtures/personalization/profiles.json").read_text(encoding="utf-8"))
    ]
    report = []
    for profile in profiles:
        result = personalize_recipes(
            profile, case.recipes, case.inventory, as_of=date(2026, 11, 26)
        )
        preview = result.ranked_recipes[:3]
        preview_keys = {
            (ingredient.ingredient_id, ingredient.unit)
            for recipe in preview for ingredient in recipe.ingredients
        }
        stock_keys = {
            (item.ingredient_id, item.unit)
            for item in available_inventory(case.inventory, as_of=date(2026, 11, 26))
        }
        preferred = {value.casefold() for value in profile.preferred_cuisines}
        report.append({
            "profile": profile.user_id,
            "preview_menu_recipe_ids": [recipe.recipe_id for recipe in preview],
            "ranked_recipe_ids": [recipe.recipe_id for recipe in result.ranked_recipes],
            "metrics": {
                "hard_excluded": sum(not decision.eligible for decision in result.decisions),
                "preferred_cuisine_in_preview": sum(
                    bool(recipe.cuisine and recipe.cuisine.casefold() in preferred) for recipe in preview
                ),
                "inventory_ingredient_coverage": (
                    round(len(preview_keys & stock_keys) / len(preview_keys), 3) if preview_keys else 0
                ),
            },
            "excluded": {
                decision.recipe_id: decision.hard_reasons
                for decision in result.decisions if not decision.eligible
            },
        })
    print(json.dumps(report, ensure_ascii=False, indent=2))
