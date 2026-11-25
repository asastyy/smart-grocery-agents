"""Reproducible report; catalogue price quotes are distinct from safe selection."""
from datetime import datetime, timezone
import json

from smart_grocery.retail.matching import SPECS
from smart_grocery.retail.purchasing import eligibility_reasons, quote_packages
from smart_grocery.tools.grocery_provider import ProviderUnavailable
from smart_grocery.workflow.golden import load_golden_case
from smart_grocery.workflow.integration import run_integration_workflow


def build_retail_report(provider) -> dict:
    generated_at = datetime.now(timezone.utc)
    offers = []
    errors = []
    by_ingredient = {}
    for ingredient_id in SPECS:
        try:
            found = provider.search_products(ingredient_id)
        except ProviderUnavailable:
            found = []
            errors.append({"ingredient_id": ingredient_id, "code": "provider_unavailable"})
        offers.extend(found)
        by_ingredient[ingredient_id] = len(found)
    case, _ = load_golden_case()
    result = run_integration_workflow(case.profile, case.inventory, case.recipes, provider,
                                      days=case.days, mock_planner=True)
    rice_quotes = []
    for offer in offers:
        if offer.ingredient_id == "rice":
            rice_quotes.append({"offer": offer.model_dump(mode="json"),
                                "quote": quote_packages(offer, 600).model_dump(mode="json"),
                                "selection_blockers": eligibility_reasons(
                                    offer, unit="g", currency="RUB", allergies=("peanut",), now=generated_at)})
    return {
        "generated_at": generated_at.isoformat(),
        "price_kind": "catalogue_snapshot_not_delivery_quote",
        "normalized_offer_count": len(offers), "offers_by_ingredient": by_ingredient,
        "offers": [offer.model_dump(mode="json") for offer in offers],
        "normalization_issues": [issue.model_dump() for issue in provider.issues], "errors": errors,
        "rice_600g_quotes": rice_quotes,
        "golden_case_strict": json.loads(result.model_dump_json()),
        "note": "Unknown availability or allergens cannot produce a confirmed purchasable basket. No order or payment is made.",
    }
