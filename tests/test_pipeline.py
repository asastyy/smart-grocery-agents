import json
from pathlib import Path
from smart_grocery.schemas.models import PlanningRequest
from smart_grocery.workflow.runner import run_workflow
from smart_grocery.tools.recipes import search_recipes
from smart_grocery.tools.budget import evaluate_menu

def test_sample_workflow(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    request = PlanningRequest.model_validate(json.loads(Path("examples/request.json").read_text()))
    result = run_workflow(request)
    assert result.valid
    assert len(result.recipe_ids) == request.days
    assert result.total_cost <= request.budget

def test_over_budget():
    request = PlanningRequest(pantry=[],budget=0,days=1,servings=1)
    result = evaluate_menu(request, search_recipes(request), ["omelette"])
    assert not result.valid
    assert any("Budget exceeded" in s for s in result.issues)
