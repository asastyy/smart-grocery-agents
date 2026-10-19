"""Streamlit entry point for role 4; calculations live in the team modules."""
import json
from pathlib import Path
import sys

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env", override=False)

from smart_grocery.schemas.models import PlanningRequest
from smart_grocery.workflow.runner import run_workflow_with_trace

st.set_page_config(page_title="Smart Grocery Agents", page_icon="🥗", layout="wide")
st.title("Smart Grocery Agents")
st.caption("Prototype with demo recipes and illustrative prices. Pantry items are treated as available without quantity limits.")
st.caption("MVP: one meal per day for one person, quantities in illustrative portions. These are not store prices. Multi-person scaling belongs to the calculator module and is not supported yet.")
example = json.loads((ROOT / "examples/request.json").read_text(encoding="utf-8"))
pantry = st.text_input("Pantry (comma-separated)", ", ".join(example["pantry"]))
budget = st.number_input("Budget", min_value=0.0, value=float(example["budget"]), step=0.5)
days = st.slider("Days", 1, 7, int(example["days"]))
diet = st.selectbox("Diet", ["none", "vegetarian", "vegan"])
st.caption("Currency: EUR — the fixed demo price catalog. Use normalized English ingredient IDs, e.g. eggs, tomato, rice.")

request = PlanningRequest(
    pantry=list(dict.fromkeys(s.strip().lower() for s in pantry.split(",") if s.strip())),
    budget=budget, days=days, servings=1, diet=diet, currency="EUR",
)
if st.button("Plan meals", type="primary"):
    with st.spinner("Searching recipes, planning and checking the menu…"):
        st.session_state["workflow_run"] = run_workflow_with_trace(request)

run = st.session_state.get("workflow_run")
if run is not None:
    if run.request != request:
        st.warning("Inputs changed. Click Plan meals to calculate a new result. The result below belongs to the saved request.")
    if run.mode == "mock":
        st.warning("MOCK mode: fixed planner output, no LLM calls. It may stay invalid after revision. Live LLM must be checked before the proposal.")
    else:
        st.caption("Live mode requested. The trace shows completed steps; check critic messages for API failures.")
    with st.expander("Saved request"):
        st.json(run.request.model_dump())
    if run.error:
        st.error(run.error)
    result = run.result
    if result is not None:
        if result.valid:
            st.success("Valid plan")
            st.metric("Estimated demo cost", f"{result.total_cost:.2f} {result.currency}")
        else:
            st.warning("Plan requires revision. Do not use this result as a complete shopping estimate.")
            for issue in result.issues:
                st.error(issue)
            st.metric("Calculated subtotal — unvalidated", f"{result.total_cost:.2f} {result.currency}")
        st.subheader("Selected recipes")
        names = {recipe.id: recipe.name for recipe in run.candidates}
        for day, recipe_id in enumerate(result.recipe_ids, start=1):
            st.write(f"Day {day} · {names.get(recipe_id, recipe_id)} ({recipe_id})")
        st.subheader("Shopping list" if result.valid else "Calculated shopping items — check issues above")
        if result.shopping:
            st.dataframe([line.model_dump() for line in result.shopping], hide_index=True)
        elif result.valid:
            st.info("No purchases needed under the demo pantry assumptions.")
        else:
            st.info("No priced shopping items to display. This does not confirm that no purchases are needed.")
        with st.expander("Result details"):
            st.json(result.model_dump())
    st.subheader("Agent trace")
    for event in run.agent_trace:
        label = f"{event['step']} · attempt {event['attempt']} · {event['status']} · {event['duration_ms']} ms"
        with st.expander(label):
            st.json(event)
    st.download_button("Download result and trace", json.dumps(run.model_dump(), ensure_ascii=False, indent=2),
                       file_name="smart-grocery-result.json", mime="application/json")
