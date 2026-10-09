# Two-week parallel plan — October 9–22, 2026

**Oct 9–10: all four in parallel**: choose owners; accept `CONTRACTS.md`; each creates a feature branch; Role 1 creates a 30–100 recipe sample; Role 2 tests 3 model-generated structured menus on fixture recipes; Role 3 builds budget/constraint tests; Role 4 builds Streamlit+Docker and offline wiring.

**Oct 11–13: individual module freeze**: Role 1 returns candidates through `search_recipes`; Role 2 gets validated `list[str]` from an actual LLM with retries; Role 3 returns shopping and violation reports; Role 4 runs UI with mocks. Each delivers PR + tests by Oct 13.

**Oct 14–15: integration**: merge in contract order, run actual LLM planning end-to-end, record tool outputs and failure cases. Oct 15 first live demo.

**Oct 16–18: quality**: fix ingredient aliases, enforce dietary constraints, incorporate validator feedback, test 5 fixtures, make budget errors visible. Oct 18 feature-complete MVP.

**Oct 19–20: submission hardening**: Docker cold boot, API key setup, review README, model/provider explanation, compare deterministic baseline vs LLM, presentation slides. Oct 20 freeze for proposal.

**Oct 21–22: buffer and rehearsal**: every participant presents >=1 slide, each explains their code and decisions, run live demo twice.

## Git workflow
- `main` protected by convention; one branch per module (`feature/recipes`, `feature/planner`, `feature/budget`, `feature/ui`)
- PRs include screenshot/log of working scenario, test output, schema changes and owner
- Data never committed at full source size; keys never committed
- A nightly smoke test uses sample JSON and MOCK_LLM=true
