import json
from pathlib import Path
from smart_grocery.schemas.models import PlanningRequest, Recipe

DATA = Path(__file__).resolve().parents[3] / "examples" / "recipes.json"

def search_recipes(request: PlanningRequest) -> list[Recipe]:
    recipes = [Recipe.model_validate(r) for r in json.loads(DATA.read_text(encoding="utf-8"))]
    if request.diet == "vegetarian":
        recipes = [r for r in recipes if "vegetarian" in r.tags]
    if request.diet == "vegan":
        recipes = [r for r in recipes if "vegan" in r.tags]
    return recipes
