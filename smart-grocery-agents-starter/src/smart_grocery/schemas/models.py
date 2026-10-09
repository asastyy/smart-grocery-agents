from pydantic import BaseModel, Field

class PlanningRequest(BaseModel):
    pantry: list[str]
    budget: float = Field(ge=0)
    days: int = Field(ge=1, le=7)
    servings: int = Field(ge=1, le=10)
    diet: str = "none"
    currency: str = "EUR"

class Ingredient(BaseModel):
    item: str
    qty: float = Field(gt=0)
    unit: str = "portion"

class Recipe(BaseModel):
    id: str
    name: str
    ingredients: list[Ingredient]
    tags: list[str] = []

class ShoppingLine(BaseModel):
    item: str
    quantity: float
    unit: str
    unit_price: float
    cost: float

class PlanningResult(BaseModel):
    recipe_ids: list[str]
    shopping: list[ShoppingLine]
    total_cost: float
    currency: str
    valid: bool
    issues: list[str]
