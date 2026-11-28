"""Cross-branch boundaries: data quality, personalization and retail quotes."""
from datetime import date
from decimal import Decimal
from pathlib import Path

from streamlit.testing.v1 import AppTest

from smart_grocery.catalog.loader import planning_recipes
from smart_grocery.retail.snapshot import snapshot_provider
from smart_grocery.workflow.golden import load_golden_case
from smart_grocery.workflow.integration import run_integration_workflow

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_unknown_allergens_stop_before_model_and_store(monkeypatch):
    case, provider = load_golden_case()
    def forbidden(*args, **kwargs):
        raise AssertionError("Rejected candidates must not trigger a model or store request")
    monkeypatch.setattr(provider, "search_products", forbidden)
    monkeypatch.setattr("smart_grocery.workflow.foodcom.plan_meals", forbidden)
    result = run_integration_workflow(case.profile, case.inventory, planning_recipes(), provider, days=5)
    assert result.attempts == 0 and result.plan is None
    assert [issue.code for issue in result.violations] == ["no_candidates"]


def test_retail_snapshot_never_becomes_a_complete_golden_basket(monkeypatch):
    case, _ = load_golden_case()
    monkeypatch.setenv("MOCK_LLM", "true")
    result = run_integration_workflow(case.profile, case.inventory, case.recipes, snapshot_provider(), days=5,
                                      as_of=date(2026, 11, 19), mock_planner=True)
    assert result.plan and len(result.plan.meals) == 10
    assert not result.valid and result.shopping_list.estimated_total is None
    assert result.shopping_list.priced_subtotal == Decimal(0)
    assert all(line.selected_offer is None for line in result.shopping_list.lines)


def test_source_change_clears_previous_test_total(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    app.radio(key="section").set_value("Профиль и запасы").run()
    app.button(key="sprint_submit").click().run()
    assert app.metric[0].value == "1710.00 ₽"
    app.selectbox(key="sprint_store_source").set_value("ВкусВилл: сохраненный снимок").run()
    assert not app.exception and not app.metric
    app.button(key="sprint_submit").click().run()
    assert not app.exception and app.metric[0].label == "Частичный итог"
    app.selectbox(key="sprint_recipe_source").set_value("Каталог источников").run()
    app.button(key="sprint_submit").click().run()
    assert not app.exception and not app.metric
    assert any("нет подходящих рецептов" in warning.value for warning in app.warning)


def test_critic_recommendations_only_enrich_retry(monkeypatch):
    case, provider = load_golden_case()
    case.profile.budget = Decimal(100)
    monkeypatch.setenv("MOCK_LLM", "true")
    calls = []
    def advise(*args):
        calls.append(args)
        return ["Увеличьте бюджет или пополните запасы."]
    monkeypatch.setattr("smart_grocery.agents.critic.critique_context", advise)
    result = run_integration_workflow(case.profile, case.inventory, case.recipes, provider, days=5,
                                      as_of=date(2026, 11, 19))
    assert len(calls) == 1 and result.attempts == 2
    assert not result.valid and result.shopping_list.estimated_total == Decimal("1710.00")
    assert result.recommendations == ["Увеличьте бюджет или пополните запасы."]
