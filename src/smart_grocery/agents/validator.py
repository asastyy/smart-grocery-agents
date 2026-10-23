from smart_grocery.schemas.models import PlanningRequest, PlanningResult, Recipe
from smart_grocery.tools.budget import evaluate_menu
from smart_grocery.agents.critic import critique_plan

def validate_plan(request: PlanningRequest, recipes: list[Recipe], selected: list[str]) -> PlanningResult:
    result = evaluate_menu(request, recipes, selected)
    if not result.valid:
        advice = critique_plan(request, recipes, result)
        return result.model_copy(update={"issues": [*result.issues, *advice]})
    return result


def validate_foodcom_plan(request, plan, catalog):
    """Role 3 entry point for the shared Food.com contract."""
    from smart_grocery.tools.budget_v2 import evaluate_plan
    from smart_grocery.agents.critic import critique_context

    result = evaluate_plan(request, plan, catalog)
    if result["valid"] or any(v["code"] == "invalid_input" for v in result["violations"]):
        return result
    candidates = []
    for recipe in catalog["recipes"]:
        single_request = {**request, "days": 1}
        single_plan = {"meals": [{"day": 1, "slot": "dinner",
                        "recipe_id": recipe["recipe_id"], "servings": request["people"]}]}
        estimate = evaluate_plan(single_request, single_plan, catalog, slots=("dinner",))
        candidates.append({"recipe": recipe, "assessment": estimate})
    context = {**result, "issues": [v["message"] for v in result["violations"]]}
    advice = critique_context(request, context, candidates,
                              {r["recipe_id"] for r in catalog["recipes"]}, len(result["violations"]))
    return {**result, "feedback": "\n".join([result["feedback"], *advice])}
