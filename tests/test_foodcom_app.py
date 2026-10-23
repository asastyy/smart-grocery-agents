from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_foodcom_preview_runs_real_data_in_mock_mode(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py",
                           default_timeout=30).run()
    app.button(key="plan_menu").click().run()
    assert not app.exception
    assert app.success
    assert len(app.dataframe[0].value) == 6
    app.number_input(key="budget").set_value(0.0)
    app.button(key="plan_menu").click().run()
    assert not app.exception
    assert not app.success
    assert any("mock-критик" in item.value for item in app.info)


def test_pantry_controls_send_quantities_and_support_removal(monkeypatch):
    from smart_grocery.workflow import foodcom
    received = []
    original = foodcom.run_foodcom_workflow
    def capture(request):
        received.append(request)
        return original(request)
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setattr(foodcom, "run_foodcom_workflow", capture)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py",
                           default_timeout=30).run()
    assert not app.text_area
    app.selectbox(key="pantry_product").select("onion").run()
    app.number_input(key="pantry_quantity").set_value(2.0)
    app.button(key="add_pantry").click().run()
    app.button(key="plan_menu").click().run()
    assert not app.exception
    assert received[-1]["pantry"] == [{"ingredient_id": "onion", "quantity": 2.0, "unit": "pcs"}]
    app.number_input(key="pantry_quantity").set_value(3.0)
    app.button(key="add_pantry").click().run()
    assert app.session_state["pantry_items"]["onion"] == 5.0
    assert app.session_state["pantry_items"]["onion"] == 5.0
    app.button(key="remove_onion").click().run()
    assert app.session_state["pantry_items"] == {}
    app.button(key="plan_menu").click().run()
    assert received[-1]["pantry"] == []


def test_recipe_search_shows_names_and_handles_no_match(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py",
                           default_timeout=30).run()
    app.text_input(key="recipe_search").set_value("Cabbage Soup").run()
    assert not app.exception
    assert "Cabbage Soup" in app.selectbox(key="browse_recipe").options
    app.text_input(key="recipe_search").set_value("nonexistent-recipe-xyz").run()
    assert not app.exception
    assert any("Найдено рецептов: 0" in c.value for c in app.caption)
