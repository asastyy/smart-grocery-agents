"""Exact decimal arithmetic, independent of matching and availability claims."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from smart_grocery.retail.models import PackageQuote
from smart_grocery.schemas.integration import ProductOffer


def quote_packages(offer: ProductOffer, missing_quantity: Decimal | int | str) -> PackageQuote:
    missing = Decimal(str(missing_quantity))
    if not missing.is_finite() or missing <= 0:
        raise ValueError("Missing quantity must be finite and positive")
    if offer.price is None:
        raise ValueError("Unknown price cannot become a free purchase")
    count = int((missing / offer.package_quantity).to_integral_value(rounding=ROUND_CEILING))
    purchased = count * offer.package_quantity
    return PackageQuote(
        product_id=offer.product_id, required_quantity=missing, package_count=count,
        purchased_quantity=purchased, surplus_quantity=purchased - missing,
        total=(count * offer.price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        currency=offer.currency,
    )


def eligibility_reasons(offer: ProductOffer, *, unit: str, currency: str,
                        allergies: tuple[str, ...] = (), now: datetime | None = None,
                        max_age: timedelta = timedelta(hours=24)) -> list[str]:
    """Catalogue quotations may be displayed while purchase selection stays blocked."""
    reasons = []
    if offer.package_unit != unit:
        reasons.append("unit_mismatch")
    if offer.currency != currency:
        reasons.append("currency_mismatch")
    if offer.price is None:
        reasons.append("unknown_price")
    if offer.availability != "in_stock":
        reasons.append("out_of_stock" if offer.availability == "out_of_stock" else "availability_unknown")
    if allergies:
        if offer.allergens_status != "confirmed" or offer.allergens is None:
            reasons.append("allergens_unknown")
        elif set(allergies).intersection(offer.allergens):
            reasons.append("allergen_conflict")
    current = now or datetime.now(timezone.utc)
    age = current - offer.retrieved_at
    if age < -timedelta(minutes=5) or age > max_age:
        reasons.append("stale_or_future_offer")
    return reasons
