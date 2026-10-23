from pathlib import Path

from streamlit.testing.v1 import AppTest

from smart_grocery.workflow import foodcom


ROOT = Path(__file__).resolve().parents[1]


def start_app(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    assert not app.exception
    return app


def test_valid_menu_display(monkeypatch):
    app = start_app(monkeypatch)
    app.button(key="plan_menu").click().run()
    assert not app.exception
    assert any("Меню прошло проверку" in item.value for item in app.success)
    assert app.metric[0].label == "Стоимость"
    assert len(app.dataframe[0].value) == 6
    assert app.download_button


def test_over_budget_is_not_success(monkeypatch):
    app = start_app(monkeypatch)
    app.number_input(key="budget").set_value(0.0)
    app.button(key="plan_menu").click().run()
    assert not app.exception
    assert not any("Меню прошло проверку" in item.value for item in app.success)
    assert any("Бюджет превышен" in item.value for item in app.markdown)
    assert app.metric[0].label == "Стоимость"
    assert len(app.expander) >= 2


def test_unknown_prices_show_incomplete_estimate(monkeypatch):
    monkeypatch.setattr(foodcom, "load_prices", lambda: {})
    app = start_app(monkeypatch)
    app.button(key="plan_menu").click().run()
    assert not app.exception
    assert any("нет цены" in item.value for item in app.markdown)
    assert any("нет сопоставимой цены" in item.value for item in app.caption)
    assert app.metric[0].label == "Оценённая часть"


def test_no_eligible_recipes_is_explained(monkeypatch):
    monkeypatch.setattr(foodcom, "search_recipes", lambda request: {"candidates": []})
    app = start_app(monkeypatch)
    app.button(key="plan_menu").click().run()
    assert not app.exception
    assert any("Подходящие рецепты не найдены" in item.value for item in app.markdown)
    assert any("Меню не сформировано" in item.value for item in app.info)
