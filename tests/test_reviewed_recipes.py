"""Acceptance checks for the first 50 source-audited planning recipes."""
import json
from decimal import Decimal
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from smart_grocery.catalog.reviewed import REVIEWED_DIR, load_reviewed_records, reviewed_planning_recipes, scale_recipe, source_measurement
from smart_grocery.catalog.reviewed_ui import NAMES
from smart_grocery.schemas.foodcom import Ingredient, Meal, Plan, Request
from smart_grocery.tools.budget_v2 import measure_plan
from smart_grocery.tools.personalization import personalize_recipes
from smart_grocery.workflow.golden import load_golden_case
from smart_grocery.workflow.integration import run_integration_workflow

ROOT = Path(__file__).resolve().parents[1]
RECIPES = reviewed_planning_recipes()
BY_ID = {r.recipe_id: r for r in RECIPES}


def test_exactly_50_distinct_audited_sources_with_unknown_allergens():
    rows = load_reviewed_records()
    assert len(rows) == len({r['recipe_id'] for r in rows}) == len({r['source'] for r in rows}) == 50
    assert sum(r.meal_slots == ['breakfast'] for r in RECIPES) == 6
    assert all(r['allergens_status'] == 'unknown' and r['allergens'] is None for r in rows)
    assert all(r['review']['checks']['ingredients_and_steps'] for r in rows)
    assert {i.ingredient_id for r in RECIPES for i in r.ingredients} <= NAMES.keys()


@pytest.mark.parametrize('recipe', RECIPES, ids=lambda r: r.recipe_id)
def test_all_recipes_scale_and_subtract_inventory_without_mutation(recipe):
    before = recipe.model_dump(mode='json')
    # Quantities add across households; no ceil/rounding is allowed in food needs.
    three, four, seven = [scale_recipe(recipe, n) for n in (3, 4, 7)]
    for a, b, c in zip(three, four, seven):
        assert abs(a.quantity + b.quantity - c.quantity) < Decimal('1e-20')
    for people in (1, 2, 4, 7):
        amounts = scale_recipe(recipe, people)
        # A household with half of each required ingredient must buy exactly the other half.
        pantry = [item.model_copy(update={'quantity': item.quantity / 2}) for item in amounts]
        request = Request(pantry=pantry, budget=0, days=1, people=people, max_cook_minutes=2000)
        slot = recipe.meal_slots[0]
        plan = Plan(meals=[Meal(day=1, slot=slot, recipe_id=recipe.recipe_id, servings=people)])
        balances, violations, incomplete = measure_plan(request, plan, [recipe], slots=(slot,))
        assert not violations and not incomplete
        expected = {(item.ingredient_id, item.unit): item.quantity / 2 for item in amounts}
        actual = {(line.ingredient_id, line.unit): line.missing_quantity for line in balances}
        assert actual.keys() == expected.keys()
        assert all(abs(actual[key] - value) < Decimal('1e-20') for key, value in expected.items())
    assert recipe.model_dump(mode='json') == before


def test_independent_source_quantities_and_all_ingredient_sections():
    # Source spaghetti: 1/2 lb beef and 12 oz pasta for 10 portions -> half for 5.
    items = {i.ingredient_id: i for i in scale_recipe(BY_ID['ml_one_pan_spaghetti'], 5)}
    assert items['ground_beef'].quantity == Decimal('113.3980925')
    assert items['dry_spaghetti'].quantity == Decimal('170.09713875')
    # Three quarts of cooking water are only in the instruction, not the ingredient list.
    pasta = {i.ingredient_id: i for i in scale_recipe(BY_ID['ml_pasta_caprese'], 2)}
    assert pasta['water'].quantity == Decimal('1419.529419') and pasta['water'].unit == 'ml'
    # The 1.25 oz taco seasoning packet must never become an unknown-size "piece".
    chili = {i.ingredient_id: i for i in BY_ID['ml_turkey_pumpkin_chili'].ingredients}
    assert chili['taco_seasoning'].quantity == Decimal('35.43690390625')
    assert chili['taco_seasoning'].unit == 'g'
    # "1/4 teaspoon each" means one full quarter-teaspoon of each food.
    fish = {i.ingredient_id: i.quantity for i in BY_ID['ml_fish_and_spinach_bake'].ingredients}
    assert fish['salt'] == fish['black_pepper'] == Decimal('1.2322303984375')


def test_prepared_foods_do_not_turn_into_raw_food_or_grams():
    bowl = {i.ingredient_id: i for i in BY_ID['ml_rice_bowl_southwestern_style'].ingredients}
    assert 'cooked_brown_rice' in bowl and 'dry_rice' not in bowl and 'rice' not in bowl
    assert bowl['cooked_brown_rice'].unit == 'ml'
    assert source_measurement('1 cup flour') == (Decimal('236.5882365'), 'ml')
    assert source_measurement('1 clove garlic') == (Decimal(1), 'pcs')
    for value in ('salt to taste', '1 pinch salt', '1 teaspoon salt as needed', 'dash of pepper', '1 package noodles'):
        with pytest.raises(ValueError):
            source_measurement(value)


def test_waiting_and_sequential_heat_are_not_hidden_by_header_totals():
    rows = {r['recipe_id']: r for r in load_reviewed_records()}
    assert rows['ml_overnight_oatmeal']['timing']['wait_minutes'] == [360, 720]
    assert BY_ID['ml_overnight_oatmeal'].cook_minutes == 735
    assert BY_ID['ml_fish_and_spinach_bake'].cook_minutes == 50  # 15 prep + 15 + 20 bake
    assert BY_ID['ml_vegetarian_tofu_enchiladas'].cook_minutes == 75  # 30 prep + 10 + 30 bake + 5 rest
    assert BY_ID['ml_salsa_chicken'].cook_minutes == 485  # includes prep omitted by header total
    assert rows['ml_one_pan_spaghetti']['timing']['wait_minutes'] is None


@pytest.mark.parametrize('allergy', ['peanut', 'milk', 'egg', 'wheat', 'soy', 'unknown_allergen'])
def test_any_active_allergy_blocks_all_50_before_llm_or_store(monkeypatch, allergy):
    case, provider = load_golden_case()
    case.profile.allergies = [allergy]
    case.profile.max_cooking_time = 2000
    def forbidden(*args, **kwargs):
        raise AssertionError('No model/store call is allowed for unverified composition')
    monkeypatch.setattr('smart_grocery.workflow.foodcom.plan_meals', forbidden)
    monkeypatch.setattr(provider, 'search_products', forbidden)
    assert not personalize_recipes(case.profile, RECIPES).ranked_recipes
    result = run_integration_workflow(case.profile, [], RECIPES, provider, days=1)
    assert result.attempts == 0 and result.plan is None
    assert [v.code for v in result.violations] == ['no_candidates']


def test_missing_real_prices_do_not_become_zero_and_meal_slots_are_respected():
    case, provider = load_golden_case()
    case.profile.allergies = []
    case.profile.max_cooking_time = 2000
    result = run_integration_workflow(case.profile, [], RECIPES, provider, days=1, mock_planner=True)
    assert result.plan and result.shopping_list.lines
    assert result.shopping_list.estimated_total is None and not result.valid
    assert all('breakfast' not in BY_ID[meal.recipe_id].meal_slots for meal in result.plan.meals)
    breakfast = run_integration_workflow(case.profile, [], RECIPES, provider, days=2,
                                         mock_planner=True, slots=('breakfast',))
    assert breakfast.plan and len(breakfast.plan.meals) == 2
    assert all(meal.slot == 'breakfast' and BY_ID[meal.recipe_id].meal_slots == ['breakfast']
               for meal in breakfast.plan.meals)


def test_excess_stock_never_makes_negative_missing_and_units_are_not_guessed():
    recipe = BY_ID['ml_salsa_chicken']
    req = Request(pantry=[Ingredient(ingredient_id='chicken_boneless', quantity=10000, unit='g'),
                           Ingredient(ingredient_id='salsa', quantity=5, unit='pcs')],
                  budget=0, days=1, people=2, max_cook_minutes=2000)
    plan = Plan(meals=[Meal(day=1, slot='dinner', recipe_id=recipe.recipe_id, servings=2)])
    balances, violations, incomplete = measure_plan(req, plan, [recipe], slots=('dinner',))
    assert next(b for b in balances if b.ingredient_id == 'chicken_boneless').missing_quantity == 0
    assert incomplete and any(v.code == 'unit_mismatch' for v in violations)


def test_tampered_source_or_missing_required_ingredient_fails_closed(tmp_path):
    source = (REVIEWED_DIR / 'sources.jsonl.gz').read_bytes()
    (tmp_path / 'sources.jsonl.gz').write_bytes(source)
    rows = load_reviewed_records()
    rows[0]['ingredients'].pop()
    path = tmp_path / 'corrections.jsonl'
    path.write_text('\n'.join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError, match='silently dropped'):
        load_reviewed_records(tmp_path)
    rows = load_reviewed_records()
    rows[0]['ingredients'][0]['quantity'] = '1000'
    path.write_text('\n'.join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError, match='Quantity disagrees'):
        load_reviewed_records(tmp_path)
    rows = load_reviewed_records()
    rows[0]['source_sha256'] = '0' * 64
    path.write_text('\n'.join(json.dumps(r) for r in rows))
    with pytest.raises(ValueError, match='Source/audit mismatch'):
        load_reviewed_records(tmp_path)


def test_reviewed_catalog_and_allergy_stop_in_streamlit(monkeypatch):
    monkeypatch.setenv('MOCK_LLM', 'true')
    app = AppTest.from_file(ROOT / 'app.py', default_timeout=30).run()
    app.radio(key='section').set_value('Каталог рецептов').run()
    app.radio(key='catalog_dataset').set_value('Подготовленные 50').run()
    assert not app.exception and app.dataframe
    assert any('не подтвержден' in c.value for c in app.caption)
    app.radio(key='section').set_value('Профиль и запасы').run()
    app.selectbox(key='sprint_recipe_source').set_value('Рецепты с проверенными данными · 50').run()
    app.button(key='sprint_submit').click().run()
    assert not app.exception and not app.metric
    assert any('нет подходящих рецептов' in w.value for w in app.warning)


def test_reviewed_inputs_are_complete_with_stock_and_no_price_lookup(monkeypatch):
    case, provider = load_golden_case()
    recipe = BY_ID['ml_skillet_mac_and_cheese']
    case.profile.allergies = []
    case.profile.max_cooking_time = 2000
    from smart_grocery.schemas.integration import InventoryItem
    inventory = [InventoryItem(ingredient_id=i.ingredient_id, quantity=i.quantity * 2,
                               unit=i.unit, display_name=i.ingredient_id, source='test', confidence=1)
                 for i in recipe.ingredients]
    def forbidden(*args, **kwargs):
        raise AssertionError('A fully stocked menu must not need a store lookup')
    monkeypatch.setattr(provider, 'search_products', forbidden)
    result = run_integration_workflow(case.profile, inventory, [recipe], provider, days=1, mock_planner=True)
    assert result.valid and not result.shopping_list.lines
    assert result.shopping_list.estimated_total == 0
