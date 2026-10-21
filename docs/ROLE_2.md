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

The implementation uses the existing OpenAI-compatible client and does not
lock the project to one provider. The live integration was verified with Groq:

```dotenv
MOCK_LLM=false
LLM_API_KEY=YOUR_GROQ_API_KEY
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=qwen/qwen3.8-27b
```

Gemini through Google AI Studio:

```dotenv
MOCK_LLM=false
LLM_API_KEY=YOUR_GEMINI_API_KEY
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-3.8-flash
```

Qwen through DashScope / QwenCloud:

```dotenv
MOCK_LLM=false
LLM_API_KEY=YOUR_DASHSCOPE_API_KEY
LLM_BASE_URL=https://maas.qwencloudapi.com/compatible-mode/v1
LLM_MODEL=qwen3.8-max
```

Store the key only in a local `.env`; never commit it. Before the presentation,
the team must perform one real request with the chosen provider and model.
