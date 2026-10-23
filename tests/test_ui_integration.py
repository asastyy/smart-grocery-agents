from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_result_survives_rerun_and_labels_saved_inputs(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    app.button(key="plan_menu").click().run()
    assert not app.exception
    assert app.success
    original_cost = app.metric[0].value

    app.selectbox(key="pantry_product").select("onion").run()
    app.button(key="add_pantry").click().run()
    assert not app.exception
    assert app.metric[0].value == original_cost
    assert any("Параметры изменены" in item.value for item in app.warning)

    app.number_input(key="budget").set_value(0.0)
    app.button(key="plan_menu").click().run()
    assert not any("прошло Python-проверку" in item.value for item in app.success)
    assert any("over_budget" in item.value for item in app.error)
    assert any("Попытка 2" in item.label for item in app.expander)


def test_live_missing_key_shows_actionable_error(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    app.button(key="plan_menu").click().run()
    assert not app.exception
    assert "LLM_API_KEY" in app.error[0].value
    assert not app.success
    assert not app.metric
