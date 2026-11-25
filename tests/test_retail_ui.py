from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def test_offline_retail_view_shows_real_packages_and_does_not_claim_safety(monkeypatch):
    import httpx
    monkeypatch.setenv("MOCK_LLM", "true")
    def no_network(*args, **kwargs):
        raise AssertionError("Offline retail view must not use the network")
    monkeypatch.setattr(httpx.Client, "send", no_network)
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    app.toggle(key="retail_demo").set_value(True).run()
    assert not app.exception
    table = app.dataframe[0].value
    assert len(table) == 3
    assert table.iloc[0]["Упаковок"] == 1
    assert table.iloc[0]["Оценка, ₽"] == 146
    assert "Аллергены не подтверждены" in table.iloc[0]["Проверка"]
    assert app.download_button and not app.success
    app.selectbox(key="retail_ingredient").set_value("olive_oil").run()
    assert not app.exception and app.info
