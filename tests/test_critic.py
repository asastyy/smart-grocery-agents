import json

import httpx
import pytest
from openai import OpenAI

from smart_grocery.agents import critic
from smart_grocery.agents.validator import validate_plan
from smart_grocery.schemas.models import PlanningRequest
from smart_grocery.tools.budget import evaluate_menu
from smart_grocery.tools.recipes import search_recipes
from smart_grocery.workflow import runner


GOOD = json.dumps({"advice": [{"issue_index": 0,
    "recommendation": "Выберите более доступный рецепт.", "candidate_ids": ["salad"]}]})


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.delenv("CRITIC_MODEL", raising=False)
    calls = []

    def install(outputs, status=200):
        def handle(request):
            calls.append(json.loads(request.content))
            if status != 200:
                return httpx.Response(status, json={"error": {"message": "private-provider-detail"}})
            content = outputs[min(len(calls) - 1, len(outputs) - 1)]
            return httpx.Response(200, json={"id": "test", "object": "chat.completion",
                "created": 0, "model": "test-model", "choices": [{"index": 0,
                "finish_reason": "stop", "message": {"role": "assistant", "content": content}}]})
        def factory(**kwargs):
            assert kwargs["max_retries"] == 0
            assert kwargs["timeout"] == 20
            kwargs["base_url"] = "https://test.invalid/v1"
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        monkeypatch.setattr(critic, "OpenAI", factory)
        return calls
    return install


def invalid_request():
    return PlanningRequest(pantry=[], budget=0, days=1, servings=1)


def test_critic_preserves_facts_and_sends_computed_context(api):
    calls = api([GOOD])
    req = invalid_request()
    recipes = search_recipes(req)
    baseline = evaluate_menu(req, recipes, ["omelette"])
    result = validate_plan(req, recipes, ["omelette"])
    assert result.model_dump(exclude={"issues"}) == baseline.model_dump(exclude={"issues"})
    assert result.issues[:len(baseline.issues)] == baseline.issues
    assert result.issues[-1].startswith("Critic [LLM")
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert payload["assessment"]["total_cost"] == baseline.total_cost
    assert payload["candidates"][0]["assessment"]["total_cost"] == baseline.total_cost


@pytest.mark.parametrize("bad", ["not JSON", "{}", "", '{"advice":[]}',
    GOOD.replace('"salad"', '"invented"'), GOOD.replace('"issue_index": 0', '"issue_index": 999'),
    GOOD.replace('"advice":', '"valid":true,"advice":')])
def test_invalid_response_retried_once(api, bad):
    calls = api([bad, GOOD])
    req = invalid_request()
    result = validate_plan(req, search_recipes(req), ["omelette"])
    assert len(calls) == 2
    assert not result.valid
    assert "Critic [LLM" in result.issues[-1]


def test_persistent_bad_json_falls_back(api):
    calls = api(["{}"])
    req = invalid_request()
    result = validate_plan(req, search_recipes(req), ["omelette"])
    assert len(calls) == 2
    assert not result.valid
    assert "Budget exceeded" in result.issues[0]
    assert "Critic unavailable" in result.issues[-1]


def test_api_failure_is_nonfatal_and_does_not_leak(api):
    calls = api([], status=500)
    req = invalid_request()
    result = validate_plan(req, search_recipes(req), ["omelette"])
    assert len(calls) == 1
    assert not result.valid
    assert "Critic unavailable" in result.issues[-1]
    assert "private-provider-detail" not in str(result)


def test_valid_plan_does_not_call_api(api):
    calls = api([GOOD])
    req = invalid_request().model_copy(update={"budget": 100})
    assert validate_plan(req, search_recipes(req), ["omelette"]).valid
    assert not calls


def test_mock_mode_no_api(api, monkeypatch):
    calls = api([GOOD])
    monkeypatch.setenv("MOCK_LLM", "true")
    req = invalid_request()
    result = validate_plan(req, search_recipes(req), ["omelette"])
    assert "Critic [mock]" in result.issues[-1]
    assert not calls


def test_missing_configuration(api, monkeypatch):
    calls = api([GOOD])
    monkeypatch.delenv("LLM_API_KEY")
    req = invalid_request()
    result = validate_plan(req, search_recipes(req), ["omelette"])
    assert "configure" in result.issues[-1]
    assert not calls


def test_feedback_reaches_planner_and_revision_is_revalidated(api, monkeypatch):
    calls = api([GOOD])
    feedback_seen = []
    def planner(request, recipes, feedback=None):
        feedback_seen.append(feedback)
        return ["omelette"] if feedback is None else ["salad"]
    monkeypatch.setattr(runner, "propose_menu", planner)
    req = invalid_request().model_copy(update={"budget": 2.1})
    result = runner.run_workflow(req)
    assert result.valid
    assert result.recipe_ids == ["salad"]
    assert result.total_cost == 2.0
    assert len(feedback_seen) == 2
    assert any("Critic [LLM" in issue for issue in feedback_seen[1])
    assert len(calls) == 1


def test_revision_loop_is_bounded(api, monkeypatch):
    calls = api([GOOD])
    monkeypatch.setattr(runner, "propose_menu", lambda *args: ["omelette"])
    assert not runner.run_workflow(invalid_request()).valid
    assert len(calls) == 2
