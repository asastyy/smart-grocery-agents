# Role 1 — Data & Recipe Search

## Источник
Food.com Recipes and Reviews (Kaggle: irkaal/foodcom-recipes-and-reviews).
Используется только recipes.csv; отзывы не используются.
RecipeNLG — резерв. USDA / Open Prices — после MVP.

## Как построены данные
Скрипт scripts/build_from_foodcom.py:
1. Скачивает датасет через kagglehub (если data/raw/recipes.csv нет)
2. Сканирует vegetarian-рецепты с CookTime 10-30 мин и >=3 ингредиентами
3. Считает частоту ингредиентов, нормализует имена (lowercase, singular, без дескрипторов)
4. Определяет base_unit по доминирующей единице в датасете (g / ml / pcs)
5. Конвертирует объёмы и веса через таблицу плотностей
6. Отбрасывает рецепты, где хоть один ингредиент не удалось нормализовать или сконвертировать
7. Пишет data/{ingredients,recipes,prices}.csv|jsonl

## Файлы
| Файл | Назначение |
|---|---|
| data/raw/recipes.csv | сырой датасет, НЕ коммитится |
| data/ingredients.csv | единый словарь: id, canonical_name, aliases, base_unit |
| data/recipes.jsonl | 150 подготовленных рецептов из Food.com в текущем MVP |
| data/prices.csv | цены в CU (демо), unit == base_unit |
| scripts/build_from_foodcom.py | воспроизводимая очистка |
| fixtures/mock_candidates.json | мок для ролей 2 и 3 |

## Правила нормализации
- Фильтр: vegetarian в Keywords/RecipeCategory; CookTime в [10, 30] мин; >=3 ингредиента.
- Ингредиент: lowercase, singular, без дескрипторов (large/fresh/chopped/...), id = snake_case.
- Единицы: g, ml, pcs. kg/oz/lb -> g; l/cup/tbsp/tsp -> ml или g по плотности; clove/slice/piece/large -> pcs.
- Если единица не распознана или конвертация невозможна — рецепт отбрасывается.
- recipe_id = r001..rNNN, уникальный.

## Пересборка
    python scripts/build_from_foodcom.py --max-recipes 100 --max-ingredients 200

## Проверка
    python -m pytest tests/test_recipes.py -q
    python scripts/check_data.py

## Цены
Собственный статический каталог в CU (демо-цены), назначается по категории ингредиента.
Food.com цен не содержит. Open Prices — после MVP.
Отсутствие цены — unknown_price у роли 3, а не цена 0.
