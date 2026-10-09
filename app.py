import json
import streamlit as st
from smart_grocery.schemas.models import PlanningRequest
from smart_grocery.workflow.runner import run_workflow

st.set_page_config(page_title="Smart Grocery Agents")
st.title("Smart Grocery Agents")
st.caption("Prototype: curated demo recipes, illustrative prices; set MOCK_LLM=false for model-backed planning")
with open("examples/request.json", encoding="utf-8") as f:
    example = json.load(f)
pantry = st.text_input("Pantry (comma-separated)", ", ".join(example["pantry"]))
budget = st.number_input("Budget", min_value=0.0, value=float(example["budget"]))
days = st.slider("Days", 1, 5, int(example["days"]))
diet = st.selectbox("Diet", ["none", "vegetarian", "vegan"])
if st.button("Plan meals"):
    try:
        request = PlanningRequest(pantry=[s.strip().lower() for s in pantry.split(",") if s.strip()],budget=budget,days=days,servings=1,diet=diet)
        result = run_workflow(request)
        st.success("Valid plan" if result.valid else "Plan requires revision")
        st.json(result.model_dump())
    except Exception as exc:
        st.error(str(exc))
