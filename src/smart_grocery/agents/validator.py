from smart_grocery.schemas.models import PlanningRequest, PlanningResult, Recipe
from smart_grocery.tools.budget import evaluate_menu

def validate_plan(request: PlanningRequest, recipes: list[Recipe], selected: list[str]) -> PlanningResult:
    return evaluate_menu(request, recipes, selected)
