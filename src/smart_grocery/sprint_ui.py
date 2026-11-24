"""Streamlit controls for the offline integration demo."""
import streamlit as st
from pydantic import ValidationError

from smart_grocery.schemas.integration import UserProfile
from smart_grocery.workflow.golden import load_golden_case
from smart_grocery.workflow.integration import run_integration_workflow


UNITS = {"g": "г", "ml": "мл", "pcs": "шт."}
VIOLATIONS = {
    "no_candidates": "По этому профилю нет подходящих рецептов с нужными данными о составе.",
    "no_compatible_offer": "Для части продуктов нет подходящего предложения.",
    "provider_unavailable": "Поиск некоторых товаров недоступен.",
    "over_budget": "Оценённая стоимость превышает бюджет.",
    "unit_mismatch": "Для части продуктов единицы рецепта и запасов различаются.",
}


def _values(text: str) -> list[str]:
    return [item.strip().casefold() for item in text.split(",") if item.strip()]


def render_integration_demo() -> None:
    case, provider = load_golden_case()
    profile = case.profile
    st.caption("Учебный сценарий. Рецепты, сведения о составе и цены заданы в тестовых данных.")
    st.subheader("Профиль и запасы")
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
            st.session_state.sprint_result = run_integration_workflow(
                submitted_profile, case.inventory, case.recipes, provider, days=days, mock_planner=True,
            )

    result = st.session_state.get("sprint_result")
    if result is None:
        return
    for issue in result.violations:
        st.warning(VIOLATIONS.get(issue.code, issue.message))
    if result.plan is None or result.shopping_list is None:
        return

    titles = {recipe.recipe_id: recipe.title for recipe in case.recipes}
    st.subheader("Меню")
    st.dataframe([
        {"День": meal.day, "Приём пищи": "Обед" if meal.slot == "lunch" else "Ужин",
         "Блюдо": titles[meal.recipe_id], "Порций": int(meal.servings)}
        for meal in result.plan.meals
    ], hide_index=True)

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
