import json
import streamlit as st
from smart_grocery.schemas.models import PlanningRequest
from smart_grocery.workflow.runner import run_workflow

st.set_page_config(page_title="Smart Grocery Agents")
st.title("Smart Grocery Agents")
st.caption("Prototype with demo recipes and illustrative prices. Pantry items are treated as available without quantity limits.")
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
        if result.valid:
            st.success("Valid plan")
            st.metric("Estimated demo cost", f"{result.total_cost:.2f} {result.currency}")
        else:
            st.warning("Plan requires revision. Do not use this result as a complete shopping estimate.")
            for issue in result.issues:
                st.error(issue)
            st.metric("Calculated subtotal — unvalidated", f"{result.total_cost:.2f} {result.currency}")
        st.subheader("Selected recipes")
        st.write(", ".join(result.recipe_ids))
        st.subheader("Shopping list" if result.valid else "Calculated shopping items — check issues above")
        if result.shopping:
            st.dataframe([line.model_dump() for line in result.shopping], hide_index=True)
        elif result.valid:
            st.info("No purchases needed under the demo pantry assumptions.")
        else:
            st.info("No priced shopping items to display. This does not confirm that no purchases are needed.")
        with st.expander("Result details"):
            st.json(result.model_dump())
    except Exception as exc:
        st.error(str(exc))
