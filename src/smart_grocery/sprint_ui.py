"""Streamlit controls for the offline integration demo."""
import os

import streamlit as st
from pydantic import ValidationError
from openai import OpenAIError

from smart_grocery.schemas.integration import UserProfile
from smart_grocery.workflow.golden import load_golden_case
from smart_grocery.workflow.integration import run_integration_workflow


UNITS = {"g": "г", "ml": "мл", "pcs": "шт."}
VIOLATIONS = {
    "no_candidates": "По этому профилю нет подходящих рецептов с нужными данными о составе.",
    "no_compatible_offer": "Для части продуктов нет подходящего предложения.",
    "provider_unavailable": "Поиск некоторых товаров недоступен.",
    "over_budget": "Оцененная стоимость превышает бюджет.",
    "unit_mismatch": "Для части продуктов единицы рецепта и запасов различаются.",
}


def _values(text: str) -> list[str]:
    return [item.strip().casefold() for item in text.split(",") if item.strip()]


def render_integration_demo() -> None:
    case, provider = load_golden_case()
    profile = case.profile
    st.caption("Учебный сценарий. Рецепты, сведения о составе и цены заданы в тестовых данных.")
    st.subheader("Профиль и запасы")
    recipe_source = st.selectbox("Рецепты", ["Тестовый набор", "Каталог источников"], key="sprint_recipe_source")
    store_source = st.selectbox("Цены", ["Тестовый магазин", "ВкусВилл: сохраненный снимок", "ВкусВилл: свежий запрос"], key="sprint_store_source")
    if recipe_source == "Каталог источников":
        from smart_grocery.catalog.loader import planning_recipes
        case.recipes = planning_recipes()
        st.caption("В подбор попадают только записи без структурных блокеров. При аллергиях неподтвержденный состав исключается.")
    llm_available = os.getenv("MOCK_LLM", "true").lower() == "false" and bool(os.getenv("LLM_API_KEY")) and bool(os.getenv("LLM_MODEL"))
    use_llm = st.checkbox("Планирование через настроенную модель", value=False, disabled=not llm_available, key="sprint_use_llm")
    st.caption(f"Планировщик: {os.getenv('LLM_MODEL')}" if use_llm else "Планировщик: автономный алгоритм")
    profile_col, inventory_col = st.columns(2)
    with inventory_col:
        st.write("Запасы для сценария")
        for item in case.inventory:
            st.write(f"{item.display_name} · {item.quantity:g} {UNITS[item.unit]}")
    with profile_col, st.form("sprint_profile"):
        days = st.slider("Дни", 1, 7, case.days, key="sprint_days")
        people = st.number_input("Люди", min_value=1, value=profile.household_size, key="sprint_people")
        budget = st.number_input("Бюджет, ₽", min_value=0.0, value=float(profile.budget), key="sprint_budget")
        minutes = st.number_input("Время приготовления, минут", min_value=1, value=profile.max_cooking_time)
        allergies = st.text_input("Аллергены", ", ".join(profile.allergies))
        excluded = st.text_input("Исключить ингредиенты", ", ".join(profile.disliked_ingredients))
        with st.expander("Предпочтения и диета"):
            cuisines = st.text_input("Кухни", ", ".join(profile.preferred_cuisines))
            goals = st.text_input("Цели питания", ", ".join(profile.goals))
            diet = st.text_input("Требуемые теги диеты", ", ".join(profile.dietary_pattern))
        st.caption("Указывайте идентификаторы через запятую, например peanut, cilantro, high_protein.")
        submit = st.form_submit_button("Рассчитать меню и покупки", type="primary", key="sprint_submit")

    if submit:
        st.session_state.pop("sprint_result", None)
        try:
            submitted_profile = UserProfile.model_validate({
                **profile.model_dump(),
                "household_size": people,
                "budget": budget,
                "max_cooking_time": minutes,
                "allergies": _values(allergies),
                "disliked_ingredients": _values(excluded),
                "preferred_cuisines": _values(cuisines),
                "goals": _values(goals),
                "dietary_pattern": _values(diet),
            })
        except ValidationError:
            st.error("Проверьте параметры профиля. Для аллергенов и исключений используйте идентификаторы вроде peanut.")
        else:
            live_provider = None
            if store_source == "ВкусВилл: сохраненный снимок":
                from smart_grocery.retail.snapshot import snapshot_provider
                provider = snapshot_provider()
            elif store_source == "ВкусВилл: свежий запрос":
                from smart_grocery.retail.mcp import MCPClient
                from smart_grocery.retail.vkusvill import VkusVillProvider
                live_provider = VkusVillProvider(MCPClient(token=os.getenv("VKUSVILL_ACCESS_TOKEN")))
                provider = live_provider
            try:
                with st.spinner("Составляем меню и рассчитываем покупки…"):
                    st.session_state.sprint_result = run_integration_workflow(
                        submitted_profile, case.inventory, case.recipes, provider, days=days,
                        mock_planner=not use_llm,
                    )
                st.session_state.sprint_titles = {recipe.recipe_id: recipe for recipe in case.recipes}
            except OpenAIError:
                st.error("Модель сейчас недоступна. Проверьте локальные настройки или выберите автономный планировщик.")
            finally:
                if live_provider is not None:
                    live_provider.close()

    signature = (recipe_source, store_source, use_llm)
    if submit:
        st.session_state.sprint_sources = signature
    elif st.session_state.get("sprint_sources") != signature:
        st.session_state.pop("sprint_result", None)
    result = st.session_state.get("sprint_result")
    if result is None:
        return
    if result.recommendations:
        with st.expander("Рекомендации критика"):
            for recommendation in result.recommendations:
                st.write(recommendation)
    for issue in result.violations:
        st.warning(VIOLATIONS.get(issue.code, issue.message))
    if result.plan is None or result.shopping_list is None:
        return

    result_recipes = st.session_state.get("sprint_titles", {})
    titles = {key: recipe.title for key, recipe in result_recipes.items()}
    st.subheader("Меню")
    st.dataframe([
        {"День": meal.day, "Прием пищи": "Обед" if meal.slot == "lunch" else "Ужин",
         "Блюдо": titles[meal.recipe_id], "Порций": int(meal.servings)}
        for meal in result.plan.meals
    ], hide_index=True)

    with st.expander("Рецепты выбранных блюд"):
        for recipe_id in dict.fromkeys(meal.recipe_id for meal in result.plan.meals):
            recipe = result_recipes.get(recipe_id)
            if recipe is None:
                continue
            st.markdown(f"**{recipe.title}**")
            if recipe.instructions:
                for number, instruction in enumerate(recipe.instructions, 1):
                    st.write(f"{number}. {instruction}")
            else:
                st.caption("Инструкции отсутствуют в этом наборе.")
            if recipe.source:
                st.link_button("Источник рецепта", recipe.source)

    st.subheader("Покупки")
    shopping = result.shopping_list
    partial = shopping.estimated_total is None
    amount = shopping.priced_subtotal if partial else shopping.estimated_total
    st.metric("Частичный итог" if partial else "Итого по тестовым ценам", f"{amount:.2f} ₽")
    names = {item.ingredient_id: item.display_name for item in case.inventory}
    names["olive_oil"] = "Оливковое масло"
    if shopping.lines:
        st.dataframe([
            {
                "Ингредиент": names.get(line.ingredient_id, line.ingredient_id),
                "Нужно": f"{line.required_quantity:g} {UNITS[line.unit]}",
                "Дома": f"{line.inventory_quantity:g} {UNITS[line.unit]}",
                "Докупить": f"{line.missing_quantity:g} {UNITS[line.unit]}",
                "Товар": line.selected_offer.title if line.selected_offer else None,
                "Упаковок": line.package_count,
                "Сумма, ₽": float(line.estimated_total) if line.estimated_total is not None else None,
            }
            for line in shopping.lines
        ], hide_index=True)
    else:
        st.caption("Список покупок пуст.")
