from smart_grocery.schemas.models import PlanningRequest, PlanningResult
from smart_grocery.tools.legacy_recipes import search_recipes
from smart_grocery.agents.planner import propose_menu
from smart_grocery.agents.validator import validate_plan

def run_workflow(request: PlanningRequest) -> PlanningResult:
    recipes = search_recipes(request)
    if not recipes: raise ValueError("No eligible recipes")
    feedback = None
    for _ in range(2):
        selected = propose_menu(request, recipes, feedback)
        result = validate_plan(request, recipes, selected)
        if result.valid: return result
        feedback = result.issues
    return result
