from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_foodcom_preview_runs_real_data_in_mock_mode(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app_foodcom.py",
                           default_timeout=30).run()
    app.button[0].click().run()
    assert not app.exception
    assert app.success
    assert len(app.dataframe[0].value) == 6
    app.number_input[0].set_value(0.0)
    app.button[0].click().run()
    assert not app.exception
    assert not app.success
    assert "Critic [mock]" in app.text[0].value
