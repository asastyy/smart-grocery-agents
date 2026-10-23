"""Primary Streamlit UI for the integrated Food.com MVP."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env", override=False)

from smart_grocery.tools.recipes import load_ingredients, load_recipes
from smart_grocery.workflow.foodcom import run_foodcom_workflow


st.set_page_config(page_title="Smart Grocery Agents", page_icon="🥗", layout="wide")
st.title("Smart Grocery Agents")
st.caption("Меню, корзина и проверка бюджета на 150 подготовленных рецептах Food.com.")
st.warning(
    "Цены в CU демонстрационные. Часть исходных количеств обозначена в штуках; "
    "это учебная оценка, а не цены и фасовки магазина."
)

mock_mode = os.getenv("MOCK_LLM", "true").lower() == "true"
if mock_mode:
    st.info("Mock-режим: планировщик и критик не обращаются к LLM.")
else:
    planner_model = os.getenv("LLM_MODEL", "не настроена")
    critic_model = os.getenv("CRITIC_MODEL") or planner_model
    st.info(f"Live-режим · планировщик: {planner_model} · критик: {critic_model}")

ingredients = load_ingredients()
recipes = load_recipes()
recipes_by_id = {recipe["recipe_id"]: recipe for recipe in recipes}
unit_labels = {"g": "г", "ml": "мл", "pcs": "шт."}

with st.expander("Каталог рецептов"):
    query = st.text_input("Поиск по названию или ингредиенту", key="recipe_search")
    normalized_query = query.casefold()
    matching = [
        recipe
        for recipe in recipes
        if normalized_query in recipe["title"].casefold()
        or any(normalized_query in item["ingredient_id"].casefold() for item in recipe["ingredients"])
    ]
    st.caption(f"Найдено рецептов: {len(matching)}. Названия и состав сохранены на языке каталога.")
    if matching:
        recipe_id = st.selectbox(
            "Рецепт",
            [recipe["recipe_id"] for recipe in matching],
            key="browse_recipe",
            format_func=lambda value: recipes_by_id[value]["title"],
        )
        recipe = recipes_by_id[recipe_id]
        st.write(f"{recipe['cook_minutes']} минут · исходный рецепт на {recipe['servings']} порций")
        for item in recipe["ingredients"]:
            name = ingredients[item["ingredient_id"]]["canonical_name"]
            st.write(f"• {name}: {item['quantity']:g} {unit_labels[item['unit']]}")
        st.caption("Пошаговых инструкций приготовления в подготовленном наборе нет.")

if "pantry_items" not in st.session_state:
    st.session_state.pantry_items = {}

st.subheader("Что есть дома")
selected = st.selectbox(
    "Продукт",
    sorted(ingredients, key=lambda value: ingredients[value]["canonical_name"]),
    index=None,
    placeholder="Начните вводить название…",
    key="pantry_product",
    format_func=lambda value: ingredients[value]["canonical_name"],
)
selected_unit = ingredients[selected]["base_unit"] if selected else None
with st.form("add_pantry", clear_on_submit=True):
    quantity = st.number_input(
        f"Количество{', ' + unit_labels[selected_unit] if selected_unit else ''}",
        min_value=0.0,
        value=1.0,
        step=1.0,
        key="pantry_quantity",
    )
    add = st.form_submit_button("Добавить в запасы", disabled=selected is None, key="add_pantry")
if add and selected:
    if quantity <= 0:
        st.error("Укажите количество больше нуля.")
    else:
        st.session_state.pantry_items[selected] = st.session_state.pantry_items.get(selected, 0.0) + quantity

if st.session_state.pantry_items:
    for ingredient_id, amount in list(st.session_state.pantry_items.items()):
        name_col, amount_col, remove_col = st.columns([3, 2, 1])
        name_col.write(ingredients[ingredient_id]["canonical_name"])
        amount_col.write(f"{amount:g} {unit_labels[ingredients[ingredient_id]['base_unit']]}")
        if remove_col.button("Удалить", key=f"remove_{ingredient_id}"):
            del st.session_state.pantry_items[ingredient_id]
            st.rerun()
    if st.button("Очистить запасы", key="clear_pantry"):
        st.session_state.pantry_items = {}
        st.rerun()
else:
    st.caption("Запасы не добавлены: все нужные ингредиенты попадут в список покупок.")

st.subheader("Параметры меню")
with st.form("request"):
    budget = st.number_input("Бюджет, CU", min_value=0.0, value=25.0, key="budget")
    days = st.slider("Дни", 1, 7, 3, key="days")
    people = st.number_input("Количество людей", min_value=1, value=2, step=1, key="people")
    max_cook = st.number_input(
        "Максимальное время приготовления, минут", min_value=1, value=30, key="max_cook"
    )
    submit = st.form_submit_button("Составить меню", type="primary", key="plan_menu")


def current_request() -> dict:
    pantry = [
        {
            "ingredient_id": ingredient_id,
            "quantity": amount,
            "unit": ingredients[ingredient_id]["base_unit"],
        }
        for ingredient_id, amount in st.session_state.pantry_items.items()
    ]
    return {
        "pantry": pantry,
        "budget": budget,
        "currency": "CU",
        "days": days,
        "people": people,
        "diet": ["vegetarian"],
        "max_cook_minutes": max_cook,
    }


request = current_request()
if submit:
    st.session_state.pop("workflow_error", None)
    if not mock_mode and not all(os.getenv(name, "").strip() for name in ("LLM_API_KEY", "LLM_MODEL")):
        st.session_state.pop("workflow_run", None)
        st.session_state.workflow_error = (
            "Для live-режима заполните LLM_API_KEY и LLM_MODEL в локальном .env, "
            "затем перезапустите приложение."
        )
    else:
        try:
            with st.spinner("Ищем рецепты, планируем и проверяем меню…"):
                result = run_foodcom_workflow(request)
            st.session_state.workflow_run = {"request": request, **result, "mode": "mock" if mock_mode else "live"}
        except Exception:
            st.session_state.pop("workflow_run", None)
            st.session_state.workflow_error = (
                "Не удалось завершить расчёт. Проверьте данные и настройки API; "
                "детали ответа провайдера скрыты."
            )

if st.session_state.get("workflow_error"):
    st.error(st.session_state.workflow_error)

run = st.session_state.get("workflow_run")
if run is not None:
    if run["request"] != request:
        st.warning("Параметры изменены. Результат ниже относится к сохранённому запросу.")
    with st.expander("Сохранённый запрос"):
        st.json(run["request"])

    assessment = run["assessment"]
    if assessment["valid"]:
        st.success("Меню прошло Python-проверку")
    else:
        st.warning("Меню требует исправления")
        for violation in assessment["violations"]:
            st.error(f"{violation['code']}: {violation['message']}")

    if assessment["total_cost"] is None:
        st.error("Полная стоимость неизвестна: часть позиций не удалось оценить.")
        st.metric("Стоимость оценённых позиций", f"{assessment['priced_subtotal']:.2f} CU")
    else:
        st.metric("Расчётная стоимость", f"{assessment['total_cost']:.2f} CU")

    st.subheader("Меню")
    meals = run["plan"]["meals"]
    if meals:
        st.dataframe(
            [
                {
                    "День": meal["day"],
                    "Приём пищи": {"lunch": "Обед", "dinner": "Ужин"}.get(meal["slot"], meal["slot"]),
                    "Блюдо": recipes_by_id.get(meal["recipe_id"], {}).get("title", meal["recipe_id"]),
                    "Порций": meal["servings"],
                }
                for meal in meals
            ],
            hide_index=True,
        )
    else:
        st.info("Меню не сформировано. Измените ограничения и повторите поиск.")

    st.subheader("Список покупок")
    if assessment["shopping_list"]:
        st.dataframe(assessment["shopping_list"], hide_index=True)
    else:
        st.info("Покупки не требуются либо список нельзя построить из текущих данных.")

    st.subheader("Критик и история попыток")
    if not run["agent_trace"]:
        st.caption("Попыток планирования не было: подходящие рецепты не найдены.")
    for entry in run["agent_trace"]:
        feedback = entry["assessment"].get("feedback", "")
        with st.expander(f"Попытка {entry['attempt']}"):
            if "Critic [LLM," in feedback:
                st.success("Получен и проверен ответ LLM-критика.")
            elif "Critic [mock]" in feedback:
                st.info("Сработал mock-критик; внешнего вызова не было.")
            elif "Critic unavailable" in feedback:
                st.warning("Критик недоступен; Python-нарушения остаются действующими.")
            else:
                st.caption("Критик не вызывался: эта попытка прошла проверку.")
            st.json(entry)

    st.download_button(
        "Скачать результат JSON",
        json.dumps(run, ensure_ascii=False, indent=2),
        file_name="smart-grocery-result.json",
        mime="application/json",
    )
