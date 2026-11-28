from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from smart_grocery.tools.grocery_provider import CartItem, ProviderUnavailable
from smart_grocery.workflow.golden import load_golden_case
from smart_grocery.workflow.integration import run_integration_workflow


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def golden(monkeypatch):
    # The demo must remain offline even on a machine configured for live Gemini.
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    return load_golden_case()


def run_golden(case, provider):
    return run_integration_workflow(
        case.profile, case.inventory, case.recipes, provider, days=case.days,
        as_of=date(2026, 11, 19), mock_planner=True,
    )


def test_golden_profile_to_whole_packages(golden):
    case, provider = golden
    result = run_golden(case, provider)
    assert result.valid and result.attempts == 1
    assert result.plan.days == 5
    assert result.candidate_ids == ["golden-rice", "golden-chicken"]
    assert [(meal.day, meal.slot, meal.servings) for meal in result.plan.meals] == [
        (day, slot, 2) for day in range(1, 6) for slot in ("lunch", "dinner")
    ]
    assert {meal.recipe_id for meal in result.plan.meals} == set(result.candidate_ids)
    shopping = result.shopping_list
    assert shopping.currency == "RUB"
    assert shopping.estimated_total == shopping.priced_subtotal == Decimal("1710.00")
    lines = {line.ingredient_id: line for line in shopping.lines}
    rice = lines["rice"]
    assert (rice.required_quantity, rice.inventory_quantity, rice.missing_quantity) == (1100, 500, 600)
    assert rice.selected_offer.product_id == "rice-400"
    assert (rice.package_count, rice.estimated_total) == (2, Decimal("240.00"))
    assert len(lines) == 5 and "milk" not in lines
    assert provider.get_product_details("rice-400") == rice.selected_offer
    assert provider.check_availability("rice-750-sold-out") == "out_of_stock"
    assert provider.check_availability("unknown-sku") == "unknown"
    items = [CartItem(product_id="rice-400", package_count=2)]
    assert provider.create_cart(items).model_dump() == {"status": "not_supported", "operation": "create_cart"}
    assert provider.cart_link(items).model_dump() == {"status": "not_supported", "operation": "cart_link"}


def test_unverified_recipes_stop_before_planning(golden):
    case, provider = golden
    case.recipes = [recipe for recipe in case.recipes if recipe.recipe_id == "golden-unknown"]
    result = run_golden(case, provider)
    assert [issue.code for issue in result.violations] == ["no_candidates"]
    assert result.attempts == 0
    assert result.plan is None and result.shopping_list is None


def test_no_offer_in_currency_keeps_partial_total_and_budget_warning(golden):
    case, provider = golden
    case.profile.budget = Decimal(500)
    provider.get_product_details("oil-250").currency = "CU"
    result = run_golden(case, provider)
    assert not result.valid and result.attempts == 2
    assert result.plan is not None
    assert {issue.code for issue in result.violations} == {"no_compatible_offer", "over_budget"}
    assert result.shopping_list.estimated_total is None
    assert result.shopping_list.priced_subtotal == Decimal("1470.00")
    oil = next(line for line in result.shopping_list.lines if line.ingredient_id == "olive_oil")
    assert oil.selected_offer is None and oil.missing_quantity == 100


def test_unverified_product_composition_stays_unpriced(golden):
    case, provider = golden
    provider.get_product_details("oil-250").allergens_status = "unknown"
    result = run_golden(case, provider)
    assert result.shopping_list.estimated_total is None
    assert any(issue.code == "no_compatible_offer" for issue in result.violations)


def test_provider_error_preserves_menu_and_other_prices(golden, monkeypatch):
    case, provider = golden
    search = provider.search_products

    def unavailable_for_rice(ingredient_id):
        if ingredient_id == "rice":
            raise ProviderUnavailable("private provider details")
        return search(ingredient_id)

    monkeypatch.setattr(provider, "search_products", unavailable_for_rice)
    result = run_golden(case, provider)
    assert result.plan is not None and len(result.plan.meals) == 10
    assert [issue.code for issue in result.violations] == ["provider_unavailable"]
    assert result.shopping_list.estimated_total is None
    assert result.shopping_list.priced_subtotal == Decimal("1470.00")
    assert "private provider details" not in result.model_dump_json()


def test_expired_and_unconfirmed_inventory_and_mismatched_units(golden):
    case, provider = golden
    rice = next(item for item in case.inventory if item.ingredient_id == "rice")
    rice.expiry_date = date(2026, 11, 18)
    eggs = next(item for item in case.inventory if item.ingredient_id == "egg")
    eggs.confidence = Decimal("0.5")
    tomato = next(item for item in case.inventory if item.ingredient_id == "tomato")
    tomato.unit = "pcs"
    result = run_golden(case, provider)
    lines = {line.ingredient_id: line for line in result.shopping_list.lines}
    assert (lines["rice"].missing_quantity, lines["rice"].package_count) == (1100, 3)
    assert (lines["egg"].missing_quantity, lines["egg"].package_count) == (10, 2)
    assert lines["tomato"].matched_offers == []
    assert lines["tomato"].selected_offer is None
    assert result.shopping_list.estimated_total is None
    assert any(issue.code == "unit_mismatch" for issue in result.violations)
    assert rice.quantity == 500


def test_streamlit_golden_and_profile_update(golden):
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    app.radio(key="section").set_value("Профиль и запасы").run()
    app.button(key="sprint_submit").click().run()
    assert not app.exception
    assert app.metric[0].value == "1710.00 ₽"
    assert len(app.dataframe[0].value) == 10
    assert len(app.dataframe[1].value) == 5
    app.number_input(key="sprint_budget").set_value(100.0)
    app.button(key="sprint_submit").click().run()
    assert any("превышает бюджет" in message.value for message in app.warning)
