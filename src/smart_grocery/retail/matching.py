"""Small, auditable dictionary for the sprint's six ingredients.

Fuzzy matches are suggestions only. A search hit is not evidence of equivalence.
"""
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape
import re

from smart_grocery.retail.models import MatchDecision


def clean_text(value: str) -> str:
    text = re.sub(r"<[^>]*>", " ", unescape(str(value)))
    return " ".join(text.casefold().replace("ё", "е").split())


@dataclass(frozen=True)
class IngredientSpec:
    ingredient_id: str
    query: str
    unit: str
    aliases: tuple[str, ...]
    blocked: tuple[str, ...] = ()


SPECS = {
    "rice": IngredientSpec("rice", "рис", "g", ("рис", "rice")),
    "egg": IngredientSpec("egg", "яйца", "pcs", ("яйцо куриное", "яйца куриные", "egg", "eggs"), ("перепел", "варен")),
    "chicken_breast": IngredientSpec("chicken_breast", "куриная грудка", "g", ("куриная грудка", "chicken breast"), ("на кости", "с костью", "без кожи на кости")),
    "milk": IngredientSpec("milk", "молоко", "ml", ("молоко", "milk"), ("кокос", "миндал", "овсян", "соев", "козье", "сухое", "сгущ")),
    "tomato": IngredientSpec("tomato", "помидоры", "g", ("томаты", "томат", "помидор", "помидоры", "tomato", "tomatoes")),
    "olive_oil": IngredientSpec("olive_oil", "масло оливковое", "ml", ("масло оливковое", "оливковое масло", "olive oil"), ("спрей", "смесь")),
}
PROCESSED = ("соус", "салат", "суп", "каша", "мука", "лапша", "напиток", "десерт", "котлет", "паниров", "копчен", "консерв", "маринован", "хлопья", "пюре")


def resolve_ingredient(value: str) -> str:
    if value in SPECS:
        return value
    normalized = clean_text(value)
    for key, spec in SPECS.items():
        if normalized in {clean_text(alias) for alias in (*spec.aliases, spec.query)}:
            return key
    raise ValueError("Ingredient is outside the reviewed retail dictionary")


def match_product(ingredient_id: str, title: str) -> MatchDecision:
    spec = SPECS[ingredient_id]
    name = clean_text(title)
    if any(word in name for word in (*PROCESSED, *spec.blocked)):
        return MatchDecision(status="rejected", method="rule", reason="Different ingredient or processed product")
    if ingredient_id == "chicken_breast":
        # Bone-in breast is not a boneless ingredient; do not infer edible yield.
        accepted = "филе" in name and "груд" in name and ("цып" in name or "кур" in name)
    else:
        accepted = False
    for alias in spec.aliases:
        pattern = r"(?<!\w)" + re.escape(clean_text(alias)) + r"(?!\w)"
        if re.search(pattern, name):
            if ingredient_id != "chicken_breast" or "филе" in name:
                return MatchDecision(status="accepted", method="exact" if name == clean_text(alias) else "alias", reason="Reviewed ingredient name")
    if accepted:
        return MatchDecision(status="accepted", method="alias", reason="Boneless breast fillet name")
    score = max(SequenceMatcher(None, name, clean_text(alias)).ratio() for alias in spec.aliases)
    if score >= 0.70:
        return MatchDecision(status="review", method="fuzzy", reason="Text similarity requires human confirmation")
    return MatchDecision(status="rejected", method="rule", reason="No reviewed name match")
