from copy import deepcopy

import pytest

from smart_grocery.tools.budget_v2 import evaluate_plan
from smart_grocery.workflow import foodcom


@pytest.fixture
def sample():
    request = {"pantry": [{"ingredient_id": "rice", "quantity": 100, "unit": "g"}],
               "budget": 5, "currency": "CU", "days": 1, "people": 2,
               "diet": ["vegetarian"], "max_cook_minutes": 30}
    recipe = {"recipe_id": "r1", "title": "Rice", "servings": 4, "cook_minutes": 20,
              "tags": ["vegetarian"], "ingredients": [
                  {"ingredient_id": "rice", "quantity": 400, "unit": "g"}]}
    plan = {"meals": [{"day": 1, "slot": slot, "recipe_id": "r1", "servings": 2}
                      for slot in ("lunch", "dinner")]}
    catalog = {"recipes": [recipe], "prices": {"rice": {
        "unit": "g", "price_per_unit": 0.01, "currency": "CU"}}}
    return request, plan, catalog


def codes(result):
    return {v["code"] for v in result["violations"]}


def test_scaling_aggregation_and_depletion(sample):
    result = evaluate_plan(*sample)
    assert result["valid"]
    assert result["total_cost"] == 3
    assert result["shopping_list"][0]["quantity"] == 300


def test_duplicate_pantry_entries_and_surplus(sample):
    req, plan, cat = sample
    req["pantry"] *= 5
    result = evaluate_plan(req, plan, cat)
    assert result["valid"]
    assert result["shopping_list"] == []
    assert result["total_cost"] == 0


@pytest.mark.parametrize("budget,valid", [(3, True), (2.99, False)])
def test_budget_boundary(sample, budget, valid):
    req, plan, cat = sample
    req["budget"] = budget
    assert evaluate_plan(req, plan, cat)["valid"] is valid


@pytest.mark.parametrize("change,code", [
    ("missing_price", "missing_price"), ("unit", "price_mismatch"),
    ("currency", "price_mismatch"), ("negative", "invalid_price"),
    ("nan", "invalid_price"), ("pantry_unit", "unit_mismatch")])
def test_incomplete_cost_keeps_unpriced_item(sample, change, code):
    req, plan, cat = sample
    if change == "missing_price": cat["prices"].clear()
    elif change == "unit": cat["prices"]["rice"]["unit"] = "ml"
    elif change == "currency": cat["prices"]["rice"]["currency"] = "EUR"
    elif change == "negative": cat["prices"]["rice"]["price_per_unit"] = -1
    elif change == "nan": cat["prices"]["rice"]["price_per_unit"] = float("nan")
    else: req["pantry"][0]["unit"] = "pcs"
    result = evaluate_plan(req, plan, cat)
    assert code in codes(result)
    assert not result["valid"]
    assert result["total_cost"] is None
    assert result["shopping_list"][0]["cost"] is None


@pytest.mark.parametrize("change,code", [
    ("duplicate_slot", "meal_slots"), ("missing_slot", "meal_slots"),
    ("wrong_day", "meal_slots"), ("servings", "servings_mismatch"),
    ("unknown", "unknown_recipe"), ("diet", "diet_mismatch"),
    ("time", "cook_time"), ("recipe_unit", "invalid_recipe")])
def test_plan_constraints(sample, change, code):
    req, plan, cat = sample
    if change == "duplicate_slot": plan["meals"][1]["slot"] = "lunch"
    elif change == "missing_slot": plan["meals"].pop()
    elif change == "wrong_day": plan["meals"][1]["day"] = 2
    elif change == "servings": plan["meals"][0]["servings"] = 1
    elif change == "unknown": plan["meals"][0]["recipe_id"] = "invented"
    elif change == "diet": cat["recipes"][0]["tags"] = []
    elif change == "time": cat["recipes"][0]["cook_minutes"] = 60
    else: cat["recipes"][0]["ingredients"][0]["unit"] = "kg"
    assert code in codes(evaluate_plan(req, plan, cat))


def test_negative_pantry_rejected(sample):
    req, plan, cat = sample
    req["pantry"][0]["quantity"] = -1
    assert "invalid_input" in codes(evaluate_plan(req, plan, cat))


def test_actual_data_and_planner_work_together(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    request = {"pantry": [], "budget": 100, "currency": "CU", "days": 3,
               "people": 2, "diet": ["vegetarian"], "max_cook_minutes": 30}
    result = foodcom.run_foodcom_workflow(request)
    assert result["assessment"]["valid"]
    assert len(result["plan"]["meals"]) == 6
    assert len(result["agent_trace"]) == 1
    assert all(m["servings"] == 2 for m in result["plan"]["meals"])
    request["budget"] = 0
    failed = foodcom.run_foodcom_workflow(request)
    assert not failed["assessment"]["valid"]
    assert len(failed["agent_trace"]) == 2
    assert "Critic [mock]" in failed["assessment"]["feedback"]


def test_no_candidates(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    result = foodcom.run_foodcom_workflow({"pantry": [], "budget": 20, "days": 1,
        "people": 1, "diet": ["vegan"], "max_cook_minutes": 30})
    assert codes(result["assessment"]) == {"no_candidates"}


def test_feedback_reaches_role2_and_corrected_plan_revalidated(sample, monkeypatch):
    req, plan, cat = sample
    cheap = deepcopy(cat["recipes"][0])
    cheap["recipe_id"] = "cheap"
    cheap["ingredients"][0]["quantity"] = 200
    cat["recipes"].append(cheap)
    req["budget"] = 1
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setattr(foodcom, "search_recipes", lambda r: {"candidates": cat["recipes"]})
    monkeypatch.setattr(foodcom, "load_prices", lambda: cat["prices"])
    feedbacks = []
    def planner(request, candidates, feedback, slots):
        feedbacks.append(feedback)
        revised = deepcopy(plan)
        if feedback:
            for meal in revised["meals"]: meal["recipe_id"] = "cheap"
        return revised
    monkeypatch.setattr(foodcom, "plan_meals", planner)
    result = foodcom.run_foodcom_workflow(req)
    assert result["assessment"]["valid"]
    assert result["assessment"]["total_cost"] == 1
    assert any("exceeds budget" in line for line in feedbacks[1])
    assert len(result["agent_trace"]) == 2
