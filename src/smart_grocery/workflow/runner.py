"""Bounded orchestration; business rules stay in the team-owned modules."""
from dataclasses import dataclass, field
import os
from time import perf_counter
from typing import Callable

from smart_grocery.schemas.models import PlanningRequest, PlanningResult, Recipe
from smart_grocery.tools.legacy_recipes import search_recipes
from smart_grocery.agents.planner import propose_menu
from smart_grocery.agents.validator import validate_plan

@dataclass
class WorkflowRun:
    """UI envelope; does not change the frozen PlanningResult contract."""

    request: PlanningRequest
    result: PlanningResult | None = None
    candidates: list[Recipe] = field(default_factory=list)
    agent_trace: list[dict] = field(default_factory=list)
    error: str | None = None
    mode: str = "mock"

    def model_dump(self) -> dict:
        return {
            "request": self.request.model_dump(),
            "result": self.result.model_dump() if self.result else None,
            "agent_trace": self.agent_trace,
            "error": self.error,
            "mode": self.mode,
        }


def run_workflow_with_trace(request: PlanningRequest) -> WorkflowRun:
    """Search, plan, validate and revise at most once; no silent mock fallback."""
    mode = "mock" if os.getenv("MOCK_LLM", "true").lower() == "true" else "live"
    run = WorkflowRun(request=request.model_copy(deep=True), mode=mode)

    def step(name: str, attempt: int, operation: Callable, summarize: Callable):
        started = perf_counter()
        try:
            value = operation()
        except Exception:
            run.agent_trace.append({"step": name, "attempt": attempt,
                                    "status": "error", "mode": mode,
                                    "duration_ms": round((perf_counter() - started) * 1000)})
            raise
        run.agent_trace.append({"step": name, "attempt": attempt,
                                "status": "ok", "mode": mode,
                                "duration_ms": round((perf_counter() - started) * 1000),
                                **summarize(value)})
        return value

    if mode == "live" and not all(os.getenv(v, "").strip() for v in ("LLM_API_KEY", "LLM_MODEL")):
        run.error = "Configure LLM_API_KEY and LLM_MODEL in .env before using live mode."
        return run
    current_step = "recipe_search"
    try:
        run.candidates = step(current_step, 0, lambda: search_recipes(request),
                              lambda recipes: {"candidate_count": len(recipes)})
        if not run.candidates:
            run.error = "No eligible recipes"
            return run
        feedback = None
        for attempt in (1, 2):
            current_step = "planner"
            selected = step(current_step, attempt,
                            lambda: propose_menu(request, run.candidates, feedback),
                            lambda ids: {"recipe_ids": list(ids), "feedback": list(feedback or [])})
            current_step = "validator"
            assessment = step(current_step, attempt,
                              lambda: validate_plan(request, run.candidates, selected),
                              lambda result: {"assessment": result.model_dump()})
            if assessment.valid or attempt == 2:
                run.result = assessment
                return run
            feedback = list(assessment.issues)
    except Exception:
        run.error = (f"Workflow failed at {current_step}. Check recipe/price files or LLM "
                     "configuration and provider availability; no final plan was accepted.")
    return run


def run_workflow(request: PlanningRequest) -> PlanningResult:
    """Backward-compatible entry point for roles 1–3 and existing tests."""
    run = run_workflow_with_trace(request)
    if run.error:
        raise ValueError(run.error)
    assert run.result is not None
    return run.result
