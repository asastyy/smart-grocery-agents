# CONTRACTS (заморожены 10.10)

## Recipe format (источник истины)

    {
      "recipe_id": "r001",
      "title": "Egg fried rice",
      "servings": 2,
      "cook_minutes": 20,
      "tags": ["vegetarian"],
      "ingredients": [
        {"ingredient_id": "rice", "quantity": 200, "unit": "g"},
        {"ingredient_id": "egg",  "quantity": 2,   "unit": "pcs"}
      ]
    }

Правила:
- ingredient_id — snake_case, только из data/ingredients.csv
- unit — только g | ml | pcs
- tags MVP: "vegetarian" (обяз.), "high_protein" (опц.)
- recipe_id стабильный: r001..rNNN, уникальный
- Цены в рецепте НЕ хранятся — только data/prices.csv
- Неизвестный ингредиент или единица → рецепт отбрасывается

## Слоты MVP
1 обед + 1 ужин в день (согласовано 10.10)

## Функции

- search_recipes(request) -> {"candidates": [recipe, ...]}
- plan_meals(request, candidates, feedback=None) -> {"meals": [...], "reasoning_summary": "..."}
- evaluate_plan(request, plan, catalog) -> {"valid": bool, "total_cost": float, "shopping_list": [...], "violations": [...], "feedback": "..."}
- run_workflow(request) -> {"plan": ..., "assessment": ..., "agent_trace": [...]}
