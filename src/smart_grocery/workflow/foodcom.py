"""Bounded integration of role 1 search, role 2 planner and role 3 validator."""
from smart_grocery.agents.planner import MAX_CANDIDATES, plan_meals
from smart_grocery.agents.validator import validate_foodcom_plan
from smart_grocery.tools.budget_v2 import Request
from smart_grocery.tools.recipes import load_prices, search_recipes


def run_foodcom_workflow(request):
    # Validate once before invoking other modules; keep ordinary JSON numbers.
    Request.model_validate(request)
    candidates = search_recipes(request)["candidates"][:MAX_CANDIDATES]
    if not candidates:
        return {"plan": {"meals": [], "reasoning_summary": "No eligible recipes"},
                "assessment": {"valid": False, "total_cost": None, "priced_subtotal": 0.0,
                    "shopping_list": [], "violations": [{"code": "no_candidates",
                    "message": "No eligible recipes"}], "feedback": "Change dietary or cooking constraints."},
                "agent_trace": []}
    catalog = {"recipes": candidates, "prices": load_prices()}
    trace = []
    feedback = None
    for attempt in range(2):
        plan = plan_meals(request, candidates, feedback, slots=("lunch", "dinner"))
        assessment = validate_foodcom_plan(request, plan, catalog)
        trace.append({"attempt": attempt + 1, "plan": plan, "assessment": assessment})
        if assessment["valid"]:
            break
        feedback = assessment["feedback"].splitlines()
    return {"plan": plan, "assessment": assessment, "agent_trace": trace}
