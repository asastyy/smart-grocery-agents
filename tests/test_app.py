import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from smart_grocery.tools import budget


def start_app(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    app = AppTest.from_file(
        Path(__file__).resolve().parents[1] / "app.py", default_timeout=30
    ).run()
    assert not app.exception
    return app


def test_valid_menu_display(monkeypatch):
    app = start_app(monkeypatch)
    app.button[0].click().run()
    assert not app.exception
    assert app.success[0].value == "Valid plan"
    assert app.metric[0].value == "3.50 EUR"
    assert not app.error
    assert len(app.dataframe) == 1


def test_over_budget_is_not_success(monkeypatch):
    app = start_app(monkeypatch)
    app.number_input[0].set_value(0.0)
    app.button[0].click().run()
    assert not app.exception
    assert not app.success
    assert app.warning
    assert any("Budget exceeded" in error.value for error in app.error)
    assert "unvalidated" in app.metric[0].label


def test_unknown_prices_show_incomplete_estimate(monkeypatch, tmp_path):
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(budget, "PRICES", prices)
    app = start_app(monkeypatch)
    app.button[0].click().run()
    assert not app.exception
    assert not app.success
    assert any("Unknown price" in error.value for error in app.error)
    assert any("incomplete" in error.value for error in app.error)
    assert "unvalidated" in app.metric[0].label
    assert "does not confirm" in app.info[0].value


def test_no_eligible_recipes_shows_error(monkeypatch):
    monkeypatch.setattr("smart_grocery.workflow.runner.search_recipes", lambda request: [])
    app = start_app(monkeypatch)
    app.button[0].click().run()
    assert not app.exception
    assert not app.success
    assert not app.metric
    assert app.error[0].value == "No eligible recipes"
