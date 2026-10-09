import os
from pydantic import BaseModel
from smart_grocery.schemas.models import PlanningRequest, Recipe

class MenuIds(BaseModel):
    recipe_ids: list[str]

def propose_menu(request: PlanningRequest, recipes: list[Recipe], feedback: list[str] | None = None) -> list[str]:
    if os.getenv("MOCK_LLM", "true").lower() == "true":
        return [r.id for r in recipes[:request.days]]
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ.get("LLM_BASE_URL") or None)
    available = [{"id": r.id, "name": r.name, "ingredients": [i.model_dump() for i in r.ingredients], "tags": r.tags} for r in recipes]
    prompt = f"Choose exactly {request.days} recipe IDs from {available}. Constraints: {request.model_dump()}. Validator feedback: {feedback or []}. Respond ONLY as JSON with recipe_ids string array. Do not invent IDs."
    answer = client.chat.completions.create(model=os.environ["LLM_MODEL"], messages=[{"role":"system","content":"You plan meals using only provided recipe IDs; return strict JSON."},{"role":"user","content":prompt}], response_format={"type":"json_object"}, temperature=0)
    result = MenuIds.model_validate_json(answer.choices[0].message.content)
    return result.recipe_ids
