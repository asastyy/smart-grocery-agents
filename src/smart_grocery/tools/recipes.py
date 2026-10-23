"""Роль 1: единый словарь ингредиентов + поиск рецептов по ограничениям.

Контракт: search_recipes(request) -> {"candidates": [recipe, ...]}
"""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "data"))
RECIPES_PATH = Path(os.getenv("RECIPES_PATH", DATA_DIR / "recipes.jsonl"))
PRICES_PATH = Path(os.getenv("PRICES_PATH", DATA_DIR / "prices.csv"))
INGREDIENTS_PATH = Path(os.getenv("INGREDIENTS_PATH", DATA_DIR / "ingredients.csv"))


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    raise TypeError(f"request must be Mapping or Pydantic model, got {type(value)!r}")


def _norm_key(text: str) -> str:
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_ingredients(path: Path | None = None) -> dict[str, dict[str, Any]]:
    path = Path(path or INGREDIENTS_PATH)
    with path.open(newline="", encoding="utf-8") as f:
        return {
            row["ingredient_id"]: {
                "canonical_name": row["canonical_name"],
                "base_unit": row["base_unit"],
                "category": row.get("category", ""),
            }
            for row in csv.DictReader(f)
        }


def load_prices(path: Path | None = None) -> dict[str, dict[str, Any]]:
    path = Path(path or PRICES_PATH)
    with path.open(newline="", encoding="utf-8") as f:
        return {
            row["ingredient_id"]: {
                "unit": row["unit"],
                "price_per_unit": float(row["price_per_unit"]),
                "currency": row["currency"],
            }
            for row in csv.DictReader(f)
        }


def load_recipes(path: Path | None = None) -> list[dict[str, Any]]:
    path = Path(path or RECIPES_PATH)
    recipes: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recipes.append(json.loads(line))
    return recipes


def search_recipes(
    request: Mapping[str, Any] | Any,
    recipes_path: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Фильтр по diet и max_cook_minutes, сортировка по покрытию pantry."""
    req = _as_dict(request)
    recipes = load_recipes(recipes_path)

    diet = req.get("diet") or []
    if isinstance(diet, str):
        diet = [diet]
    diet = [d.lower() for d in diet]

    max_cook = req.get("max_cook_minutes")
    max_cook = int(max_cook) if max_cook is not None else None

    pantry_ids = {
        str(item["ingredient_id"])
        for item in req.get("pantry", [])
        if isinstance(item, Mapping) and "ingredient_id" in item
    }

    ranked: list[tuple[int, int, int, str, dict[str, Any]]] = []
    for recipe in recipes:
        tags = {t.lower() for t in recipe.get("tags", [])}

        if diet and not all(d in tags for d in diet):
            continue
        if max_cook is not None and int(recipe["cook_minutes"]) > max_cook:
            continue

        ing_ids = {i["ingredient_id"] for i in recipe["ingredients"]}
        covered = len(ing_ids & pantry_ids)
        missing = len(ing_ids - pantry_ids)
        ranked.append((-covered, missing, int(recipe["cook_minutes"]), recipe["recipe_id"], recipe))

    ranked.sort(key=lambda x: x[:4])
    return {"candidates": [item[-1] for item in ranked]}
