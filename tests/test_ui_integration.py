from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_result_survives_rerun_and_labels_saved_inputs(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    app.button[0].click().run()
    assert not app.exception
    assert app.success
    app.number_input[0].set_value(0.0).run()
    assert not app.exception
    assert app.metric[0].value == "3.50 EUR"
    assert any("Inputs changed" in item.value for item in app.warning)
    app.button[0].click().run()
    assert not app.success
    assert any("Budget exceeded" in item.value for item in app.error)
    assert any("attempt 2" in item.label for item in app.expander)


def test_live_missing_key_shows_actionable_error(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    app.button[0].click().run()
    assert not app.exception
    assert "LLM_API_KEY" in app.error[0].value
    assert not app.success
    assert not app.metric
