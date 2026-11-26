# Role 2 Meal Planner

The planner has one provider-neutral core and two adapters while the team
resolves the shared data contract.

- `propose_menu(request, recipes, feedback=None) -> list[str]` is for the
  existing starter workflow and its `id` / `name` recipes.
- `plan_meals(request, candidates, feedback=None, slots=("dinner",)) -> dict`
  accepts the Food.com branch's `recipe_id` / `title` candidates and returns
  `{ "meals": [{"day", "slot", "recipe_id", "servings"}, ...],
  "reasoning_summary": "..." }`.

Both adapters validate that every LLM-selected ID is a supplied candidate,
limit the prompt to the first 20 ranked candidates, retry one malformed JSON
response, and use a deterministic candidate-only fallback after a second
invalid response. The LLM does not calculate prices or decide validity.

## Provider configuration

The implementation uses a provider-neutral Chat Completions client. Configure
the endpoint and model in the local `.env`:

```dotenv
MOCK_LLM=false
LLM_API_KEY=YOUR_LOCAL_API_KEY
LLM_BASE_URL=https://provider.example/v1
LLM_MODEL=provider-model-name
```

Store the key only in a local `.env`; never commit it. `MOCK_LLM=true` runs
the deterministic offline scenario without a network request.
