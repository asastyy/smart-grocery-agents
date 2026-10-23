"""Integration preview for roles 1–3; does not replace role 4's UI."""
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from smart_grocery.workflow.foodcom import run_foodcom_workflow
from smart_grocery.tools.recipes import load_ingredients, load_recipes

st.set_page_config(page_title="Smart Grocery — Food.com")
st.title("Smart Grocery — Food.com")
st.caption("150 рецептов. Демо-цены в CU, не реальные цены магазинов. Обед и ужин каждый день.")
st.warning("Единицы в данных ещё требуют проверки: часть продуктов указана в pcs. Стоимость демонстрационная.")
mock_mode = os.getenv("MOCK_LLM", "true").lower() == "true"
if mock_mode:
    st.info("Режим заглушки: обращения к модели отключены.")
else:
    st.info(f"Вызовы API включены. Планировщик: {os.getenv('LLM_MODEL', 'не настроен')}. "
            f"Критик: {os.getenv('CRITIC_MODEL') or os.getenv('LLM_MODEL', 'не настроен')}.")
st.caption("Критик вызывается автоматически, когда проверка меню находит нарушения. "
           "Для проверки оставьте запасы пустыми и задайте бюджет 0 CU, затем нажмите «Составить меню».")
ingredients = load_ingredients()
recipes = load_recipes()
recipes_by_id = {r["recipe_id"]: r for r in recipes}
unit_labels = {"g": "г", "ml": "мл", "pcs": "шт."}
with st.expander("Посмотреть рецепты"):
    query = st.text_input("Поиск по названию или ингредиенту", key="recipe_search")
    matching = [r for r in recipes if query.casefold() in r["title"].casefold()
                or any(query.casefold() in i["ingredient_id"].casefold() for i in r["ingredients"])]
    st.caption(f"Найдено рецептов: {len(matching)}. Названия и состав — на языке исходного каталога.")
    if matching:
        rid = st.selectbox("Рецепт", [r["recipe_id"] for r in matching], key="browse_recipe",
                           format_func=lambda iid: recipes_by_id[iid]["title"])
        recipe = recipes_by_id[rid]
        st.write(f"{recipe['cook_minutes']} минут · исходный рецепт на {recipe['servings']} порций")
        for ingredient in recipe["ingredients"]:
            name = ingredients[ingredient["ingredient_id"]]["canonical_name"]
            st.write(f"• {name}: {ingredient['quantity']:g} {unit_labels[ingredient['unit']]}")
        st.caption("Пошаговые инструкции приготовления в подготовленном датасете отсутствуют.")
if "pantry_items" not in st.session_state:
    st.session_state.pantry_items = {}

st.subheader("Что есть дома")
st.caption("Найдите продукт по названию и укажите запас. Названия пока приведены на языке каталога — английском.")
selected = st.selectbox(
    "Продукт", sorted(ingredients, key=lambda iid: ingredients[iid]["canonical_name"]),
    index=None, placeholder="Начните вводить название продукта…", key="pantry_product",
    format_func=lambda iid: ingredients[iid]["canonical_name"],
)
unit = ingredients[selected]["base_unit"] if selected else None
with st.form("add_pantry", clear_on_submit=True):
    quantity = st.number_input(
        f"Количество{', ' + unit_labels[unit] if unit else ''}",
        min_value=0.0, value=1.0, step=1.0, key="pantry_quantity",
    )
    if selected:
        st.caption(f"Единица из каталога: {unit_labels[unit]}. Повторное добавление увеличит запас.")
    add = st.form_submit_button("Добавить в запасы", disabled=selected is None, key="add_pantry")
if add and selected:
    if quantity <= 0:
        st.error("Укажите количество больше нуля.")
    else:
        st.session_state.pantry_items[selected] = st.session_state.pantry_items.get(selected, 0.0) + quantity
        st.session_state.pop("foodcom_result", None)

if st.session_state.pantry_items:
    for iid, amount in list(st.session_state.pantry_items.items()):
        name_col, amount_col, remove_col = st.columns([3, 2, 1])
        name_col.write(ingredients[iid]["canonical_name"])
        amount_col.write(f"{amount:g} {unit_labels[ingredients[iid]['base_unit']]}")
        if remove_col.button("Удалить", key=f"remove_{iid}"):
            del st.session_state.pantry_items[iid]
            st.session_state.pop("foodcom_result", None)
            st.rerun()
    if st.button("Очистить запасы", key="clear_pantry"):
        st.session_state.pantry_items = {}
        st.session_state.pop("foodcom_result", None)
        st.rerun()
else:
    st.info("Запасы не добавлены — все ингредиенты войдут в список покупок.")

st.subheader("Параметры меню")
with st.form("request"):
    budget = st.number_input("Бюджет, CU", min_value=0.0, value=25.0, key="budget")
    days = st.slider("Дни", 1, 7, 3)
    people = st.number_input("Количество людей", min_value=1, value=2, step=1)
    max_cook = st.number_input("Время приготовления, минут", min_value=1, value=30)
    submit = st.form_submit_button("Составить меню", key="plan_menu")
if submit:
    st.session_state.pop("foodcom_result", None)
    try:
        pantry = [{"ingredient_id": iid, "quantity": amount,
                   "unit": ingredients[iid]["base_unit"]}
                  for iid, amount in st.session_state.pantry_items.items()]
        request = {"pantry": pantry, "budget": budget, "currency": "CU",
                   "days": days, "people": people, "diet": ["vegetarian"],
                   "max_cook_minutes": max_cook}
        with st.spinner("Планирование и проверка…"):
            st.session_state.foodcom_result = run_foodcom_workflow(request)
    except Exception:
        st.error("Не удалось завершить расчёт. Проверьте формат запроса, доступность данных и настройки API.")
if "foodcom_result" in st.session_state:
    result = st.session_state.foodcom_result
    assessment = result["assessment"]
    st.subheader("Работа критика")
    for entry in result.get("agent_trace", []):
        feedback = entry["assessment"].get("feedback", "")
        label = f"Попытка {entry['attempt']}: "
        if "Critic [LLM," in feedback:
            st.info(label + "получен и проверен ответ настоящей модели.")
        elif "Critic [mock]" in feedback:
            st.info(label + "сработала заглушка, запроса к модели не было.")
        elif "Critic unavailable" in feedback:
            st.warning(label + "ответ критика не получен или не прошёл проверку. Проверьте доступ к API и лимиты.")
        else:
            st.caption(label + "критик не вызывался.")
        if "Critic [LLM," in feedback:
            st.text(feedback)
    if not result.get("agent_trace"):
        st.caption("Критик не вызывался: меню не было сформировано.")
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
        st.dataframe([{"День": m["day"], "Приём пищи": {"lunch": "Обед", "dinner": "Ужин"}.get(m["slot"], m["slot"]),
                       "Блюдо": recipes_by_id.get(m["recipe_id"], {}).get("title", m["recipe_id"]),
                       "Порций": m["servings"]} for m in result["plan"]["meals"]], hide_index=True)
    if assessment["shopping_list"]:
        st.dataframe(assessment["shopping_list"], hide_index=True)
    if assessment["feedback"]:
        st.text(assessment["feedback"])
    with st.expander("Попытки планирования и полный результат"):
        st.json(result)
