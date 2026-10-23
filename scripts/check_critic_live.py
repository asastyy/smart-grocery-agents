"""Opt-in, small live critic check; does not call the planner or print secrets."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv
from smart_grocery.tools.recipes import load_prices, search_recipes
from smart_grocery.tools.budget_v2 import evaluate_plan
from smart_grocery.agents.validator import validate_foodcom_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly allow an external critic API call")
    args = parser.parse_args()
    if not args.live:
        print("Use --live to permit an external API call. No call made.")
        return 2
    load_dotenv(ROOT / ".env")
    if not os.getenv("LLM_API_KEY") or not (os.getenv("CRITIC_MODEL") or os.getenv("LLM_MODEL")):
        print("Missing local LLM_API_KEY or model in .env. No call made.")
        return 2
    os.environ["MOCK_LLM"] = "false"
    request = {"pantry": [], "budget": 0, "currency": "CU", "days": 1,
               "people": 2, "diet": ["vegetarian"], "max_cook_minutes": 30}
    candidates = search_recipes(request)["candidates"][:3]
    plan = {"meals": [{"day": 1, "slot": slot, "recipe_id": candidates[0]["recipe_id"], "servings": 2}
                      for slot in ("lunch", "dinner")]}
    catalog = {"recipes": candidates, "prices": load_prices()}
    baseline = evaluate_plan(request, plan, catalog)
    result = validate_foodcom_plan(request, plan, catalog)
    unchanged = all(result[key] == baseline[key] for key in
                    ("valid", "total_cost", "shopping_list", "violations"))
    successful = "Critic [LLM," in result["feedback"]
    print(result["feedback"])
    print(f"Deterministic facts preserved: {unchanged}")
    print(f"Real critic response validated: {successful}")
    return 0 if unchanged and successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
