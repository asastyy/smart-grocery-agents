from smart_grocery.schemas.models import PlanningRequest, PlanningResult, Recipe
from smart_grocery.tools.budget import evaluate_menu
from smart_grocery.agents.critic import critique_plan

def validate_plan(request: PlanningRequest, recipes: list[Recipe], selected: list[str]) -> PlanningResult:
    result = evaluate_menu(request, recipes, selected)
    if not result.valid:
        advice = critique_plan(request, recipes, result)
        return result.model_copy(update={"issues": [*result.issues, *advice]})
    return result
