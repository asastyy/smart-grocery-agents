import json
from smart_grocery.tools.budget_v2 import evaluate_plan  # Food.com public contract
from collections import defaultdict
from pathlib import Path
from smart_grocery.schemas.models import PlanningRequest, PlanningResult, Recipe, ShoppingLine

PRICES = Path(__file__).resolve().parents[3] / "examples" / "prices.json"

def evaluate_menu(request: PlanningRequest, recipes: list[Recipe], recipe_ids: list[str]) -> PlanningResult:
    by_id = {r.id: r for r in recipes}
    issues = []
    if len(recipe_ids) != request.days: issues.append("Recipe count does not match days")
    if any(rid not in by_id for rid in recipe_ids): issues.append("Unknown recipe ID")
    price = json.loads(PRICES.read_text(encoding="utf-8"))
    needed = defaultdict(float)
    for rid in recipe_ids:
        if rid not in by_id: continue
        r = by_id[rid]
        if request.diet in {"vegetarian", "vegan"} and request.diet not in r.tags:
            issues.append(f"Diet mismatch: {rid}")
        for ingredient in r.ingredients: needed[(ingredient.item, ingredient.unit)] += ingredient.qty
    pantry = {s.lower().strip() for s in request.pantry}
    shopping = []
    incomplete = False
    for (item,unit),qty in sorted(needed.items()):
        if unit != "portion":
            issues.append(f"Unsupported unit for {item}: {unit}; expected portion")
            incomplete = True
            continue
        if item in pantry: continue # MVP treats pantry items as unbounded; see CONTRACTS
        if item not in price:
            issues.append(f"Unknown price for {item}; missing quantity: {qty} {unit}")
            incomplete = True
            continue
        shopping.append(ShoppingLine(item=item, quantity=qty, unit=unit, unit_price=price[item], cost=round(qty*price[item],2)))
    total = round(sum(s.cost for s in shopping),2)
    if incomplete:
        issues.append("Shopping list and total_cost are incomplete; resolve missing prices or unsupported units before accepting this menu")
    if total > request.budget: issues.append(f"Budget exceeded: {total} > {request.budget}")
    return PlanningResult(recipe_ids=recipe_ids, shopping=shopping, total_cost=total, currency=request.currency, valid=not issues, issues=issues)
