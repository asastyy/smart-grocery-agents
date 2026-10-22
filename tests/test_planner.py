import json
from pathlib import Path

import httpx
from openai import OpenAI

from smart_grocery.agents import planner
from smart_grocery.schemas.models import PlanningRequest, Recipe


OLD_RECIPES = [
    Recipe(id="omelette", name="Tomato omelette", ingredients=[], tags=["vegetarian"]),
    Recipe(id="salad", name="Green salad", ingredients=[], tags=["vegan"]),
]
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
NEW_CANDIDATES = json.loads((FIXTURES_DIR / "mock_candidates.json").read_text(encoding="utf-8"))


def test_normalizes_both_recipe_contracts():
    assert [item.recipe_id for item in planner.normalize_candidates(OLD_RECIPES)] == ["omelette", "salad"]
    assert [item.title for item in planner.normalize_candidates(NEW_CANDIDATES)] == ["Cabbage soup", "Rice bowl"]


def test_legacy_adapter_is_offline_and_preserves_old_contract(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    request = PlanningRequest(pantry=[], budget=10, days=3, servings=1)
    assert planner.propose_menu(request, OLD_RECIPES) == ["omelette", "salad", "omelette"]


def test_v2_adapter_builds_day_and_slot_plan(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    result = planner.plan_meals({"days": 2, "diet": ["vegetarian"]}, NEW_CANDIDATES, slots=("lunch", "dinner"))
    assert result["meals"] == [
        {"day": 1, "slot": "lunch", "recipe_id": "r001", "servings": 1},
        {"day": 1, "slot": "dinner", "recipe_id": "r002", "servings": 1},
        {"day": 2, "slot": "lunch", "recipe_id": "r001", "servings": 1},
        {"day": 2, "slot": "dinner", "recipe_id": "r002", "servings": 1},
    ]


def test_live_mode_retries_invalid_json_and_rejects_unknown_ids(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    replies = ["not json", json.dumps({"recipe_ids": ["r001"], "reasoning_summary": "ok"})]
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 0, "model": "test-model",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": replies[len(requests) - 1]}}],
        })

    def factory(**kwargs):
        assert kwargs["max_retries"] == 0
        assert kwargs["timeout"] == 20.0
        kwargs["base_url"] = "https://offline.invalid/v1"
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr("openai.OpenAI", factory)
    result = planner.plan_meals({"days": 1}, NEW_CANDIDATES)
    assert result["meals"][0]["recipe_id"] == "r001"
    assert len(requests) == 2


def test_live_mode_never_accepts_invented_id_and_falls_back(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    def factory(**kwargs):
        kwargs["base_url"] = "https://offline.invalid/v1"
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={
                "id": "test", "object": "chat.completion", "created": 0, "model": "test-model",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"recipe_ids":["invented"]}'}}],
            })
        )))

    monkeypatch.setattr("openai.OpenAI", factory)
    result = planner.plan_meals({"days": 1}, NEW_CANDIDATES)
    assert result["meals"][0]["recipe_id"] == "r001"
    assert "fallback" in result["reasoning_summary"].lower()
