"""Source-audited overlays. Never modify imports or infer unknown food facts."""
from __future__ import annotations

import gzip
import hashlib
import html
import json
import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from smart_grocery.schemas.foodcom import Ingredient, Recipe

ROOT = Path(__file__).resolve().parents[3]
REVIEWED_DIR = ROOT / "data/reviewed/medlineplus"
NUMBER = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
# US customary volumes; these are not ingredient densities or nutrition-label cups.
UNITS = {
    "cup": ("ml", "236.5882365"), "cups": ("ml", "236.5882365"),
    "tablespoon": ("ml", "14.78676478125"), "tablespoons": ("ml", "14.78676478125"),
    "tbsp": ("ml", "14.78676478125"),
    "teaspoon": ("ml", "4.92892159375"), "teaspoons": ("ml", "4.92892159375"),
    "tsp": ("ml", "4.92892159375"),
    "quart": ("ml", "946.352946"), "quarts": ("ml", "946.352946"),
    "pound": ("g", "453.59237"), "pounds": ("g", "453.59237"), "lb": ("g", "453.59237"),
    "ounce": ("g", "28.349523125"), "ounces": ("g", "28.349523125"), "oz": ("g", "28.349523125"),
}


def _number(text: str) -> Decimal:
    result = Decimal(0)
    for part in text.split():
        if "/" in part:
            a, b = part.split("/")
            result += Decimal(a) / Decimal(b)
        else:
            result += Decimal(part)
    return result


def source_measurement(text: str) -> tuple[Decimal, str]:
    """Verify the frozen explicit choice, not arbitrary unreviewed recipe text."""
    text = text.replace("⁄", "/").replace(" and ", " ").replace("*", "").strip()
    if re.search(r"\b(?:dash|pinch|taste|needed|approximately|about)\b", text, re.I):
        # Approximate descriptions after a precise first amount are merely annotations.
        text = re.split(r"\s*\(", text, maxsplit=1)[0]
        if re.search(r"\b(?:dash|pinch|taste|needed|approximately|about)\b", text, re.I):
            raise ValueError("Unspecified or approximate measure")
    match = re.match(f"({NUMBER})\\s*([a-zA-Z]+)?", text)
    if match is None:
        raise ValueError("No explicit source quantity")
    quantity = _number(match[1])
    name = (match[2] or "").lower()
    package = re.match(f"({NUMBER})\\s+(?:cans?|packages?|cartons?)\\s*\\(({NUMBER})\\s*(?:ounces?|oz)(?:\\s+each)?\\)", text, re.I)
    if package:
        return quantity * _number(package[2]) * Decimal("28.349523125"), "g"
    equivalent = re.search(f"\\(({NUMBER})\\s*(?:ounces?|oz)\\)", text, re.I)
    if equivalent and (name in {"package", "packages", "carton", "cartons"}
                       or name in UNITS and UNITS[name][0] == "ml"):
        return _number(equivalent[1]) * Decimal("28.349523125"), "g"
    if name in UNITS:
        unit, factor = UNITS[name]
        return quantity * Decimal(factor), unit
    # Only counts with an explicitly reviewed piece definition are allowed below.
    if name in {"package", "packages", "can", "cans", "dash", "pinch"}:
        raise ValueError("Unverified package size or kitchen measure")
    return quantity, "pcs"


def load_reviewed_records(directory: Path = REVIEWED_DIR) -> list[dict]:
    """Fail closed if a source, audit or quantity no longer matches the overlay."""
    with gzip.open(directory / "sources.jsonl.gz", "rt", encoding="utf-8") as source_file:
        sources = {row["url"]: row for row in map(json.loads, source_file)}
    rows = [json.loads(line) for line in (directory / "corrections.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    seen = set()
    for row in rows:
        if row["recipe_id"] in seen:
            raise ValueError("Duplicate reviewed recipe")
        seen.add(row["recipe_id"])
        source = sources[row["source"]]
        digest = hashlib.sha256(source["html"].encode()).hexdigest()
        instruction_digest = hashlib.sha256(json.dumps(source["instructions"], ensure_ascii=False).encode()).hexdigest()
        # Re-extract every ingredient section from the actual pinned HTML. In
        # particular, secondary lists (marinades/toppings) may not be skipped.
        section = re.search(r'<h3>Ingredients</h3>(.*?)<h3>Directions</h3>', source["html"], re.S)
        def clean(text):
            return ' '.join(html.unescape(re.sub('<[^>]+>', ' ', text)).split())
        extracted = [clean(text) for text in re.findall(r'<li[^>]*>(.*?)</li>', section[1], re.S)] if section else []
        if extracted != source["ingredients"]:
            raise ValueError("Extracted source ingredients disagree with pinned HTML")
        review = row["review"]
        if (row["source_sha256"] != digest or source["sha256"] != digest
                or review["audited_instructions_sha256"] != instruction_digest
                or review["status"] != "source_audited"
                or review["ingredient_step_audit"] != "checked_against_pinned_ingredient_lists_and_all_instructions"
                or review["audited_russian_instructions_sha256"] != hashlib.sha256(json.dumps(row["instructions_ru"], ensure_ascii=False).encode()).hexdigest()
                or review["unresolved_required_ingredients"] or not all(review["checks"].values())):
            raise ValueError("Source/audit mismatch or unresolved required ingredient")
        if row["allergens_status"] != "unknown" or row["allergens"] is not None:
            raise ValueError("This source audit cannot certify allergen safety")
        covered = set()
        for ingredient in row["ingredients"]:
            amount, unit = source_measurement(ingredient["selected_text"])
            if amount <= 0 or amount != Decimal(ingredient["quantity"]) or unit != ingredient["unit"]:
                raise ValueError("Quantity disagrees with its explicit source evidence")
            if ingredient["ingredient_id"] in {"chicken_broth", "vegetable_broth", "milk", "evaporated_milk"} and unit == "g":
                raise ValueError("Ambiguous liquid ounce: need explicit volume or verified mass")
            line = ingredient.get("source_line")
            if line is not None:
                if source["ingredients"][line] != ingredient["source_text"]:
                    raise ValueError("Source ingredient changed")
                covered.add(line)
            elif source["instructions"][ingredient["source_step"]] != ingredient["source_text"]:
                raise ValueError("Instruction ingredient changed")
            if unit == "pcs" and not ingredient.get("count_definition"):
                raise ValueError("Piece count without a piece definition")
        omitted = {int(change["field"].split("/")[1]) for change in review["changes"]
                   if change["kind"] == "optional_omission" and change["field"].startswith("ingredients/")}
        if covered | omitted != set(range(len(source["ingredients"]))):
            raise ValueError("A source ingredient was silently dropped")
        times = row["timing"]
        if times["total_upper_bound_minutes"] < times["source_total_minutes"][1]:
            raise ValueError("Planning limit understates source duration")
    return rows


def reviewed_planning_recipes(directory: Path = REVIEWED_DIR) -> list[Recipe]:
    recipes = []
    for row in load_reviewed_records(directory):
        amounts = defaultdict(Decimal)
        for item in row["ingredients"]:
            amounts[item["ingredient_id"], item["unit"]] += Decimal(item["quantity"])
        recipes.append(Recipe(
            recipe_id=row["recipe_id"], title=row["title"], servings=row["servings"],
            cook_minutes=row["timing"]["total_upper_bound_minutes"], tags=row["tags"],
            ingredients=[Ingredient(ingredient_id=key, quantity=amount, unit=unit)
                         for (key, unit), amount in sorted(amounts.items())],
            instructions=row["instructions_ru"], meal_type=row["dish_type"], meal_slots=row["meal_slots"],
            source=row["source"], allergens_status="unknown", allergens=None,
        ))
    return recipes


def scale_recipe(recipe: Recipe, people: int) -> list[Ingredient]:
    """Scale food amounts, not duration, purchase packages or assumed densities."""
    if isinstance(people, bool) or not isinstance(people, int) or people < 1:
        raise ValueError("people must be a positive integer")
    return [item.model_copy(update={"quantity": item.quantity * people / recipe.servings})
            for item in recipe.ingredients]
