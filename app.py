"""Минималистичный Streamlit-интерфейс проекта Smart Grocery Agents."""
from __future__ import annotations

import json
import os
from html import escape
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
st.markdown(
    """
    <style>
    :root {
        --ink: #171717;
        --muted: #6b7280;
        --line: #e5e7eb;
        --soft: #f7f7f5;
        --accent: #1f6f5b;
    }
    .stApp { background: #ffffff; color: var(--ink); }
    .block-container { max-width: 1160px; padding-top: 3.4rem; padding-bottom: 5rem; }
    [data-testid="stHeader"] { background: rgba(255,255,255,.95); }
    h1, h2, h3, p, label, [data-testid="stMetricLabel"], [data-testid="stMetricValue"] {
        color: var(--ink) !important;
    }
    h1 { font-size: 3rem !important; letter-spacing: -0.045em; font-weight: 680 !important; }
    h2 { font-size: 1.55rem !important; letter-spacing: -0.025em; }
    h3 { font-size: 1.15rem !important; }
    [data-testid="stCaptionContainer"] { color: var(--muted); }
    [data-testid="stExpander"] {
        border: 1px solid var(--line); border-radius: 12px; background: #fff;
    }
    [data-testid="stForm"] { border: 0; padding: 0; }
    [data-testid="stAlert"] { border-radius: 10px; border: 1px solid var(--line); }
    div[data-testid="stButton"] button, div[data-testid="stFormSubmitButton"] button {
        border-radius: 9px; min-height: 2.7rem; font-weight: 600;
    }
    div[data-testid="stFormSubmitButton"] button[kind="primary"] {
        background: var(--ink); border-color: var(--ink); color: #fff;
    }
    div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
        background: #303030; border-color: #303030;
    }
    [data-testid="stMetric"] {
        background: var(--soft); border: 1px solid var(--line); border-radius: 12px; padding: 1rem 1.1rem;
    }
    [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
    [data-testid="stVerticalBlockBorderWrapper"] > div { border-color: var(--line); border-radius: 16px; }
    [data-testid="stTabs"] button[role="tab"] { font-weight: 600; padding: .7rem 1.1rem; }
    .sg-meal { padding: 1.3rem 1.4rem; border: 1px solid var(--line); border-radius: 14px; min-height: 176px; background: #fff; margin: .7rem 0; }
    .sg-meal-slot { color: var(--accent); font-size: .75rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; }
    .sg-meal-title { font-size: 1.3rem; font-weight: 650; line-height: 1.35; margin: .7rem 0 1rem; overflow-wrap: anywhere; }
    .sg-meal-meta { font-size: .86rem; color: var(--muted); }
    .sg-empty { padding: 2.2rem; margin-top: 1.8rem; border-radius: 16px; background: var(--soft); text-align: center; }
    .sg-empty strong { display: block; font-size: 1.2rem; margin-bottom: .5rem; }
    .sg-empty span { color: var(--muted); font-size: .95rem; }
    .sg-footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--line); color: var(--muted); font-size: .8rem; }
    @media (max-width: 640px) { h1 { font-size: 2.1rem !important; } .block-container { padding-top: 2rem; } }
    .sg-kicker { color: var(--accent); font-size: .82rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
    .sg-lead { max-width: 720px; color: var(--muted); font-size: 1.08rem; line-height: 1.55; margin: .35rem 0 1.2rem; }
    .sg-rule { height: 1px; background: var(--line); margin: 1.4rem 0 2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown('<div class="sg-kicker">Планирование питания</div>', unsafe_allow_html=True)
st.title("Smart Grocery Agents")
st.markdown(
    '<div class="sg-lead">Ваши запасы и планы на неделю. Меню и покупки — в одном месте.</div>',
    unsafe_allow_html=True,
)

mock_mode = os.getenv("MOCK_LLM", "true").lower() == "true"
if mock_mode:
    st.caption("Демонстрационный режим · без обращения к внешней модели")
else:
    planner_model = os.getenv("LLM_MODEL", "не настроена")
    critic_model = os.getenv("CRITIC_MODEL") or planner_model
    st.caption(f"Gemini · планирование: {planner_model} · проверка рекомендаций: {critic_model}")

st.markdown('<div class="sg-rule"></div>', unsafe_allow_html=True)

ingredients = load_ingredients()
recipes = load_recipes()
recipes_by_id = {recipe["recipe_id"]: recipe for recipe in recipes}
unit_labels = {"g": "г", "ml": "мл", "pcs": "шт."}

with st.expander("Каталог"):
    query = st.text_input("Поиск по названию или ингредиенту", key="recipe_search")
    normalized_query = query.casefold()
    matching = [
        recipe
        for recipe in recipes
        if normalized_query in recipe["title"].casefold()
        or any(normalized_query in item["ingredient_id"].casefold() for item in recipe["ingredients"])
    ]
    st.caption(f"Найдено рецептов: {len(matching)}")
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
        st.caption("В наборе нет пошаговых инструкций.")

if "pantry_items" not in st.session_state:
    st.session_state.pantry_items = {}

pantry_col, request_col = st.columns([1, 1], gap="large")
with pantry_col, st.container(border=True):
    st.subheader("Что есть дома")
    selected = st.selectbox(
        "Продукт",
        sorted(ingredients, key=lambda value: ingredients[value]["canonical_name"]),
        index=None,
        placeholder="Введите название",
        key="pantry_product",
        format_func=lambda value: ingredients[value]["canonical_name"],
    )
    selected_unit = ingredients[selected]["base_unit"] if selected else None
    with st.form("add_pantry", clear_on_submit=True, border=False):
        quantity = st.number_input(
            f"Количество{', ' + unit_labels[selected_unit] if selected_unit else ''}",
            min_value=0.0,
            value=1.0,
            step=1.0,
            key="pantry_quantity",
        )
        add = st.form_submit_button("Добавить", disabled=selected is None, key="add_pantry")
    if add and selected:
        if quantity <= 0:
            st.error("Количество должно быть больше нуля.")
        else:
            st.session_state.pantry_items[selected] = st.session_state.pantry_items.get(selected, 0.0) + quantity

    if st.session_state.pantry_items:
        for ingredient_id, amount in list(st.session_state.pantry_items.items()):
            name_col, amount_col, remove_col = st.columns([3, 2, 1])
            name_col.write(ingredients[ingredient_id]["canonical_name"])
            amount_col.write(f"{amount:g} {unit_labels[ingredients[ingredient_id]['base_unit']]}")
            if remove_col.button("×", key=f"remove_{ingredient_id}", help="Удалить"):
                del st.session_state.pantry_items[ingredient_id]
                st.rerun()
        if st.button("Очистить", key="clear_pantry"):
            st.session_state.pantry_items = {}
            st.rerun()
    else:
        st.caption("Пока продуктов нет.")

with request_col, st.container(border=True):
    st.subheader("Ваш план")
    st.caption("Вегетарианское меню · обед и ужин")
    with st.form("request", border=False):
        budget = st.number_input("Бюджет, CU", min_value=0.0, value=25.0, key="budget")
        days = st.slider("Дни", 1, 7, 3, key="days")
        people = st.number_input("Люди", min_value=1, value=2, step=1, key="people")
        max_cook = st.number_input("Время приготовления, минут", min_value=1, value=30, key="max_cook")
        submit = st.form_submit_button("Составить меню", type="primary", key="plan_menu", use_container_width=True)

st.caption("Цены указаны в условных единицах CU.")


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


VIOLATION_LABELS = {
    "invalid_input": "Проверьте параметры запроса.",
    "duplicate_recipe": "В меню повторяется один и тот же рецепт.",
    "meal_slots": "На каждый день нужен один обед и один ужин.",
    "servings_mismatch": "Количество порций не совпадает с числом людей.",
    "unknown_recipe": "В меню найден неизвестный рецепт.",
    "invalid_recipe": "В рецепте есть некорректные данные.",
    "diet_mismatch": "Рецепт не соответствует ограничению питания.",
    "cook_time": "Рецепт готовится дольше указанного времени.",
    "unit_mismatch": "Единицы измерения нельзя сопоставить.",
    "missing_price": "Для части продуктов нет цены.",
    "invalid_price": "Для части продуктов указана некорректная цена.",
    "price_mismatch": "Единица цены не совпадает с единицей продукта.",
    "over_budget": "Бюджет превышен.",
    "incomplete_cost": "Полную стоимость рассчитать нельзя.",
    "no_candidates": "Подходящие рецепты не найдены.",
}


def violation_text(violation: dict) -> str:
    return VIOLATION_LABELS.get(violation["code"], violation["message"])


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
        st.caption("Показан результат для предыдущих параметров.")

    assessment = run["assessment"]
    if assessment["valid"]:
        st.success("Меню прошло проверку")
    else:
        st.warning("Проверьте ограничения")
        for violation in assessment["violations"]:
            st.write(f"— {violation_text(violation)}")

    cost_col, days_col, meals_col = st.columns(3)
    if assessment["total_cost"] is None:
        cost_col.metric("Оценённая часть", f"{assessment['priced_subtotal']:.2f} CU")
        st.caption("Для части продуктов нет сопоставимой цены.")
    else:
        cost_col.metric("Стоимость", f"{assessment['total_cost']:.2f} CU")
    days_col.metric("Дни", run["request"]["days"])
    meals_col.metric("Блюда", len(run["plan"]["meals"]))

    st.markdown('<div class="sg-rule"></div>', unsafe_allow_html=True)
    st.subheader("Ваше меню")
    meals = run["plan"]["meals"]
    if meals:
        day_numbers = sorted({meal["day"] for meal in meals})
        for day, tab in zip(day_numbers, st.tabs([f"День {day}" for day in day_numbers])):
            with tab:
                day_meals = [meal for meal in meals if meal["day"] == day]
                meal_columns = st.columns(2)
                for index, meal in enumerate(day_meals):
                    recipe = recipes_by_id.get(meal["recipe_id"], {})
                    slot = {"lunch": "Обед", "dinner": "Ужин"}.get(meal["slot"], meal["slot"])
                    title = recipe.get("title", meal["recipe_id"])
                    minutes = recipe.get("cook_minutes")
                    meta = f"{minutes} мин · " if minutes is not None else ""
                    meta += f"Порций: {meal['servings']}"
                    with meal_columns[index % 2]:
                        st.markdown(
                            f'<div class="sg-meal"><div class="sg-meal-slot">{escape(str(slot))}</div>'
                            f'<div class="sg-meal-title">{escape(str(title))}</div>'
                            f'<div class="sg-meal-meta">{escape(meta)}</div></div>',
                            unsafe_allow_html=True,
                        )
        with st.expander("Всё меню таблицей"):
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
                use_container_width=True,
            )
    else:
        st.info("Меню не сформировано. Измените ограничения и повторите поиск.")

    st.subheader("Список покупок")
    if assessment["shopping_list"]:
        st.dataframe(
            [
                {
                    "Продукт": ingredients.get(item["ingredient_id"], {}).get(
                        "canonical_name", item["ingredient_id"]
                    ),
                    "Количество": item["quantity"],
                    "Единица": unit_labels.get(item["unit"], item["unit"]),
                    "Цена": item["unit_price"],
                    "Стоимость": item["cost"],
                }
                for item in assessment["shopping_list"]
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("Список пуст.")

    with st.expander("Технические детали"):
        st.caption("Стоимость и ограничения проверяет Python. Gemini выбирает меню и формирует рекомендации.")
        if not run["agent_trace"]:
            st.write("Подходящие рецепты не найдены.")
        for entry in run["agent_trace"]:
            feedback = entry["assessment"].get("feedback", "")
            st.markdown(f"**Попытка {entry['attempt']}**")
            if "Critic [LLM," in feedback:
                st.write("Gemini сформировал рекомендацию для повторного планирования.")
            elif "Critic [mock]" in feedback:
                st.info("Сработал mock-критик; внешнего вызова не было.")
            elif "Critic unavailable" in feedback:
                st.write("Рекомендация модели недоступна; результат проверки сохранён.")
            else:
                st.write("Дополнительная рекомендация не потребовалась.")

    st.download_button(
        "Скачать результат",
        json.dumps(run, ensure_ascii=False, indent=2),
        file_name="smart-grocery-result.json",
        mime="application/json",
    )
elif not st.session_state.get("workflow_error"):
    st.markdown(
        '<div class="sg-empty"><strong>Меньше планирования. Больше времени на себя.</strong>'
        '<span>Задайте параметры — здесь появятся меню и список покупок.</span></div>',
        unsafe_allow_html=True,
    )

st.markdown(
    '<div class="sg-footer">Smart Grocery Agents · Учебный MVP · Цены в условных единицах CU</div>',
    unsafe_allow_html=True,
)
