"""Bounded integration of role 1 search, role 2 planner and role 3 validator."""
from smart_grocery.agents.planner import MAX_CANDIDATES, plan_meals
from smart_grocery.agents.validator import validate_foodcom_plan
from smart_grocery.schemas.foodcom import Request
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

    def assess(plan):
        return validate_foodcom_plan(request, plan, catalog)

    return run_candidate_loop(request, candidates, assess)


def run_candidate_loop(request, candidates, assess, *, planner=None, feedback_enricher=None, slots=("lunch", "dinner")):
    """Reuse the bounded planner and feedback loop with a choice of assessment."""
    planner = plan_meals if planner is None else planner
    trace = []
    feedback = None
    for attempt in range(2):
        plan = planner(request, candidates, feedback, slots=slots)
        assessment = assess(plan)
        trace.append({"attempt": attempt + 1, "plan": plan, "assessment": assessment})
        if assessment["valid"]:
            break
        feedback = assessment["feedback"].splitlines()
        if attempt == 0 and feedback_enricher is not None:
            feedback.extend(feedback_enricher(assessment))
    return {"plan": plan, "assessment": assessment, "agent_trace": trace}
