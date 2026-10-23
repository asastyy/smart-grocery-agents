import json
from pathlib import Path

import pytest

from smart_grocery.schemas.models import Ingredient, PlanningRequest, Recipe
from smart_grocery.tools import budget
from smart_grocery.tools.legacy_recipes import search_recipes


@pytest.fixture
def prices(tmp_path, monkeypatch):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"rice": 0.9, "beans": 1.1}), encoding="utf-8")
    monkeypatch.setattr(budget, "PRICES", path)


def request(**overrides):
    return PlanningRequest(**({"pantry": [], "budget": 20, "days": 1,
                              "servings": 1} | overrides))


def recipe(id="rice", item="rice", qty=1, unit="portion", tags=None):
    return Recipe(id=id, name=id, ingredients=[Ingredient(item=item, qty=qty, unit=unit)],
                  tags=tags or [])


def test_sample_request_exact_shopping():
    req = PlanningRequest.model_validate_json(Path("examples/request.json").read_text())
    result = budget.evaluate_menu(req, search_recipes(req), ["omelette", "rice_bowl"])
    assert result.valid
    assert result.total_cost == 3.5
    assert {line.item: line.quantity for line in result.shopping} == {
        "cheese": 1, "rice": 1, "beans": 1}


def test_shared_ingredient_and_repeated_meal(prices):
    result = budget.evaluate_menu(request(days=3),
                                  [recipe("a", qty=2), recipe("b", qty=3)],
                                  ["a", "b", "a"])
    assert result.valid
    assert len(result.shopping) == 1
    assert result.shopping[0].quantity == 7
    assert result.total_cost == 6.3


def test_pantry_boolean_availability(prices):
    result = budget.evaluate_menu(request(pantry=[" RICE "], budget=0),
                                  [recipe(qty=100)], ["rice"])
    assert result.valid
    assert result.shopping == []
    assert result.total_cost == 0


@pytest.mark.parametrize("limit, valid", [(0.9, True), (0.89, False)])
def test_budget_boundary(prices, limit, valid):
    result = budget.evaluate_menu(request(budget=limit), [recipe()], ["rice"])
    assert result.valid is valid
    assert any("Budget exceeded" in issue for issue in result.issues) is (not valid)


@pytest.mark.parametrize("selected, message", [
    (["missing"], "Unknown recipe ID"),
    ([], "Recipe count does not match days"),
    (["rice", "rice"], "Recipe count does not match days"),
])
def test_invalid_selection(prices, selected, message):
    result = budget.evaluate_menu(request(), [recipe()], selected)
    assert not result.valid
    assert message in result.issues


@pytest.mark.parametrize("diet,tags,valid", [
    ("vegan", ["vegetarian"], False),
    ("vegetarian", [], False),
    ("vegan", ["vegan"], True),
    ("none", [], True),
])
def test_diet_checks(prices, diet, tags, valid):
    result = budget.evaluate_menu(request(diet=diet), [recipe(tags=tags)], ["rice"])
    assert result.valid is valid


def test_missing_price_reports_partial_total(prices):
    result = budget.evaluate_menu(request(days=2),
                                  [recipe(), recipe("other", item="unknown")],
                                  ["rice", "other"])
    assert not result.valid
    assert result.total_cost == 0.9
    assert any("Unknown price for unknown" in issue for issue in result.issues)
    assert any("incomplete" in issue.lower() for issue in result.issues)


@pytest.mark.parametrize("pantry", [[], ["rice"]])
def test_unsupported_units_are_rejected(prices, pantry):
    result = budget.evaluate_menu(request(pantry=pantry), [recipe(unit="g", qty=100)], ["rice"])
    assert not result.valid
    assert result.shopping == []
    assert any("Unsupported unit" in issue for issue in result.issues)
    assert any("incomplete" in issue.lower() for issue in result.issues)
