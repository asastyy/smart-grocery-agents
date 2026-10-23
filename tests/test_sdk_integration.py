"""Both actual agents and Python calculator, using an offline SDK transport."""
import json

import httpx
from openai import OpenAI

from smart_grocery.agents import critic
from smart_grocery.schemas.models import PlanningRequest
from smart_grocery.workflow.runner import run_workflow_with_trace


def test_planner_critic_revision_with_actual_sdk(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("LLM_API_KEY", "offline-test-key")
    monkeypatch.setenv("LLM_MODEL", "offline-test-model")
    calls = []
    outputs = [
        {"recipe_ids": ["omelette"]},
        {"advice": [{"issue_index": 0, "recommendation": "Choose the cheaper salad.", "candidate_ids": ["salad"]}]},
        {"recipe_ids": ["salad"]},
    ]

    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 0,
            "model": "offline-test-model", "choices": [{"index": 0,
            "finish_reason": "stop", "message": {"role": "assistant",
            "content": json.dumps(outputs[len(calls) - 1])}}],
        })

    clients = []

    def factory(**kwargs):
        kwargs["base_url"] = "https://offline.invalid/v1"
        kwargs["max_retries"] = 0
        client = OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        clients.append(client)
        return client

    monkeypatch.setattr("openai.OpenAI", factory)
    monkeypatch.setattr(critic, "OpenAI", factory)
    try:
        request = PlanningRequest(pantry=["eggs", "tomato"], budget=1.3, days=1, servings=1)
        run = run_workflow_with_trace(request)
        assert run.error is None
        assert run.result.valid
        assert run.result.total_cost == 1.2
        assert run.result.recipe_ids == ["salad"]
        assert len(calls) == 3
        assert "Smart Grocery critic" in calls[1]["messages"][0]["content"]
        assert "Choose the cheaper salad." in calls[2]["messages"][1]["content"]
        assert not run.agent_trace[2]["assessment"]["valid"]
        assert run.agent_trace[4]["assessment"]["valid"]
        assert "offline-test-key" not in json.dumps(run.model_dump())
    finally:
        for client in clients:
            client.close()
