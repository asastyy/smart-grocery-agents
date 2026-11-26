from datetime import date, timedelta
from decimal import Decimal

import pytest

from smart_grocery.schemas.foodcom import Ingredient
from smart_grocery.schemas.integration import InventoryItem
from smart_grocery.tools.inventory import (
    apply_consumption,
    available_inventory,
    confirm_inventory_suggestion,
    plan_consumption,
    suggest_inventory_from_purchase,
)


TODAY = date(2026, 11, 26)


def item(item_id, quantity, *, expiry_days=None, confidence=1, status="available", unit="g"):
    return InventoryItem(
        inventory_item_id=item_id, ingredient_id="rice", display_name="Rice",
        quantity=quantity, unit=unit, source="manual", confidence=confidence,
        status=status, expiry_date=TODAY + timedelta(days=expiry_days) if expiry_days is not None else None,
    )


def test_only_confirmed_available_unexpired_stock_is_usable():
    inventory = [
        item("ok", 100), item("guess", 100, confidence=Decimal("0.8")),
        item("expired", 100, expiry_days=-1), item("reserved", 100, status="reserved"),
    ]
    assert [entry.inventory_item_id for entry in available_inventory(inventory, as_of=TODAY)] == ["ok"]


def test_purchase_history_requires_confirmation():
    suggestion = suggest_inventory_from_purchase("rice", "Rice", quantity=Decimal("500"), unit="g")
    assert suggestion.confidence < 1
    assert available_inventory([], as_of=TODAY) == []
    confirmed = confirm_inventory_suggestion(suggestion)
    assert confirmed.confidence == 1
    assert confirmed.quantity == 500


def test_unknown_purchase_quantity_cannot_become_stock():
    suggestion = suggest_inventory_from_purchase("rice", "Rice")
    with pytest.raises(ValueError, match="quantity and unit"):
        confirm_inventory_suggestion(suggestion)


def test_consumption_uses_earliest_expiry_and_does_not_mutate_planning_input():
    inventory = [item("later", 100, expiry_days=10), item("first", 80, expiry_days=1)]
    requirement = Ingredient(ingredient_id="rice", quantity=120, unit="g")
    plan = plan_consumption(inventory, [requirement], as_of=TODAY)
    assert [(a.inventory_item_id, a.quantity) for a in plan.allocations] == [
        ("first", Decimal("80")), ("later", Decimal("40"))
    ]
    assert [entry.quantity for entry in inventory] == [100, 80]
    with pytest.raises(ValueError, match="explicit confirmation"):
        apply_consumption(inventory, plan, confirmed=False)
    assert [entry.quantity for entry in inventory] == [100, 80]


def test_confirmed_consumption_returns_new_inventory_and_never_goes_negative():
    inventory = [item("first", 80)]
    requirement = Ingredient(ingredient_id="rice", quantity=120, unit="g")
    plan = plan_consumption(inventory, [requirement], as_of=TODAY)
    assert plan.shortages[0].quantity == 40
    update = apply_consumption(inventory, plan, confirmed=True)
    assert inventory[0].quantity == 80
    assert update.inventory[0].quantity == 0
    assert update.inventory[0].status == "depleted"
    assert update.events[0].action == "deplete"


def test_incompatible_units_are_not_silently_converted():
    inventory = [item("pieces", 2, unit="pcs")]
    requirement = Ingredient(ingredient_id="rice", quantity=100, unit="g")
    plan = plan_consumption(inventory, [requirement], as_of=TODAY)
    assert plan.allocations == []
    assert plan.shortages[0].quantity == 100
