"""Only explicitly complete records cross into the existing Recipe contract."""
import json
from pathlib import Path

from smart_grocery.schemas.foodcom import Recipe

DEFAULT_CATALOG = Path(__file__).resolve().parents[3] / 'data/catalog/catalog.jsonl'


def load_catalog(path: Path = DEFAULT_CATALOG) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def planning_recipes(path: Path = DEFAULT_CATALOG) -> list[Recipe]:
    records = load_catalog(path)
    return [Recipe.model_validate(row) for row in records
            if row.get('quality', {}).get('planning_ready') is True
            and not row.get('quality', {}).get('issues')]
