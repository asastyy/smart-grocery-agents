"""Load the reproducible sprint scenario shared by the CLI and Streamlit."""
from pathlib import Path

from pydantic import Field

from smart_grocery.schemas.foodcom import Model, Recipe
from smart_grocery.schemas.integration import UserProfile, InventoryItem
from smart_grocery.tools.grocery_provider import MockGroceryProvider


FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "integration"


class GoldenCase(Model):
    days: int = Field(ge=1, le=7)
    profile: UserProfile
    inventory: list[InventoryItem]
    recipes: list[Recipe]


def load_golden_case() -> tuple[GoldenCase, MockGroceryProvider]:
    case = GoldenCase.model_validate_json((FIXTURES / "golden_case.json").read_bytes())
    return case, MockGroceryProvider.from_file(FIXTURES / "mock_offers.json")
