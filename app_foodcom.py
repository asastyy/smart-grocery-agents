"""Integration preview for roles 1–3; does not replace role 4's UI."""
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from smart_grocery.workflow.foodcom import run_foodcom_workflow

st.set_page_config(page_title="Smart Grocery — Food.com")
st.title("Smart Grocery — Food.com")
st.caption("150 рецептов. Демо-цены в CU, не реальные цены магазинов. Обед и ужин каждый день.")
st.warning("Единицы в данных ещё требуют проверки: часть продуктов указана в pcs. Стоимость демонстрационная.")
with st.form("request"):
    budget = st.number_input("Бюджет, CU", min_value=0.0, value=25.0)
    days = st.slider("Дни", 1, 7, 3)
    people = st.number_input("Количество людей", min_value=1, value=2, step=1)
    max_cook = st.number_input("Время приготовления, минут", min_value=1, value=30)
    pantry = st.text_area("Запасы в JSON: ingredient_id, quantity, unit (g/ml/pcs)", "[]")
    st.caption('Пример: [{"ingredient_id":"onion","quantity":2,"unit":"pcs"}]')
    submit = st.form_submit_button("Составить меню")
if submit:
    st.session_state.pop("foodcom_result", None)
    try:
        request = {"pantry": json.loads(pantry), "budget": budget, "currency": "CU",
                   "days": days, "people": people, "diet": ["vegetarian"],
                   "max_cook_minutes": max_cook}
        with st.spinner("Планирование и проверка…"):
            st.session_state.foodcom_result = run_foodcom_workflow(request)
    except Exception:
        st.error("Не удалось завершить расчёт. Проверьте формат запроса, доступность данных и настройки API.")
if "foodcom_result" in st.session_state:
    result = st.session_state.foodcom_result
    assessment = result["assessment"]
    if assessment["valid"]:
        st.success("Меню прошло проверку")
    else:
        st.warning("Меню требует исправления")
    if assessment["total_cost"] is None:
        st.error("Полная стоимость неизвестна")
        st.metric("Стоимость только оценённых позиций, CU", assessment["priced_subtotal"])
    else:
        st.metric("Расчётная стоимость, CU", assessment["total_cost"])
    if result["plan"]["meals"]:
        st.dataframe(result["plan"]["meals"], hide_index=True)
    if assessment["shopping_list"]:
        st.dataframe(assessment["shopping_list"], hide_index=True)
    if assessment["feedback"]:
        st.text(assessment["feedback"])
    with st.expander("Попытки планирования и полный результат"):
        st.json(result)
