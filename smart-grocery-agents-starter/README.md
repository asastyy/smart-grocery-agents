# Smart Grocery Agents

Multi-agent meal planning and grocery optimization from a pantry, budget and dietary constraints.

## Team
| Role | Full name | GitHub |
|---|---|---|
| Data & Recipe Search | TODO | TODO |
| Meal Planner | TODO | TODO |
| Shopping & Validator | TODO | TODO |
| Orchestration & UI | TODO | TODO |

## MVP (proposal)
User enters pantry ingredients, budget, diet and number of days. The system retrieves recipes, proposes a menu, validates ingredients and computes a shopping list and cost. If validation fails, planner revises its proposal once.

The LLM is used for **planning and revising** a menu from retrieved recipe candidates, not inventing prices or performing arithmetic. The model is accessed via an OpenAI-compatible API (provider and model chosen using `LLM_BASE_URL` and `LLM_MODEL`). The default `MOCK_LLM=true` allows an offline runnable scaffold; **mock mode is not the LLM functionality required at proposal**.

## Current status
Starter scaffold with a working deterministic offline pipeline and tests. `planner.py` contains a model-backed planning mode; finish and verify its structured output and agent revision prior to proposal. This is not yet a complete multi-agent system.

## Local setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

## Docker
```bash
docker build -t smart-grocery .
docker run --rm -p 8501:8501 --env-file .env smart-grocery
```
Open http://localhost:8501

## Architecture and contracts
- `docs/CONTRACTS.md`: canonical input/output schemas; agree before editing code
- `src/smart_grocery/schemas/models.py`: shared Pydantic objects
- `src/smart_grocery/tools/recipes.py`: recipe lookup (Role 1)
- `src/smart_grocery/agents/planner.py`: LLM planner (Role 2)
- `src/smart_grocery/tools/budget.py` and `agents/validator.py`: shopping + rule checks (Role 3)
- `src/smart_grocery/workflow/runner.py`, `app.py`, Docker (Role 4)

`tools` return factual / computed information. `agents` decide on actions. Future LangGraph integration can replace the scaffold runner without changing schemas.

## Dataset plan
For proposal use a **curated 30–100 recipe subset** with normalized ingredient IDs, quantities and units plus a **clearly labeled synthetic price list**. Explore Food.com Recipes & Reviews (https://www.kaggle.com/datasets/irkaal/foodcom-recipes-and-reviews), USDA FoodData Central (https://fdc.nal.usda.gov/), and Open Prices (https://prices.openfoodfacts.org/). Review their licenses and attribution requirements before redistributing dataset rows. Price data in this scaffold is fictional, not live store pricing.

## Acceptance criteria
- Same JSON contracts used by all modules
- Run 3-day menu for sample input end-to-end
- No missing ingredients omitted from shopping list
- Total spend recomputed from price table, never LLM guesses
- Invalid recipes trigger revision/failure, with bounded retries
- Docker clean start; `.env.example`; all team members identified
- 3–5 documented scenarios, at least one failed-and-revised proposal

## Source
Course repository: https://github.com/AlgazinovAleksandr/LLM-Agents-Course
