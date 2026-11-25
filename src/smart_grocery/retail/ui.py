"""Catalogue research UI; never calls checkout or selects unknown stock as safe."""
import os

import streamlit as st

from smart_grocery.retail.matching import SPECS
from smart_grocery.retail.mcp import MCPClient
from smart_grocery.retail.purchasing import eligibility_reasons, quote_packages
from smart_grocery.retail.snapshot import snapshot_provider
from smart_grocery.retail.vkusvill import VkusVillProvider
from smart_grocery.tools.grocery_provider import ProviderUnavailable


LABELS = {"rice": "Рис", "egg": "Куриные яйца", "chicken_breast": "Куриная грудка",
          "milk": "Молоко", "tomato": "Помидоры", "olive_oil": "Оливковое масло"}
UNITS = {"g": "г", "ml": "мл", "pcs": "шт."}
REASONS = {"availability_unknown": "Наличие по адресу неизвестно", "allergens_unknown": "Аллергены не подтверждены",
           "stale_or_future_offer": "Нужно обновить предложение", "out_of_stock": "Нет в наличии",
           "allergen_conflict": "Содержит исключённый аллерген", "unknown_price": "Нет подтверждённой цены",
           "unit_mismatch": "Несовместимые единицы", "currency_mismatch": "Другая валюта"}


def render_retail_demo():
    st.subheader("Товары и упаковки")
    st.caption("ВкусВилл · реальные ответы публичного каталога. Заказы и оплата не выполняются.")
    ingredient = st.selectbox("Ингредиент", list(SPECS), format_func=LABELS.get, key="retail_ingredient")
    unit = SPECS[ingredient].unit
    amount = st.number_input(f"Нужно докупить, {UNITS[unit]}", min_value=1.0,
                             value=4.0 if unit == "pcs" else 600.0, key=f"retail_amount_{unit}")
    peanut = st.checkbox("Исключить арахис", value=True, key="retail_peanut")
    live = st.button("Обновить предложения ВкусВилла", key="retail_refresh")
    if live:
        provider = VkusVillProvider(MCPClient(token=os.getenv("VKUSVILL_ACCESS_TOKEN")))
        try:
            with st.spinner("Получаем предложения…"):
                found = provider.search_products(ingredient)
            st.session_state.retail_current = {"ingredient": ingredient, "offers": found,
                                               "issues": provider.issues, "mode": "live"}
        except ProviderUnavailable:
            st.error("Каталог сейчас недоступен. Сохранённый снимок остаётся доступен.")
        finally:
            provider.close()
    current = st.session_state.get("retail_current")
    if not current or current["ingredient"] != ingredient:
        provider = snapshot_provider()
        current = {"offers": provider.search_products(ingredient), "issues": provider.issues, "mode": "snapshot"}
    offers = current["offers"]
    if offers:
        timestamp = min(offer.retrieved_at for offer in offers)
        st.caption(f"{'Свежий запрос' if current['mode'] == 'live' else 'Сохранённый снимок'} · {timestamp:%d.%m.%Y %H:%M} UTC")
    st.warning("Без адресного наличия и подтверждённых аллергенов предложения требуют проверки. Расчёт ниже — оценка по каталогу.")
    if not offers:
        st.info("В этом снимке нет товаров с подтверждённым размером подходящей упаковки.")
    rows, export = [], []
    for offer in offers:
        blockers = eligibility_reasons(offer, unit=unit, currency="RUB", allergies=("peanut",) if peanut else ())
        quote = quote_packages(offer, str(amount)) if offer.price is not None else None
        rows.append({"Товар": offer.title, "Упаковка": f"{offer.package_quantity:g} {UNITS[offer.package_unit]}",
                     "Цена, ₽": float(offer.price) if offer.price is not None else None,
                     "Упаковок": quote.package_count if quote else None,
                     "Купить": f"{quote.purchased_quantity:g} {UNITS[unit]}" if quote else None,
                     "Остаток": f"{quote.surplus_quantity:g} {UNITS[unit]}" if quote else None,
                     "Оценка, ₽": float(quote.total) if quote else None,
                     "Проверка": "; ".join(REASONS.get(reason, reason) for reason in blockers) or "Условия проверены",
                     "Карточка": str(offer.url) if offer.url else None})
        export.append({"offer": offer.model_dump(mode="json"), "quote": quote.model_dump(mode="json") if quote else None,
                       "selection_blockers": blockers})
    if rows:
        st.dataframe(rows, hide_index=True, column_config={"Карточка": st.column_config.LinkColumn("Карточка")})
        import json
        st.download_button("Скачать предложения и расчёт", json.dumps(export, ensure_ascii=False, indent=2),
                           file_name="retail-quotes.json", mime="application/json", key="retail_download")
    if current["issues"]:
        with st.expander("Неоднозначные предложения"):
            issue_labels = {"variable_weight_price_not_package": "Цена за вес — фиксированная упаковка неизвестна",
                            "package_quantity_unverified": "Размер упаковки в нужных единицах неизвестен",
                            "match_rejected": "Товар отличается по составу или форме", "match_review": "Нужно подтвердить соответствие"}
            for issue in current["issues"]:
                st.write(f"SKU {issue.product_id} · {issue_labels.get(issue.code, issue.code)}")
