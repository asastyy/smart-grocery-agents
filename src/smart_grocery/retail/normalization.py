"""Normalize public VkusVill fields without inventing stock, volume or allergens."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import unescape
import re

from pydantic import ValidationError

from smart_grocery.retail.matching import SPECS, clean_text, match_product
from smart_grocery.retail.models import NormalizationIssue, RetailOffer


class UnusableOffer(ValueError):
    pass


def _number(value) -> Decimal:
    try:
        number = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise UnusableOffer("invalid_number") from None
    if not number.is_finite() or number < 0:
        raise UnusableOffer("invalid_number")
    return number


def _convert(value, unit: str) -> tuple[Decimal, str]:
    amount = _number(value)
    units = {"кг": (1000, "g"), "kg": (1000, "g"), "г": (1, "g"), "g": (1, "g"),
             "л": (1000, "ml"), "l": (1000, "ml"), "мл": (1, "ml"), "ml": (1, "ml"),
             "шт": (1, "pcs"), "pcs": (1, "pcs")}
    if unit not in units or amount <= 0:
        raise UnusableOffer("unknown_package_unit")
    factor, base = units[unit]
    # Remove binary floating-point noise from the upstream kg weight.
    return (amount * factor).quantize(Decimal("0.001")), base


def _package(raw: dict, ingredient_id: str) -> tuple[Decimal, str, str]:
    spec = SPECS[ingredient_id]
    if clean_text(raw.get("unit", "")) not in ("шт", "pcs"):
        raise UnusableOffer("variable_weight_price_not_package")
    title = clean_text(raw.get("name", ""))
    if re.search(r"\d\s*[xх×*]\s*\d", title):
        raise UnusableOffer("multipack_requires_review")
    amounts = re.findall(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(кг|kg|мл|ml|г|g|л|l|шт|pcs)(?!\w)", title)
    compatible = [_convert(value, unit) for value, unit in amounts]
    compatible = [(value, unit) for value, unit in compatible if unit == spec.unit]
    if len(set(compatible)) > 1:
        raise UnusableOffer("ambiguous_package_size")
    if compatible:
        quantity, unit = compatible[0]
        weight = raw.get("weight")
        if isinstance(weight, dict):
            weight_quantity, weight_unit = _convert(weight.get("value"), clean_text(weight.get("unit", "")))
            if weight_unit == unit and weight_quantity != quantity:
                raise UnusableOffer("conflicting_package_size")
        return quantity, unit, "title"
    if spec.unit == "pcs":
        description = clean_text(raw.get("description", ""))
        match = re.search(r"в упаковке\s+(\d+)\s*(десятк|десяток|шт)", description)
        if match:
            count = int(match[1]) * (10 if match[2].startswith("десят") else 1)
            return Decimal(count), "pcs", "description:explicit_package_count"
    weight = raw.get("weight")
    if isinstance(weight, dict):
        quantity, unit = _convert(weight.get("value"), clean_text(weight.get("unit", "")))
        if unit == spec.unit:
            return quantity, unit, "weight"
    # In particular: 0.5 kg of oil is NOT 500 ml. Unknown remains unknown.
    raise UnusableOffer("package_quantity_unverified")


def _properties(raw: dict) -> dict[str, str]:
    return {clean_text(item.get("name", "")): re.sub(r"<[^>]*>", " ", unescape(str(item.get("value", "")))).strip()
            for item in raw.get("properties", []) if isinstance(item, dict)}


def normalize_product(raw: dict, ingredient_id: str, retrieved_at: datetime, *,
                      personalized: bool = False) -> tuple[RetailOffer | None, NormalizationIssue | None]:
    if not isinstance(raw, dict):
        return None, NormalizationIssue(product_id="unknown", code="invalid_product_fields", message="Expected a product object")
    product_id = str(raw.get("id", "unknown"))
    try:
        if not re.fullmatch(r"[1-9]\d*", product_id):
            raise UnusableOffer("invalid_product_id")
        match = match_product(ingredient_id, raw.get("name", ""))
        if match.status != "accepted":
            raise UnusableOffer("match_" + match.status)
        quantity, unit, package_source = _package(raw, ingredient_id)
        warnings = []
        price = raw.get("price")
        if not isinstance(price, dict):
            raise UnusableOffer("invalid_price_structure")
        current, old = price.get("current"), price.get("old")
        price_source = "price.current"
        amount = _number(current) if current is not None else None
        if old is not None and current is not None and _number(old) > _number(current):
            amount, price_source = _number(old), "price.old:discount_not_assumed"
            warnings.append("discount_requires_confirmation")
        elif price.get("discount_info"):
            amount = None
            warnings.append("discount_eligibility_unknown")
        availability = "unknown"
        available = raw.get("available_quantity")
        if personalized and available is not None:
            availability = "in_stock" if _number(available) > 0 else "out_of_stock"
        if availability == "unknown":
            warnings.append("availability_not_confirmed_for_address")
        properties = _properties(raw)
        composition = properties.get("состав") or None
        warnings.append("allergens_not_verified")
        nutrition_text = properties.get("пищевая и энергетическая ценность в 100 г", "")
        nutrition = {}
        for key, pattern in {"protein_g": r"белки\s+(\d+(?:[.,]\d+)?)", "fat_g": r"жиры\s+(\d+(?:[.,]\d+)?)",
                             "carbohydrate_g": r"углеводы\s+(\d+(?:[.,]\d+)?)", "energy_kcal": r"(\d+(?:[.,]\d+)?)\s*ккал"}.items():
            values = {_number(value) for value in re.findall(pattern, nutrition_text.casefold())}
            if len(values) == 1:
                nutrition[key] = values.pop()
        offer = RetailOffer(
            retailer="vkusvill", product_id=product_id, ingredient_id=ingredient_id,
            title=unescape(raw["name"]), brand=raw.get("brand"), package_quantity=quantity,
            package_unit=unit, price=amount, currency=price.get("currency", ""), availability=availability,
            url=raw.get("url"), retrieved_at=retrieved_at, ingredients=composition,
            nutrition=nutrition or None, allergens_status="unknown", allergens=None,
            package_source=package_source, price_source=price_source,
            availability_scope="delivery_context" if personalized else "unknown", warnings=warnings,
        )
        return offer, None
    except (UnusableOffer, ValidationError, KeyError, TypeError, InvalidOperation) as exc:
        code = str(exc) if isinstance(exc, UnusableOffer) else "invalid_product_fields"
        return None, NormalizationIssue(product_id=product_id, code=code,
                                         message="Offer requires review before matching and purchase calculation")
