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
    assert any("предыдущих параметров" in item.value for item in app.caption)

    app.number_input(key="budget").set_value(0.0)
    app.button(key="plan_menu").click().run()
    assert not any("Меню прошло проверку" in item.value for item in app.success)
    assert any("Бюджет превышен" in item.value for item in app.markdown)
    assert any("Попытка 2" in item.value for item in app.markdown)


def test_live_missing_key_shows_actionable_error(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    app.button(key="plan_menu").click().run()
    assert not app.exception
    assert "LLM_API_KEY" in app.error[0].value
    assert not app.success
    assert not app.metric
