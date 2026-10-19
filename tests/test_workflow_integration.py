import json
from pathlib import Path

import pytest

from smart_grocery.schemas.models import PlanningRequest, PlanningResult
from smart_grocery.workflow import runner
from smart_grocery.tools import budget, recipes

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")


def request(name="request_basic"):
    return PlanningRequest.model_validate_json((ROOT / "fixtures" / f"{name}.json").read_text())


def test_real_modules_keep_legacy_contract():
    run = runner.run_workflow_with_trace(request())
    assert run.error is None
    assert run.result.valid
    assert run.result.total_cost == 3.5
    assert [s["step"] for s in run.agent_trace] == ["recipe_search", "planner", "validator"]
    assert isinstance(runner.run_workflow(request()), PlanningResult)
    json.dumps(run.model_dump())


def test_over_budget_revises_once_and_keeps_first_assessment():
    run = runner.run_workflow_with_trace(request("request_over_budget"))
    assert not run.result.valid
    assert len(run.agent_trace) == 5
    first = run.agent_trace[2]["assessment"]
    assert any("Budget exceeded" in issue for issue in first["issues"])
    assert any("Critic [mock]" in issue for issue in first["issues"])
    assert run.agent_trace[3]["feedback"] == first["issues"]
    assert run.agent_trace[3]["attempt"] == 2


def test_revised_plan_is_checked_by_actual_validator(monkeypatch):
    feedback_seen = []

    def planner(req, candidates, feedback=None):
        feedback_seen.append(feedback)
        return ["omelette"] if feedback is None else ["salad"]

    monkeypatch.setattr(runner, "propose_menu", planner)
    req = request().model_copy(update={"days": 1, "budget": 1.3})
    run = runner.run_workflow_with_trace(req)
    assert run.result.valid
    assert run.result.recipe_ids == ["salad"]
    assert run.result.total_cost == 1.2
    assert any("Critic [mock]" in issue for issue in feedback_seen[1])
    assert not run.agent_trace[2]["assessment"]["valid"]
    assert run.agent_trace[4]["assessment"]["valid"]


def test_empty_search_is_explained(monkeypatch):
    monkeypatch.setattr(recipes, "DATA", ROOT / "fixtures" / "recipes_empty.json")
    run = runner.run_workflow_with_trace(request("request_no_match"))
    assert run.result is None
    assert run.error == "No eligible recipes"
    assert len(run.agent_trace) == 1
    with pytest.raises(ValueError, match="No eligible recipes"):
        runner.run_workflow(request())


def test_missing_prices_never_become_success(monkeypatch):
    monkeypatch.setattr(budget, "PRICES", ROOT / "fixtures" / "prices_missing.json")
    run = runner.run_workflow_with_trace(request("request_missing_price"))
    assert run.error is None
    assert not run.result.valid
    assert any("incomplete" in issue for issue in run.result.issues)


def test_unknown_model_recipe_is_rejected(monkeypatch):
    monkeypatch.setattr(runner, "propose_menu", lambda *args: ["invented"] * args[0].days)
    run = runner.run_workflow_with_trace(request())
    assert not run.result.valid
    assert "Unknown recipe ID" in run.result.issues


def test_live_mode_requires_config_and_does_not_call_planner(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    run = runner.run_workflow_with_trace(request())
    assert run.result is None
    assert "LLM_API_KEY" in run.error
    assert run.agent_trace == []


@pytest.mark.parametrize("stage", ["search_recipes", "propose_menu", "validate_plan"])
def test_component_failures_are_safe_and_traced(monkeypatch, stage):
    def fail(*args):
        raise RuntimeError("SECRET_API_KEY provider response")

    monkeypatch.setattr(runner, stage, fail)
    run = runner.run_workflow_with_trace(request())
    assert run.result is None
    assert run.error
    assert run.agent_trace[-1]["status"] == "error"
    assert "SECRET_API_KEY" not in json.dumps(run.model_dump())


def test_failed_revision_does_not_publish_old_plan(monkeypatch):
    calls = 0

    def planner(req, candidates, feedback):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("provider failed")
        return ["omelette"] * req.days

    monkeypatch.setattr(runner, "propose_menu", planner)
    run = runner.run_workflow_with_trace(request("request_over_budget"))
    assert run.result is None
    assert not run.agent_trace[2]["assessment"]["valid"]
    assert run.agent_trace[-1]["status"] == "error"


def test_three_day_demo_uses_real_modules():
    run = runner.run_workflow_with_trace(request().model_copy(update={"days": 3}))
    assert run.result.valid
    assert len(run.result.recipe_ids) == 3
