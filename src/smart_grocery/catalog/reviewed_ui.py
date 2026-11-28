"""Inspectable, source-audited recipes with quantities for a chosen household."""
import streamlit as st

from smart_grocery.catalog.reviewed import load_reviewed_records, reviewed_planning_recipes, scale_recipe

NAMES = {
    "banana": "Банан", "oat_cereal": "Овсяные хлопья для завтрака", "vanilla_yogurt": "Ванильный йогурт",
    "asparagus": "Спаржа", "squash_blossom": "Цветок кабачка", "serrano_pepper": "Перец серрано", "epazote_leaf": "Лист эпазота",
    "rolled_oats": "Овсяные хлопья", "steel_cut_oats": "Дробленый овес", "baking_powder": "Разрыхлитель",
    "cinnamon": "Корица", "salt": "Соль", "egg": "Яйцо", "brown_sugar": "Коричневый сахар",
    "sugar": "Сахар", "vanilla_extract": "Ванильный экстракт", "milk": "Молоко",
    "butter": "Сливочное масло", "raspberry": "Малина", "ground_beef": "Говяжий фарш",
    "ground_ginger": "Молотый имбирь", "garlic_powder": "Чесночный порошок", "soy_sauce": "Соевый соус",
    "cornstarch": "Кукурузный крахмал", "sesame_oil": "Кунжутное масло", "red_pepper_flakes": "Хлопья красного перца",
    "water": "Вода", "broccoli": "Брокколи", "cooked_bulgur": "Готовый булгур", "strawberry": "Клубника",
    "granola": "Гранола", "blueberry": "Черника", "plain_yogurt": "Натуральный йогурт",
    "onion": "Репчатый лук", "celery": "Сельдерей", "vegetable_oil": "Растительное масло",
    "potato": "Картофель", "vegetable_broth": "Овощной бульон", "black_pepper": "Черный перец",
    "cheddar": "Чеддер", "cooked_bacon_bits": "Готовый бекон кусочками", "canned_black_beans": "Черная фасоль в банке",
    "green_onion": "Зеленый лук", "lemon_juice": "Лимонный сок", "ground_cumin": "Молотый кумин",
    "chicken_breast": "Куриная грудка", "chili_powder": "Порошок чили", "wheat_tortilla": "Пшеничная тортилья",
    "chicken_pieces": "Куски курицы: ножки и грудка", "tomato": "Помидоры", "green_bell_pepper": "Зеленый сладкий перец",
    "red_bell_pepper": "Красный сладкий перец", "bell_pepper": "Сладкий перец", "carrot": "Морковь", "corn": "Кукуруза",
    "cilantro": "Кинза", "garlic": "Чеснок: зубчики при счете в штуках", "dry_rice": "Сырой рис",
    "peas": "Зеленый горошек", "black_olive": "Маслины без косточек", "raisin": "Изюм",
    "chicken_breast_half": "Половинка куриной грудки", "cabbage": "Капуста", "canned_diced_tomato": "Резаные томаты в банке",
    "chili_sauce": "Соус чили", "dried_basil": "Сушеный базилик", "dried_parsley": "Сушеная петрушка",
    "cayenne_pepper": "Кайенский перец", "whole_chicken": "Целая курица, размер по источнику",
    "dried_oregano": "Сушеный орегано", "cocoa_powder": "Какао-порошок", "all_purpose_flour": "Пшеничная мука",
    "peanut_butter": "Арахисовая паста", "canned_navy_beans": "Белая фасоль в банке", "chicken_broth": "Куриный бульон",
    "tomato_sauce": "Томатный соус", "canned_green_chiles": "Консервированный зеленый чили", "cooked_chicken": "Готовая курица",
    "corn_tortilla": "Кукурузная тортилья", "leek": "Лук-порей", "mushroom": "Грибы", "margarine": "Маргарин",
    "curry_powder": "Порошок карри", "pumpkin_puree": "Готовое тыквенное пюре", "evaporated_milk": "Концентрированное молоко без сахара",
    "honey": "Мед", "nutmeg": "Мускатный орех", "frozen_spinach": "Замороженный шпинат", "cod": "Треска",
    "cajun_seasoning": "Смесь специй каджун", "canned_peas": "Горошек в банке", "vegetable_bouillon": "Овощной бульонный концентрат",
    "onion_powder": "Луковый порошок", "salad_greens": "Салатная зелень", "cucumber": "Огурец",
    "salad_dressing": "Салатная заправка", "feta": "Фета", "creamed_corn": "Консервированная кремовая кукуруза",
    "cooked_ham": "Готовая ветчина", "dry_lentil": "Сухая чечевица", "turmeric": "Куркума", "dry_orzo": "Сухая паста орзо",
    "cooked_white_beans": "Готовая белая фасоль", "italian_herbs": "Итальянские травы", "kale": "Кейл",
    "fresh_oregano": "Свежий орегано", "dry_macaroni": "Сухие макароны", "canned_kidney_beans": "Красная фасоль в банке",
    "zucchini": "Кабачок", "dry_bulgur": "Сухой булгур", "spinach": "Свежий шпинат", "dry_penne": "Сухая паста пенне",
    "parmesan": "Пармезан", "dried_rosemary": "Сушеный розмарин", "dry_spaghetti": "Сухие спагетти", "apple": "Яблоко",
    "dry_whole_wheat_spaghetti": "Цельнозерновые сухие спагетти", "olive_oil": "Оливковое масло", "fresh_basil": "Свежий базилик",
    "mozzarella": "Моцарелла", "canned_pineapple": "Ананас в банке, сок сохранить", "vinegar": "Уксус",
    "orange_juice": "Апельсиновый сок", "red_chile_sauce": "Соус из красного чили", "canned_hominy": "Консервированная кукуруза хомини",
    "paprika": "Паприка", "tomato_pasta_sauce": "Томатный соус для пасты", "fresh_parsley": "Свежая петрушка",
    "cottage_cheese": "Зерненый творог", "dry_lasagna_sheet": "Сухие листы лазаньи", "cooked_black_beans": "Готовая черная фасоль",
    "cooked_brown_rice": "Готовый бурый рис", "salsa": "Сальса", "kielbasa": "Колбаса кильбаса", "jalapeno": "Халапеньо",
    "chicken_boneless": "Курица без костей", "corn_oil": "Кукурузное масло", "lean_pork": "Нежирная свинина",
    "cooked_mung_beans": "Готовый маш", "shrimp": "Очищенные креветки", "mustard_powder": "Горчичный порошок",
    "firm_tofu": "Плотный тофу", "ground_turkey": "Фарш индейки", "hot_sauce": "Острый соус", "fresh_ginger": "Свежий имбирь",
    "canned_water_chestnut": "Водяной каштан в банке", "lettuce_leaf": "Лист салата",
    "canned_great_northern_beans": "Белая фасоль Great Northern в банке", "canned_crushed_tomato": "Измельченные томаты в банке",
    "taco_seasoning": "Приправа для тако", "canned_green_beans": "Стручковая фасоль в банке", "beef_bouillon": "Говяжий бульонный концентрат",
    "canned_pinto_beans": "Фасоль пинто в банке", "canned_stewed_tomato": "Тушеные томаты в банке", "avocado": "Авокадо",
    "nutritional_yeast": "Пищевые дрожжи", "tomato_paste": "Томатная паста", "canned_white_beans": "Белая фасоль в банке",
    "sour_cream": "Сметана", "roasted_red_pepper": "Готовый печеный красный перец", "canned_tuna": "Тунец в банке",
    "mayonnaise": "Майонез", "whole_wheat_english_muffin": "Цельнозерновая булочка для сэндвича",
}
SLOTS = {"breakfast": "Завтрак", "lunch": "Обед", "dinner": "Ужин"}
UNITS = {"g": "г", "ml": "мл", "pcs": "шт."}
DISHES = {"main": "Основное блюдо", "soup": "Суп", "salad": "Салат", "breakfast": "Завтрак"}


def _range(value):
    if value is None:
        return "не выделено в источнике"
    return str(value[0]) if value[0] == value[1] else f"{value[0]}–{value[1]}"


def render_reviewed_catalog():
    records = load_reviewed_records()
    recipes = {r.recipe_id: r for r in reviewed_planning_recipes()}
    st.subheader("50 рецептов с проверенными данными")
    st.caption("Проверка по источнику · без пробного приготовления. Аллергенный состав не подтвержден.")
    query = st.text_input("Название блюда", key="reviewed_search").casefold()
    meal = st.selectbox("Прием пищи", ["Все", *SLOTS.values()], key="reviewed_meal")
    options = [row for row in records if query in row["title"].casefold()
               and (meal == "Все" or any(SLOTS[slot] == meal for slot in row["meal_slots"]))]
    if not options:
        st.info("Нет подходящих блюд.")
        return
    by_id = {r["recipe_id"]: r for r in options}
    selected = st.selectbox("Рецепт", list(by_id), format_func=lambda key: by_id[key]["title"], key="reviewed_recipe")
    row, recipe = by_id[selected], recipes[selected]
    people = st.number_input("Порций", min_value=1, max_value=100, value=int(recipe.servings), key=f"reviewed_people_{selected}")
    st.caption(f"{DISHES[row['dish_type']]} · в источнике {recipe.servings:g} порций · для лимита времени: {recipe.cook_minutes} мин")
    times = row["timing"]
    st.write(f"Подготовка: {_range(times['prep_minutes'])} мин · Приготовление: {_range(times['cook_minutes'])} · Ожидание: {_range(times['wait_minutes'])}")
    st.caption("Время относится к исходному объему. Большая партия может потребовать больше времени и другую посуду.")
    st.dataframe([
        {"Продукт": NAMES[item.ingredient_id], "Количество": f"{item.quantity:.3f}".rstrip("0").rstrip("."), "Единица": UNITS[item.unit]}
        for item in scale_recipe(recipe, people)
    ], hide_index=True)
    st.caption("Миллилитры сухих продуктов обозначают объем. В граммы он не переводится без данных о плотности. Вес банок — до слива жидкости; если источник дает объем продукта после обработки, сохраняется этот объем.")
    if row["review"]["prepared_ingredients"]:
        st.info("Нужны уже подготовленные продукты: " + ", ".join(NAMES[i] for i in sorted(set(row["review"]["prepared_ingredients"]))))
    if any(item.unit == "pcs" for item in recipe.ingredients):
        with st.expander("Что считается одной штукой"):
            for item in row["ingredients"]:
                if item["unit"] == "pcs":
                    st.write(f"{NAMES[item['ingredient_id']]}: {item['count_definition']}")
            st.caption("Доли яйца или овоща — расчетная потребность. Количество покупаемых упаковок округляется отдельно.")
    st.markdown("#### Приготовление по источнику")
    st.caption("Шаги изложены по-русски для выбранного варианта. Количества берите из списка на нужное число порций; температура и время относятся к исходной партии.")
    for step, text in enumerate(recipe.instructions or [], 1):
        st.write(f"{step}. {text}")
    st.warning("При любой активной аллергии рецепт не допускается в планирование: маркировка продуктов и перекрестный контакт не проверены.")
    st.link_button("Источник: MedlinePlus", row["source"])
    with st.expander("Основания проверки и изменения"):
        st.json({"timing": row["timing"], "potential_allergens": row["potential_allergens"], "review": row["review"]})
