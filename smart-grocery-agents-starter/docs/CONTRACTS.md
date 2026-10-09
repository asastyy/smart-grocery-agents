# Frozen interface v0.1 — changes only by team agreement

Input: `PlanningRequest` {pantry: list[str], budget: float, days: int, servings: int, diet: str, currency: str}

Recipe: `Recipe` {id: str, name: str, ingredients: list[Ingredient], tags: list[str]}; Ingredient {item: str, qty: float, unit: str}; initial unit is `portion` for simpler MVP matching

Output: `PlanningResult` {recipe_ids: list[str], shopping: list[ShoppingLine], total_cost: float, currency: str, valid: bool, issues: list[str]}

Module APIs:
- `search_recipes(request: PlanningRequest) -> list[Recipe]`
- `propose_menu(request: PlanningRequest, recipes: list[Recipe], feedback: list[str] | None = None) -> list[str]`
- `evaluate_menu(request: PlanningRequest, recipes: list[Recipe], recipe_ids: list[str]) -> PlanningResult`
- `run_workflow(request: PlanningRequest) -> PlanningResult`

No module changes Pydantic types without PR review by all four contributors. Each module must have a unit test using `examples/request.json`.

Current approximation: the pantry is boolean availability and recipe quantities are in illustrative portions. Real unit conversion, depletion across meals and accurate servings scaling are final-defense scope. Do not claim that the cost is a real retail price.
